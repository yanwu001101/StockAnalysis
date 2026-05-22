package com.stock.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

@Service
public class DataService {

    @Value("${data-service.url}")
    private String dataServiceUrl;

    private final RestTemplate restTemplate;
    private final RedisTemplate<String, Object> redisTemplate;

    public DataService(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10000);
        factory.setReadTimeout(120000);
        this.restTemplate = new RestTemplate(factory);
    }

    public JSONObject getMarketSummary() {
        return getCachedJsonObject("market:summary",
            () -> restTemplate.getForObject(dataServiceUrl + "/api/market/summary", String.class), 300);
    }

    public JSONArray getTopStocks(int limit) {
        return getCachedJsonArray("market:top:" + limit,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/market/top-stocks?limit=" + limit, String.class), 300);
    }

    public JSONObject getStockDetail(String code) {
        return getCachedJsonObject("stock:" + code,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/stock/" + code, String.class), 600);
    }

    public JSONArray getStockKLine(String code, String period, int days) {
        String key = "kline:" + code + ":" + period + ":" + days;
        return getCachedJsonArray(key,
            () -> restTemplate.getForObject(
                dataServiceUrl + "/api/stock/" + code + "/kline?period=" + period + "&days=" + days, String.class), 600);
    }

    public JSONObject getStockStrategies(String code) {
        return getCachedJsonObject("strategies:v2:" + code, () -> {
            // Prefer v2 endpoint; fall back to legacy if v2 fails.
            try {
                String resp = restTemplate.getForObject(
                    dataServiceUrl + "/api/v2/stock/" + code + "/score", String.class);
                if (resp != null && !resp.isEmpty()) {
                    return resp;
                }
            } catch (Exception ignored) {}
            return restTemplate.getForObject(
                dataServiceUrl + "/api/stock/" + code + "/strategies", String.class);
        }, 600);
    }

    public JSONObject getStockF10(String code) {
        return getCachedJsonObject("f10:" + code,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/stock/" + code + "/f10", String.class), 1800);
    }

    public JSONArray getStrategiesMeta() {
        return getCachedJsonArray("strategies:meta",
            () -> restTemplate.getForObject(dataServiceUrl + "/api/v2/strategies", String.class), 600);
    }

    public JSONArray getConditionFields() {
        return getCachedJsonArray("conditions:fields",
            () -> restTemplate.getForObject(dataServiceUrl + "/api/v2/condition-fields", String.class), 3600);
    }

    public JSONArray runConditionScreener(JSONObject body) {
        String resp = restTemplate.postForObject(
            dataServiceUrl + "/api/v2/screen/conditions", body, String.class);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return JSON.parseArray(resp);
    }

    public JSONObject getExpressionHelp() {
        return getCachedJsonObject("expression:help",
            () -> restTemplate.getForObject(dataServiceUrl + "/api/v2/expression/help", String.class), 3600);
    }

    public Object runExpressionScreener(JSONObject body) {
        String resp = restTemplate.postForObject(
            dataServiceUrl + "/api/v2/screen/expression", body, String.class);
        Object parsed = JSON.parse(resp);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return parsed;
    }

    public JSONObject validateExpression(JSONObject body) {
        try {
            String resp = restTemplate.postForObject(
                dataServiceUrl + "/api/v2/screen/expression/validate", body, String.class);
            DataTimeHolder.recordOldest(System.currentTimeMillis());
            return JSON.parseObject(resp);
        } catch (org.springframework.web.client.HttpClientErrorException e) {
            return JSON.parseObject(e.getResponseBodyAsString());
        }
    }

    public JSONArray getScreener(JSONObject request) {
        try {
            String resp = restTemplate.postForObject(
                dataServiceUrl + "/api/v2/screen", request, String.class);
            if (resp != null && !resp.isEmpty() && !resp.startsWith("{\"error\"")) {
                JSONArray arr = JSON.parseArray(resp);
                if (arr != null && !arr.isEmpty()) {
                    DataTimeHolder.recordOldest(System.currentTimeMillis());
                    return arr;
                }
            }
        } catch (Exception ignored) {}
        String resp = restTemplate.postForObject(
            dataServiceUrl + "/api/screen", request, String.class);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return JSON.parseArray(resp);
    }

    public JSONObject runBacktest(JSONObject request) {
        String resp = restTemplate.postForObject(dataServiceUrl + "/api/backtest", request, String.class);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return JSON.parseObject(resp);
    }

    public JSONArray getSectorRotation() {
        return getCachedJsonArray("market:sectors",
            () -> restTemplate.getForObject(dataServiceUrl + "/api/market/sector-rotation", String.class), 600);
    }

    public JSONArray getNorthboundFlow(int days) {
        return getCachedJsonArray("market:northbound:" + days,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/market/northbound-flow?days=" + days, String.class), 300);
    }

    public JSONArray getIndices() {
        return getCachedJsonArray("market:indices",
            () -> restTemplate.getForObject(dataServiceUrl + "/api/market/indices", String.class), 60);
    }

    public JSONArray getGainers(int limit) {
        return getCachedJsonArray("market:gainers:" + limit,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/market/gainers?limit=" + limit, String.class), 120);
    }

    public JSONArray getLosers(int limit) {
        return getCachedJsonArray("market:losers:" + limit,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/market/losers?limit=" + limit, String.class), 120);
    }

    public JSONArray getMostActive(int limit) {
        return getCachedJsonArray("market:most-active:" + limit,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/market/most-active?limit=" + limit, String.class), 120);
    }

    public JSONArray getLhbRecent(int days, String code) {
        String key = "lhb:recent:" + days + ":" + (code == null ? "" : code);
        return getCachedJsonArray(key, () -> {
            String url = dataServiceUrl + "/api/lhb/recent?days=" + days +
                (code != null && !code.isEmpty() ? "&code=" + code : "");
            return restTemplate.getForObject(url, String.class);
        }, 300);
    }

    public JSONArray getLhbInstitutionRank(int days) {
        return getCachedJsonArray("lhb:inst:" + days,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/lhb/institution-rank?days=" + days, String.class), 300);
    }

    public JSONArray getLhbStockRank(int days) {
        return getCachedJsonArray("lhb:stock:" + days,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/lhb/stock-rank?days=" + days, String.class), 300);
    }

    public JSONObject getStockPrediction(String code) {
        return getCachedJsonObject("prediction:" + code,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/v2/stock/" + code + "/prediction", String.class), 600);
    }

    public JSONObject getStockProSignal(String code) {
        return getCachedJsonObject("prosignal:" + code,
            () -> restTemplate.getForObject(dataServiceUrl + "/api/v2/stock/" + code + "/pro-signal", String.class), 300);
    }

    public JSONArray searchStock(String keyword) {
        String resp = restTemplate.getForObject(dataServiceUrl + "/api/stock/search?keyword=" + keyword, String.class);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return JSON.parseArray(resp);
    }

    public JSONArray getMoneyFlowMainRank(int days, int limit, String direction) {
        String key = "mf:main:" + days + ":" + limit + ":" + direction;
        return getCachedJsonArray(key,
            () -> restTemplate.getForObject(
                dataServiceUrl + "/api/moneyflow/main-rank?days=" + days +
                "&limit=" + limit + "&direction=" + direction, String.class), 120);
    }

    public JSONArray getMoneyFlowNorthboundRank(int days, int limit) {
        String key = "mf:nb:" + days + ":" + limit;
        return getCachedJsonArray(key,
            () -> restTemplate.getForObject(
                dataServiceUrl + "/api/moneyflow/northbound-rank?days=" + days +
                "&limit=" + limit, String.class), 300);
    }

    public JSONArray getMoneyFlowSector() {
        return getCachedJsonArray("mf:sector",
            () -> restTemplate.getForObject(dataServiceUrl + "/api/moneyflow/sector", String.class), 120);
    }

    public JSONArray getMoneyFlowStock(String code, int days) {
        String key = "mf:stock:" + code + ":" + days;
        return getCachedJsonArray(key,
            () -> restTemplate.getForObject(
                dataServiceUrl + "/api/moneyflow/stock/" + code + "?days=" + days, String.class), 300);
    }

    private JSONObject getCachedJsonObject(String key, Supplier<String> fetcher, int ttlSeconds) {
        String raw = getCachedString(key, fetcher, ttlSeconds);
        return raw == null ? null : JSON.parseObject(raw);
    }

    private JSONArray getCachedJsonArray(String key, Supplier<String> fetcher, int ttlSeconds) {
        String raw = getCachedString(key, fetcher, ttlSeconds);
        return raw == null ? null : JSON.parseArray(raw);
    }

    private String getCachedString(String key, Supplier<String> fetcher, int ttlSeconds) {
        String cacheKey = "stock:" + key;
        try {
            Object cached = redisTemplate.opsForValue().get(cacheKey);
            if (cached instanceof CachedEntry entry && entry.getJson() != null) {
                DataTimeHolder.recordOldest(entry.getWrittenAt());
                return entry.getJson();
            }
        } catch (Exception ignored) {}

        String raw = fetcher.get();
        long now = System.currentTimeMillis();
        DataTimeHolder.recordOldest(now);
        if (raw != null) {
            try {
                redisTemplate.opsForValue().set(cacheKey, new CachedEntry(raw, now), ttlSeconds, TimeUnit.SECONDS);
            } catch (Exception ignored) {}
        }
        return raw;
    }
}

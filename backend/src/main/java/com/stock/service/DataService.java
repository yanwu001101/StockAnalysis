package com.stock.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

import java.util.*;
import java.util.concurrent.TimeUnit;

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
        return getCachedOrFetch("market:summary", () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/market/summary", String.class);
            return JSON.parseObject(resp);
        }, 300);
    }

    public JSONArray getTopStocks(int limit) {
        return getCachedOrFetch("market:top:" + limit, () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/market/top-stocks?limit=" + limit, String.class);
            return JSON.parseArray(resp);
        }, 300);
    }

    public JSONObject getStockDetail(String code) {
        return getCachedOrFetch("stock:" + code, () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/stock/" + code, String.class);
            return JSON.parseObject(resp);
        }, 600);
    }

    public JSONArray getStockKLine(String code, String period, int days) {
        String key = "kline:" + code + ":" + period + ":" + days;
        return getCachedOrFetch(key, () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/stock/" + code + "/kline?period=" + period + "&days=" + days, String.class);
            return JSON.parseArray(resp);
        }, 600);
    }

    public JSONObject getStockStrategies(String code) {
        return getCachedOrFetch("strategies:v2:" + code, () -> {
            // Use the v2 endpoint backed by the new 10-strategy registry.
            // Falls back to the legacy route if v2 is unavailable so we
            // never break the page during the migration.
            try {
                String resp = restTemplate.getForObject(
                    dataServiceUrl + "/api/v2/stock/" + code + "/score", String.class);
                if (resp != null && !resp.isEmpty()) {
                    return JSON.parseObject(resp);
                }
            } catch (Exception ignored) {}
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/stock/" + code + "/strategies", String.class);
            return JSON.parseObject(resp);
        }, 600);
    }

    public JSONObject getStockF10(String code) {
        return getCachedOrFetch("f10:" + code, () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/stock/" + code + "/f10", String.class);
            return JSON.parseObject(resp);
        }, 1800);
    }

    public JSONArray getStrategiesMeta() {
        return getCachedOrFetch("strategies:meta", () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/v2/strategies", String.class);
            return JSON.parseArray(resp);
        }, 600);
    }

    public JSONArray getConditionFields() {
        return getCachedOrFetch("conditions:fields", () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/v2/condition-fields", String.class);
            return JSON.parseArray(resp);
        }, 3600);
    }

    public JSONArray runConditionScreener(JSONObject body) {
        String resp = restTemplate.postForObject(
            dataServiceUrl + "/api/v2/screen/conditions", body, String.class);
        return JSON.parseArray(resp);
    }

    public JSONObject getExpressionHelp() {
        return getCachedOrFetch("expression:help", () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/v2/expression/help", String.class);
            return JSON.parseObject(resp);
        }, 3600);
    }

    public Object runExpressionScreener(JSONObject body) {
        String resp = restTemplate.postForObject(
            dataServiceUrl + "/api/v2/screen/expression", body, String.class);
        // data-service returns either an array (success) or {error: "..."} on parse fail
        Object parsed = JSON.parse(resp);
        return parsed;
    }

    public JSONObject validateExpression(JSONObject body) {
        try {
            String resp = restTemplate.postForObject(
                dataServiceUrl + "/api/v2/screen/expression/validate", body, String.class);
            return JSON.parseObject(resp);
        } catch (org.springframework.web.client.HttpClientErrorException e) {
            // 400 from data-service when expression invalid — parse body as JSON
            return JSON.parseObject(e.getResponseBodyAsString());
        }
    }

    public JSONArray getScreener(JSONObject request) {
        // Prefer the v2 endpoint (10-strategy composite). Fall back to legacy
        // /api/screen if v2 returns an error or empty so the page never blanks.
        try {
            String resp = restTemplate.postForObject(
                dataServiceUrl + "/api/v2/screen", request, String.class);
            if (resp != null && !resp.isEmpty() && !resp.startsWith("{\"error\"")) {
                JSONArray arr = JSON.parseArray(resp);
                if (arr != null && !arr.isEmpty()) return arr;
            }
        } catch (Exception ignored) {}
        String resp = restTemplate.postForObject(
            dataServiceUrl + "/api/screen", request, String.class);
        return JSON.parseArray(resp);
    }

    public JSONObject runBacktest(JSONObject request) {
        String resp = restTemplate.postForObject(dataServiceUrl + "/api/backtest", request, String.class);
        return JSON.parseObject(resp);
    }

    public JSONArray getSectorRotation() {
        return getCachedOrFetch("market:sectors", () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/market/sector-rotation", String.class);
            return JSON.parseArray(resp);
        }, 600);
    }

    public JSONArray getNorthboundFlow(int days) {
        return getCachedOrFetch("market:northbound:" + days, () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/market/northbound-flow?days=" + days, String.class);
            return JSON.parseArray(resp);
        }, 300);
    }

    public JSONArray getIndices() {
        return getCachedOrFetch("market:indices", () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/market/indices", String.class);
            return JSON.parseArray(resp);
        }, 60);
    }

    public JSONArray getGainers(int limit) {
        return getCachedOrFetch("market:gainers:" + limit, () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/market/gainers?limit=" + limit, String.class);
            return JSON.parseArray(resp);
        }, 120);
    }

    public JSONArray getLosers(int limit) {
        return getCachedOrFetch("market:losers:" + limit, () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/market/losers?limit=" + limit, String.class);
            return JSON.parseArray(resp);
        }, 120);
    }

    public JSONArray getMostActive(int limit) {
        return getCachedOrFetch("market:most-active:" + limit, () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/market/most-active?limit=" + limit, String.class);
            return JSON.parseArray(resp);
        }, 120);
    }

    public JSONArray getLhbRecent(int days, String code) {
        String key = "lhb:recent:" + days + ":" + (code == null ? "" : code);
        return getCachedOrFetch(key, () -> {
            String url = dataServiceUrl + "/api/lhb/recent?days=" + days +
                (code != null && !code.isEmpty() ? "&code=" + code : "");
            String resp = restTemplate.getForObject(url, String.class);
            return JSON.parseArray(resp);
        }, 300);
    }

    public JSONArray getLhbInstitutionRank(int days) {
        return getCachedOrFetch("lhb:inst:" + days, () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/lhb/institution-rank?days=" + days, String.class);
            return JSON.parseArray(resp);
        }, 300);
    }

    public JSONArray getLhbStockRank(int days) {
        return getCachedOrFetch("lhb:stock:" + days, () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/lhb/stock-rank?days=" + days, String.class);
            return JSON.parseArray(resp);
        }, 300);
    }

    public JSONArray searchStock(String keyword) {
        String resp = restTemplate.getForObject(dataServiceUrl + "/api/stock/search?keyword=" + keyword, String.class);
        return JSON.parseArray(resp);
    }

    public JSONArray getMoneyFlowMainRank(int days, int limit, String direction) {
        String key = "mf:main:" + days + ":" + limit + ":" + direction;
        return getCachedOrFetch(key, () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/moneyflow/main-rank?days=" + days +
                "&limit=" + limit + "&direction=" + direction, String.class);
            return JSON.parseArray(resp);
        }, 120);
    }

    public JSONArray getMoneyFlowNorthboundRank(int days, int limit) {
        String key = "mf:nb:" + days + ":" + limit;
        return getCachedOrFetch(key, () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/moneyflow/northbound-rank?days=" + days +
                "&limit=" + limit, String.class);
            return JSON.parseArray(resp);
        }, 300);
    }

    public JSONArray getMoneyFlowSector() {
        return getCachedOrFetch("mf:sector", () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/moneyflow/sector", String.class);
            return JSON.parseArray(resp);
        }, 120);
    }

    public JSONArray getMoneyFlowStock(String code, int days) {
        String key = "mf:stock:" + code + ":" + days;
        return getCachedOrFetch(key, () -> {
            String resp = restTemplate.getForObject(
                dataServiceUrl + "/api/moneyflow/stock/" + code + "?days=" + days, String.class);
            return JSON.parseArray(resp);
        }, 300);
    }

    @SuppressWarnings("unchecked")
    private <T> T getCachedOrFetch(String key, Fetcher<T> fetcher, int ttlSeconds) {
        String cacheKey = "stock:" + key;
        try {
            Object cached = redisTemplate.opsForValue().get(cacheKey);
            if (cached != null) {
                return (T) cached;
            }
        } catch (Exception ignored) {}

        T result = fetcher.fetch();
        try {
            redisTemplate.opsForValue().set(cacheKey, result, ttlSeconds, TimeUnit.SECONDS);
        } catch (Exception ignored) {}
        return result;
    }

    @FunctionalInterface
    private interface Fetcher<T> {
        T fetch();
    }
}

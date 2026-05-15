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
        return getCachedOrFetch("strategies:" + code, () -> {
            String resp = restTemplate.getForObject(dataServiceUrl + "/api/stock/" + code + "/strategies", String.class);
            return JSON.parseObject(resp);
        }, 600);
    }

    public JSONArray getScreener(JSONObject request) {
        String resp = restTemplate.postForObject(dataServiceUrl + "/api/screen", request, String.class);
        return JSON.parseArray(resp);
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

    public JSONArray searchStock(String keyword) {
        String resp = restTemplate.getForObject(dataServiceUrl + "/api/stock/search?keyword=" + keyword, String.class);
        return JSON.parseArray(resp);
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

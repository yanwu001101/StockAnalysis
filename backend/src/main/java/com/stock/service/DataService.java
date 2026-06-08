package com.stock.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

/**
 * Pass-through proxy to the Python data-service with two-tier caching.
 *
 * <h3>Cache layering</h3>
 * <ol>
 *   <li><b>L1 Caffeine</b> — 15 s, in-process. Most rapid-fire dashboard
 *       requests stop here.</li>
 *   <li><b>L2 Redis</b> — per-endpoint TTL. Survives single-instance restart.</li>
 *   <li><b>Origin</b> — protected by a per-key lock so a cache miss never lets
 *       N concurrent callers stampede the same upstream fetch.</li>
 * </ol>
 *
 * <h3>Conventions</h3>
 * Most pass-throughs use {@link #cached} / {@link #cachedArr}. Endpoints whose
 * result is too fresh to cache (user-submitted POSTs, admin actions) use
 * {@link #postArr} / {@link #postObj} / {@link #getObjNoCache}.
 */
@Service
public class DataService {

    @Value("${data-service.url}")
    private String dataServiceUrl;

    private final RestTemplate restTemplate;
    private final RedisTemplate<String, Object> redisTemplate;

    /**
     * In-process L1 with a short TTL. Inside this window the same key never
     * touches Redis, let alone the data-service — useful for the dashboard,
     * which loads indices / gainers / losers / most-active back-to-back.
     */
    private final Cache<String, CachedEntry> l1 = Caffeine.newBuilder()
            .maximumSize(2000)
            .expireAfterWrite(Duration.ofSeconds(15))
            .build();

    /** Per-key lock so a cache miss never lets N concurrent requests stampede the same fetcher. */
    private final ConcurrentHashMap<String, Object> keyLocks = new ConcurrentHashMap<>();

    public DataService(RestTemplate restTemplate, RedisTemplate<String, Object> redisTemplate) {
        this.restTemplate = restTemplate;
        this.redisTemplate = redisTemplate;
    }

    // =====================================================================
    // Market
    // =====================================================================

    public JSONObject getMarketSummary()            { return cached("market:summary", "/api/market/summary", 60); }
    public JSONArray  getTopStocks(int limit)       { return cachedArr("market:top:" + limit, "/api/market/top-stocks?limit=" + limit, 60); }
    public JSONArray  getSectorRotation()           { return cachedArr("market:sectors", "/api/market/sector-rotation", 60); }
    public JSONArray  getNorthboundFlow(int days)   { return cachedArr("market:northbound:" + days, "/api/market/northbound-flow?days=" + days, 120); }
    public JSONArray  getIndices()                  { return cachedArr("market:indices", "/api/market/indices", 60); }
    public JSONArray  getGainers(int limit)         { return cachedArr("market:gainers:" + limit, "/api/market/gainers?limit=" + limit, 30); }
    public JSONArray  getLosers(int limit)          { return cachedArr("market:losers:" + limit, "/api/market/losers?limit=" + limit, 30); }
    public JSONArray  getMostActive(int limit)      { return cachedArr("market:most-active:" + limit, "/api/market/most-active?limit=" + limit, 30); }

    // =====================================================================
    // Stock detail
    // =====================================================================

    public JSONObject getStockDetail(String code)       { return cached("stock:" + code, "/api/stock/" + code, 60); }
    public JSONObject getStockF10(String code)          { return cached("f10:" + code, "/api/stock/" + code + "/f10", 1800); }
    public JSONObject getStockPrediction(String code)   { return cached("prediction:" + code, "/api/v2/stock/" + code + "/prediction", 120); }
    public JSONObject getStockProSignal(String code)    { return cached("prosignal:" + code, "/api/v2/stock/" + code + "/pro-signal", 60); }

    public JSONArray getStockKLine(String code, String period, int days) {
        return getStockKLine(code, period, days, "qfq");
    }

    public JSONArray getStockKLine(String code, String period, int days, String adjust) {
        String adj = (adjust == null || adjust.isEmpty()) ? "qfq" : adjust;
        String key = "kline:" + code + ":" + period + ":" + days + ":" + adj;
        String path = "/api/stock/" + code + "/kline?period=" + period + "&days=" + days + "&adjust=" + adj;
        return cachedArr(key, path, 120);
    }

    /** Strategies with a v2 → legacy fallback chain. */
    public JSONObject getStockStrategies(String code) {
        return getStockStrategies(code, null);
    }

    /** Strategies with optional user weights. Custom configs bypass cache. */
    public JSONObject getStockStrategies(String code, JSONObject strategyConfig) {
        if (strategyConfig != null && !strategyConfig.isEmpty()) {
            JSONObject body = new JSONObject();
            body.put("strategies", strategyConfig);
            try {
                String resp = restTemplate.postForObject(
                        dataServiceUrl + "/api/v2/stock/" + code + "/score", body, String.class);
                DataTimeHolder.recordOldest(System.currentTimeMillis());
                return resp == null ? null : JSON.parseObject(resp);
            } catch (Exception ignored) {
                // fall through to cached default chain
            }
        }
        return getCachedJsonObject("strategies:v2:" + code, () -> {
            try {
                String resp = restTemplate.getForObject(
                        dataServiceUrl + "/api/v2/stock/" + code + "/score", String.class);
                if (resp != null && !resp.isEmpty()) return resp;
            } catch (Exception ignored) {}
            return restTemplate.getForObject(
                    dataServiceUrl + "/api/stock/" + code + "/strategies", String.class);
        }, 120);
    }

    public JSONArray searchStock(String keyword) {
        return getArrNoCache("/api/stock/search?keyword=" + keyword);
    }

    // =====================================================================
    // Screener / strategies meta
    // =====================================================================

    public JSONArray  getStrategiesMeta()       { return cachedArr("strategies:meta", "/api/v2/strategies", 600); }
    public JSONArray  getConditionFields()      { return cachedArr("conditions:fields", "/api/v2/condition-fields", 3600); }
    public JSONObject getExpressionHelp()       { return cached("expression:help", "/api/v2/expression/help", 3600); }
    public JSONObject getStrategyTops(int limit) {
        // Pre-computed (code, strategy) scores read from MySQL. Refreshed by
        // the post-market scheduler — caching 5 min on top keeps response
        // sub-millisecond for the dashboard's repeated polls.
        return cached("strategy-tops:" + limit, "/api/v2/strategy-tops?limit=" + limit, 120);
    }
    public JSONArray  runConditionScreener(JSONObject body) { return postArr("/api/v2/screen/conditions", body); }

    public Object runExpressionScreener(JSONObject body) {
        String resp = restTemplate.postForObject(dataServiceUrl + "/api/v2/screen/expression", body, String.class);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return JSON.parse(resp);
    }

    public JSONObject validateExpression(JSONObject body) {
        try {
            return postObj("/api/v2/screen/expression/validate", body);
        } catch (HttpClientErrorException e) {
            // 4xx returns a structured error body — surface it to the caller verbatim.
            return JSON.parseObject(e.getResponseBodyAsString());
        }
    }

    /**
     * Composite screener. Tries v2 first; falls back to legacy only when v2
     * actually errors (network failure, error envelope, parse failure).
     *
     * <p>An <b>empty</b> result from v2 is treated as success — it means
     * the user's filters legitimately matched nothing (e.g. requireTriggered
     * AND-filter is strict). Older versions fell back to legacy on empty,
     * which silently dropped requireTriggered / strategyParams because the
     * legacy endpoint doesn't understand those keys.
     */
    public JSONArray getScreener(JSONObject request) {
        try {
            String resp = restTemplate.postForObject(
                    dataServiceUrl + "/api/v2/screen", request, String.class);
            if (resp != null && !resp.startsWith("{\"error\"")) {
                JSONArray arr = JSON.parseArray(resp);
                if (arr != null) {
                    DataTimeHolder.recordOldest(System.currentTimeMillis());
                    return arr;
                }
            }
        } catch (Exception ignored) {
            // v2 actually broke — legacy may still answer.
        }
        return postArr("/api/screen", request);
    }

    public JSONObject runBacktest(JSONObject request) { return postObj("/api/backtest", request); }

    // =====================================================================
    // LHB
    // =====================================================================

    public JSONArray getLhbRecent(int days, String code) {
        String key = "lhb:recent:" + days + ":" + (code == null ? "" : code);
        String path = "/api/lhb/recent?days=" + days + (code != null && !code.isEmpty() ? "&code=" + code : "");
        return cachedArr(key, path, 120);
    }
    public JSONArray getLhbInstitutionRank(int days) { return cachedArr("lhb:inst:" + days, "/api/lhb/institution-rank?days=" + days, 120); }
    public JSONArray getLhbStockRank(int days)       { return cachedArr("lhb:stock:" + days, "/api/lhb/stock-rank?days=" + days, 120); }

    // =====================================================================
    // Money flow
    // =====================================================================

    public JSONArray getMoneyFlowMainRank(int days, int limit, String direction) {
        String key = "mf:main:" + days + ":" + limit + ":" + direction;
        String path = "/api/moneyflow/main-rank?days=" + days + "&limit=" + limit + "&direction=" + direction;
        return cachedArr(key, path, 60);
    }
    public JSONArray getMoneyFlowNorthboundRank(int days, int limit) {
        return cachedArr("mf:nb:" + days + ":" + limit,
                "/api/moneyflow/northbound-rank?days=" + days + "&limit=" + limit, 120);
    }
    public JSONArray getMoneyFlowSector()                     { return cachedArr("mf:sector", "/api/moneyflow/sector", 60); }
    public JSONArray getMoneyFlowStock(String code, int days) { return cachedArr("mf:stock:" + code + ":" + days, "/api/moneyflow/stock/" + code + "?days=" + days, 120); }

    // =====================================================================
    // Admin (never cached — callers want real-time state)
    // =====================================================================

    public JSONObject getAdminHealthDetail()          { return getObjNoCache("/api/admin/health-detail"); }
    public JSONObject adminCacheClear(String pattern) { return postObj("/api/admin/cache/clear" + qs("pattern", pattern), null); }
    public JSONObject adminWarmupStart(String job)    { return postObj("/api/admin/warmup" + qs("job", job), null); }
    public JSONObject getAdminWarmupStatus(String id) { return getObjNoCache("/api/admin/warmup/status" + qs("id", id)); }
    public JSONObject getAdminSchedulerJobs()         { return getObjNoCache("/api/admin/scheduler/jobs"); }

    // =====================================================================
    // Helpers
    // =====================================================================

    /** GET, parsed as JSONObject, with full L1 + L2 + single-flight caching. */
    private JSONObject cached(String key, String path, int ttlSeconds) {
        return getCachedJsonObject(key, () -> restTemplate.getForObject(dataServiceUrl + path, String.class), ttlSeconds);
    }

    /** GET, parsed as JSONArray, with full L1 + L2 + single-flight caching. */
    private JSONArray cachedArr(String key, String path, int ttlSeconds) {
        return getCachedJsonArray(key, () -> restTemplate.getForObject(dataServiceUrl + path, String.class), ttlSeconds);
    }

    /** POST without caching — used for user-submitted bodies. Records dataTime. */
    private JSONObject postObj(String path, Object body) {
        String resp = restTemplate.postForObject(dataServiceUrl + path, body, String.class);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return resp == null ? null : JSON.parseObject(resp);
    }

    private JSONArray postArr(String path, Object body) {
        String resp = restTemplate.postForObject(dataServiceUrl + path, body, String.class);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return resp == null ? null : JSON.parseArray(resp);
    }

    /** GET without caching — used for admin / real-time endpoints. No dataTime side effect. */
    private JSONObject getObjNoCache(String path) {
        String resp = restTemplate.getForObject(dataServiceUrl + path, String.class);
        return resp == null ? null : JSON.parseObject(resp);
    }

    private JSONArray getArrNoCache(String path) {
        String resp = restTemplate.getForObject(dataServiceUrl + path, String.class);
        DataTimeHolder.recordOldest(System.currentTimeMillis());
        return resp == null ? null : JSON.parseArray(resp);
    }

    /** Build "?k=v" or "" — handy for optional query params. */
    private static String qs(String key, String value) {
        return (value == null || value.isEmpty()) ? "" : "?" + key + "=" + value;
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

        // L1: in-process cache (15s). Most requests stop here.
        CachedEntry l1Hit = l1.getIfPresent(cacheKey);
        if (l1Hit != null && l1Hit.getJson() != null) {
            DataTimeHolder.recordOldest(l1Hit.getWrittenAt());
            return l1Hit.getJson();
        }

        // L2: Redis (per-key TTL).
        try {
            Object cached = redisTemplate.opsForValue().get(cacheKey);
            if (cached instanceof CachedEntry entry && entry.getJson() != null) {
                DataTimeHolder.recordOldest(entry.getWrittenAt());
                l1.put(cacheKey, entry);
                return entry.getJson();
            }
        } catch (Exception ignored) {}

        // Origin fetch — serialize concurrent callers on the same key so a
        // miss can't fan out N identical data-service calls. The lock is
        // held only for the fetch duration; the per-key object is reused
        // across requests (interned via computeIfAbsent).
        Object lock = keyLocks.computeIfAbsent(cacheKey, k -> new Object());
        synchronized (lock) {
            // Double-check: another thread may have just populated either cache.
            CachedEntry l1Recheck = l1.getIfPresent(cacheKey);
            if (l1Recheck != null && l1Recheck.getJson() != null) {
                DataTimeHolder.recordOldest(l1Recheck.getWrittenAt());
                return l1Recheck.getJson();
            }
            try {
                Object cached = redisTemplate.opsForValue().get(cacheKey);
                if (cached instanceof CachedEntry entry && entry.getJson() != null) {
                    DataTimeHolder.recordOldest(entry.getWrittenAt());
                    l1.put(cacheKey, entry);
                    return entry.getJson();
                }
            } catch (Exception ignored) {}

            String raw = fetcher.get();
            long now = System.currentTimeMillis();
            DataTimeHolder.recordOldest(now);
            if (raw != null) {
                CachedEntry entry = new CachedEntry(raw, now);
                l1.put(cacheKey, entry);
                try {
                    redisTemplate.opsForValue().set(cacheKey, entry, ttlSeconds, TimeUnit.SECONDS);
                } catch (Exception ignored) {}
            }
            return raw;
        }
    }
}

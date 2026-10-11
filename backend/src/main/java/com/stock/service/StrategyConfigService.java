package com.stock.service;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import jakarta.annotation.PostConstruct;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.*;

/** Per-user weights with optimistic revisions; never copies one user's settings to another. */
@Service
public class StrategyConfigService {
    public static final String DDL = """
        CREATE TABLE IF NOT EXISTS user_strategy_config (
            user_id BIGINT NOT NULL PRIMARY KEY,
            version BIGINT NOT NULL DEFAULT 1,
            config_json JSON NOT NULL,
            updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """;
    private final JdbcTemplate jdbc;

    public StrategyConfigService(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @PostConstruct
    public void ensureSchema() { jdbc.execute(DDL); }

    public Map<String, Object> get(long userId) {
        List<Map<String, Object>> rows = jdbc.query(
            "SELECT version, config_json, updated_at FROM user_strategy_config WHERE user_id=?",
            (rs, n) -> {
                JSONObject json = JSON.parseObject(rs.getString("config_json"));
                Map<String, Object> out = new LinkedHashMap<>(json);
                out.put("version", rs.getLong("version"));
                out.put("updatedAt", rs.getTimestamp("updated_at").toInstant().toString());
                return out;
            }, userId);
        if (!rows.isEmpty()) return rows.get(0);
        Map<String, Object> empty = new LinkedHashMap<>();
        empty.put("version", 0L); empty.put("config", null);
        empty.put("presets", List.of()); empty.put("updatedAt", null);
        return empty;
    }

    public Map<String, Object> save(long userId, Map<String, Object> body) {
        Object rawVersion = body.get("version");
        if (!(rawVersion instanceof Number v) || !Double.isFinite(v.doubleValue()) || v.doubleValue() < 0
                || v.doubleValue() != Math.rint(v.doubleValue()) || v.doubleValue() > 9_007_199_254_740_990L)
            throw new BusinessException("缺少有效的配置版本");
        long version = ((Number) rawVersion).longValue();
        String json = JSON.toJSONString(normalize(body));
        if (json.length() > 128_000) throw new BusinessException("策略配置过大");
        int changed;
        try {
            if (version == 0) {
                changed = jdbc.update("INSERT INTO user_strategy_config(user_id,version,config_json) VALUES (?,1,?)", userId, json);
            } else {
                changed = jdbc.update("UPDATE user_strategy_config SET config_json=?,version=version+1 WHERE user_id=? AND version=?",
                                      json, userId, version);
            }
        } catch (DuplicateKeyException e) {
            throw conflict();
        }
        if (changed != 1) throw conflict();
        // Return this exact revision, not a subsequent writer's revision from a second SELECT.
        Map<String, Object> result = new LinkedHashMap<>(JSON.parseObject(json));
        result.put("version", version + 1);
        result.put("updatedAt", java.time.Instant.now().toString());
        return result;
    }

    private BusinessException conflict() {
        return new BusinessException(409, "云端配置已在其他设备更新，本地改动已保留；请加载云端后重新调整");
    }

    static Map<String, Object> normalize(Map<String, Object> body) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("config", normalizeWeights(body.get("config")));
        Object rawPresets = body.getOrDefault("presets", List.of());
        if (!(rawPresets instanceof List<?> presets) || presets.size() > 20)
            throw new BusinessException("最多保存20个策略方案");
        List<Map<String, Object>> cleaned = new ArrayList<>();
        Set<String> names = new HashSet<>();
        for (Object item : presets) {
            if (!(item instanceof Map<?, ?> preset) || !(preset.get("name") instanceof String name)
                    || name.isBlank() || name.trim().length() > 80 || !names.add(name.trim()))
                throw new BusinessException("方案名称须唯一且为1至80个字符");
            cleaned.add(Map.of("name", name.trim(), "config", normalizeWeights(preset.get("config"))));
        }
        out.put("presets", cleaned);
        return out;
    }

    static Map<String, Object> normalizeWeights(Object raw) {
        if (!(raw instanceof Map<?, ?> weights) || weights.size() > 200)
            throw new BusinessException("权重配置格式错误");
        Map<String, Object> result = new LinkedHashMap<>();
        for (var entry : weights.entrySet()) {
            if (!(entry.getKey() instanceof String id) || !id.matches("[a-z][a-z0-9_]{0,79}")
                    || !(entry.getValue() instanceof Map<?, ?> row) || !(row.get("enabled") instanceof Boolean enabled)
                    || !(row.get("weight") instanceof Number number))
                throw new BusinessException("策略标识、启用状态或权重格式错误");
            double weight = ((Number) ((Map<?, ?>) entry.getValue()).get("weight")).doubleValue();
            if (!Double.isFinite(weight) || weight < 0 || weight > 1000)
                throw new BusinessException("权重必须在0至1000之间");
            result.put(id, Map.of("enabled", enabled, "weight", weight));
        }
        return result;
    }
}

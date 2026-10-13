package com.stock.model.dto;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;

import java.util.Map;

/** One presentation contract for synchronous and asynchronous backtests.
 * Raw engine fields remain available for audit/export; the aliases only adapt
 * the existing UI contract. Missing or non-finite metrics are never invented as 0.
 */
public final class BacktestResultMapper {

    private BacktestResultMapper() {}

    private static final Map<String, String> METRICS = Map.ofEntries(
            Map.entry("total_return", "totalReturn"),
            Map.entry("annualized_return", "annualizedReturn"),
            Map.entry("max_drawdown", "maxDrawdown"),
            Map.entry("sharpe_ratio", "sharpeRatio"),
            Map.entry("calmar_ratio", "calmarRatio"),
            Map.entry("win_rate", "winRate"),
            Map.entry("trade_count", "tradeCount"),
            Map.entry("benchmark_return", "benchmarkReturn"),
            Map.entry("excess_return", "excessReturn"),
            Map.entry("turnover_rate", "turnoverRate"),
            Map.entry("total_costs", "totalCosts")
    );

    private static final Map<String, String> FIELDS = Map.ofEntries(
            Map.entry("strategy_id", "strategyId"),
            Map.entry("initial_capital", "initialCapital"),
            Map.entry("top_n", "topN"),
            Map.entry("equity_curve", "equityCurve"),
            Map.entry("benchmark_curve", "benchmarkCurve"),
            Map.entry("signal_log", "signalLog")
    );

    /** Business failure must be checked before rendering a completed job. */
    public static void requireSuccess(JSONObject data) {
        if (data != null && data.get("error") != null) {
            throw new BusinessException("回测失败: " + data.getString("error"));
        }
    }

    public static JSONObject toView(JSONObject data) {
        if (data == null) throw new IllegalArgumentException("回测结果为空");
        // Preserve status/error_kind/sample_info/engine_version and future engine
        // metadata, plus run_single's code, mode and daily signal log.
        JSONObject view = new JSONObject(data);
        if (data.get("error") != null) return view;
        JSONObject metrics = data.getJSONObject("metrics");
        for (var field : METRICS.entrySet()) {
            Number value = finiteNumber(metrics == null ? null : metrics.get(field.getKey()));
            // The existing UI expects drawdown magnitude; retain the signed raw
            // value in metrics rather than changing the engine's evidence.
            if ("max_drawdown".equals(field.getKey()) && value != null) {
                value = Math.abs(value.doubleValue());
            }
            view.put(field.getValue(), value);
        }
        for (var field : FIELDS.entrySet()) {
            view.put(field.getValue(), data.get(field.getKey()));
        }
        return view;
    }

    private static Number finiteNumber(Object value) {
        return value instanceof Number number && Double.isFinite(number.doubleValue()) ? number : null;
    }
}

package com.stock.model.dto;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BacktestResultMapperTest {

    @Test void absentAndInvalidMetricsStayNullButRealZeroSurvives() {
        JSONObject metrics = new JSONObject();
        metrics.put("total_return", 0);
        metrics.put("sharpe_ratio", Double.NaN);
        metrics.put("calmar_ratio", Double.POSITIVE_INFINITY);
        metrics.put("win_rate", "0.5");
        metrics.put("max_drawdown", null);
        JSONObject source = new JSONObject();
        source.put("metrics", metrics);

        JSONObject view = BacktestResultMapper.toView(source);
        assertEquals(0, view.get("totalReturn"));
        for (String key : new String[]{"annualizedReturn", "sharpeRatio", "calmarRatio",
                "winRate", "maxDrawdown", "tradeCount", "benchmarkReturn", "totalCosts"}) {
            assertTrue(view.containsKey(key), key);
            assertNull(view.get(key), key);
        }
    }

    @Test void noMetricsObjectDoesNotCreateZeroPerformance() {
        JSONObject view = BacktestResultMapper.toView(JSON.parseObject("{\"status\":\"INSUFFICIENT_DATA\"}"));
        assertNull(view.get("totalReturn"));
        assertNull(view.get("maxDrawdown"));
        assertEquals("INSUFFICIENT_DATA", view.getString("status"));
    }

    @Test void keepsRawEvidenceAndSingleStockMetadataWithoutMutation() {
        JSONObject source = JSON.parseObject("""
                {"mode":"single","code":"600519","strategy_id":"quality_factor",
                 "start":"2026-01-01","end":"2026-09-30","initial_capital":1000000,
                 "engine_version":"v3","status":"VALID","sample_info":{"periods":150},
                 "metrics":{"max_drawdown":-0.12,"trade_count":0},
                 "signal_log":[{"date":"2026-01-02","score":0}],
                 "equity_curve":[{"date":"2026-01-02","value":1000000}],
                 "trades":[],"picks":["600519"],"costs":{"slippage":0.001}}
                """);
        JSONObject before = JSON.parseObject(source.toJSONString());
        JSONObject view = BacktestResultMapper.toView(source);
        assertEquals(before, source);
        assertEquals("single", view.getString("mode"));
        assertEquals("600519", view.getString("code"));
        assertEquals("quality_factor", view.getString("strategyId"));
        assertEquals("v3", view.getString("engine_version"));
        assertEquals(source.get("sample_info"), view.get("sample_info"));
        assertEquals(source.get("signal_log"), view.get("signalLog"));
        assertEquals(source.get("signal_log"), view.get("signal_log"));
        assertEquals(source.get("equity_curve"), view.get("equityCurve"));
        assertEquals(0.12, view.getDoubleValue("maxDrawdown"), 1e-12);
        assertEquals(-0.12, source.getJSONObject("metrics").getDoubleValue("max_drawdown"), 1e-12);
        assertEquals(0, view.get("tradeCount"));
    }

    @Test void errorPayloadIsRetainedAndSuccessGuardRejectsIt() {
        JSONObject error = JSON.parseObject("""
                {"error":"缺少历史市值","error_kind":"coverage","status":"FAILED",
                 "sample_info":{"periods":0}}
                """);
        assertEquals(error, BacktestResultMapper.toView(error));
        BusinessException failure = assertThrows(BusinessException.class,
                () -> BacktestResultMapper.requireSuccess(error));
        assertEquals("回测失败: 缺少历史市值", failure.getMessage());
        JSONObject success = new JSONObject();
        success.put("error", null);
        assertDoesNotThrow(() -> BacktestResultMapper.requireSuccess(success));
    }
}

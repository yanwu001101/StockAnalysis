package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

/**
 * Alpha lab pass-through: user-defined cross-sectional factor expressions
 * (WorldQuant-BRAIN style) — statistical testing + portfolio backtest.
 * Research payload stays snake_case; expression errors come back in-body
 * with HTTP 200 so the front-end can render the exact reason.
 */
@RestController
@RequestMapping("/api/alphalab")
public class AlphaLabController {

    private final DataService dataService;

    public AlphaLabController(DataService dataService) {
        this.dataService = dataService;
    }

    @PostMapping("/factorlab")
    public ApiResponse<?> factorlab(@RequestBody JSONObject body) {
        JSONObject data = dataService.runAlphaFactorLab(body);
        if (data == null) throw new BusinessException("因子检验无数据");
        return ApiResponse.ok(data);
    }

    @PostMapping("/backtest")
    public ApiResponse<?> backtest(@RequestBody JSONObject body) {
        JSONObject data = dataService.runAlphaBacktest(body);
        if (data == null) throw new BusinessException("因子回测无数据");
        if (data.containsKey("error")) {
            throw new BusinessException("因子回测失败: " + data.getString("error"));
        }

        // 与 BacktestController 相同的 snake_case -> camelCase 扁平化，
        // 前端两个回测面板共用同一套结果类型与渲染。
        JSONObject view = new JSONObject();
        JSONObject m = data.getJSONObject("metrics");
        if (m != null) {
            view.put("totalReturn", m.getOrDefault("total_return", 0));
            view.put("annualizedReturn", m.getOrDefault("annualized_return", 0));
            double dd = m.getDoubleValue("max_drawdown");
            view.put("maxDrawdown", Math.abs(dd));
            view.put("sharpeRatio", m.getOrDefault("sharpe_ratio", 0));
            view.put("calmarRatio", m.getOrDefault("calmar_ratio", 0));
            view.put("winRate", m.getOrDefault("win_rate", 0));
            view.put("tradeCount", m.getOrDefault("trade_count", 0));
            if (m.containsKey("benchmark_return")) view.put("benchmarkReturn", m.get("benchmark_return"));
            if (m.containsKey("excess_return")) view.put("excessReturn", m.get("excess_return"));
            if (m.containsKey("turnover_rate")) view.put("turnoverRate", m.get("turnover_rate"));
            if (m.containsKey("total_costs")) view.put("totalCosts", m.get("total_costs"));
        }
        view.put("equityCurve", data.getJSONArray("equity_curve"));
        view.put("trades", data.getJSONArray("trades"));
        view.put("picks", data.getJSONArray("picks"));
        view.put("mode", data.getString("mode"));
        view.put("expression", data.getString("expression"));
        view.put("start", data.getString("start"));
        view.put("end", data.getString("end"));
        view.put("initialCapital", data.get("initial_capital"));
        view.put("topN", data.get("top_n"));
        view.put("rebalance", data.getString("rebalance"));
        view.put("benchmarkCurve", data.getJSONArray("benchmark_curve"));
        view.put("costs", data.getJSONObject("costs"));
        return ApiResponse.ok(view);
    }

    @GetMapping("/help")
    public ApiResponse<?> help() {
        JSONObject data = dataService.getAlphaHelp();
        if (data == null) throw new BusinessException("帮助数据为空");
        return ApiResponse.ok(data);
    }
}

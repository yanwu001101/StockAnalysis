package com.stock.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.model.dto.BacktestRequest;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

/**
 * Backtest pass-through to the Python data-service.
 *
 * The data-service returns a snake_case shape with `metrics` nested
 * ({total_return, annualized_return, ...}). The front-end's `BacktestResult`
 * type is flat + camelCase ({totalReturn, annualizedReturn, equityCurve, ...}),
 * so we flatten here.
 */
@RestController
@RequestMapping("/api")
public class BacktestController {

    private final DataService dataService;

    public BacktestController(DataService dataService) {
        this.dataService = dataService;
    }

    @PostMapping("/backtest")
    public ApiResponse<?> backtest(@RequestBody BacktestRequest request) {
        JSONObject json = (JSONObject) JSON.toJSON(request);
        JSONObject data = dataService.runBacktest(json);
        if (data == null) throw new BusinessException("回测无数据");
        if (data.containsKey("error")) {
            throw new BusinessException("回测失败: " + data.getString("error"));
        }

        JSONObject view = new JSONObject();
        JSONObject m = data.getJSONObject("metrics");
        if (m != null) {
            view.put("totalReturn", m.getOrDefault("total_return", 0));
            view.put("annualizedReturn", m.getOrDefault("annualized_return", 0));
            // Front-end renders with a leading "-", expects a positive magnitude.
            double dd = m.getDoubleValue("max_drawdown");
            view.put("maxDrawdown", Math.abs(dd));
            view.put("sharpeRatio", m.getOrDefault("sharpe_ratio", 0));
            view.put("calmarRatio", m.getOrDefault("calmar_ratio", 0));
            view.put("winRate", m.getOrDefault("win_rate", 0));
            view.put("tradeCount", m.getOrDefault("trade_count", 0));
        }
        view.put("equityCurve", data.getJSONArray("equity_curve"));
        view.put("trades", data.getJSONArray("trades"));
        view.put("picks", data.getJSONArray("picks"));
        view.put("strategyId", data.getString("strategy_id"));
        view.put("start", data.getString("start"));
        view.put("end", data.getString("end"));
        view.put("initialCapital", data.get("initial_capital"));
        view.put("topN", data.get("top_n"));
        view.put("rebalance", data.getString("rebalance"));
        return ApiResponse.ok(view);
    }
}

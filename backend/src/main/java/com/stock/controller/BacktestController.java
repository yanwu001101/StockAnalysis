package com.stock.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.model.dto.BacktestRequest;
import com.stock.model.dto.BacktestResultMapper;
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
        BacktestResultMapper.requireSuccess(data);
        return ApiResponse.ok(BacktestResultMapper.toView(data));
    }
}

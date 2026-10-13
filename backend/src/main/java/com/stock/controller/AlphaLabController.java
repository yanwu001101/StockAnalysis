package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.model.dto.BacktestResultMapper;
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
        BacktestResultMapper.requireSuccess(data);
        return ApiResponse.ok(BacktestResultMapper.toView(data));
    }

    @GetMapping("/help")
    public ApiResponse<?> help() {
        JSONObject data = dataService.getAlphaHelp();
        if (data == null) throw new BusinessException("帮助数据为空");
        return ApiResponse.ok(data);
    }
}

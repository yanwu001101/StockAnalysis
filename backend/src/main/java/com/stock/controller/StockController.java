package com.stock.controller;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/stock")
public class StockController {

    private final DataService dataService;

    public StockController(DataService dataService) {
        this.dataService = dataService;
    }

    @GetMapping("/{code}")
    public ApiResponse<?> detail(@PathVariable String code) {
        JSONObject data = dataService.getStockDetail(code);
        return ApiResponse.ok(data);
    }

    @GetMapping("/{code}/kline")
    public ApiResponse<?> kline(@PathVariable String code,
                                @RequestParam(defaultValue = "daily") String period,
                                @RequestParam(defaultValue = "250") int days,
                                @RequestParam(defaultValue = "qfq") String adjust) {
        JSONArray data = dataService.getStockKLine(code, period, days, adjust);
        return ApiResponse.ok(data);
    }

    @GetMapping("/{code}/strategies")
    public ApiResponse<?> strategies(@PathVariable String code) {
        JSONObject data = dataService.getStockStrategies(code);
        return ApiResponse.ok(data);
    }

    @GetMapping("/{code}/f10")
    public ApiResponse<?> f10(@PathVariable String code) {
        JSONObject data = dataService.getStockF10(code);
        return ApiResponse.ok(data);
    }

    @GetMapping("/{code}/financials")
    public ApiResponse<?> financials(@PathVariable String code) {
        JSONObject data = dataService.getStockFinancials(code);
        return ApiResponse.ok(data);
    }

    /** 批量策略分:盘面高分表一次拿完,替掉逐只 /{code}/strategies 的 N+1。 */
    @PostMapping("/strategies/batch")
    public ApiResponse<?> strategiesBatch(@RequestBody JSONObject body) {
        return ApiResponse.ok(dataService.strategiesBatch(body));
    }

    @GetMapping("/{code}/prediction")
    public ApiResponse<?> prediction(@PathVariable String code) {
        JSONObject data = dataService.getStockPrediction(code);
        return ApiResponse.ok(data);
    }

    @GetMapping("/{code}/pro-signal")
    public ApiResponse<?> proSignal(@PathVariable String code) {
        JSONObject data = dataService.getStockProSignal(code);
        return ApiResponse.ok(data);
    }

    @GetMapping("/search")
    public ApiResponse<?> search(@RequestParam String keyword) {
        JSONArray data = dataService.searchStock(keyword);
        return ApiResponse.ok(data);
    }
}

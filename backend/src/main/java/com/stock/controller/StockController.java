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
        try {
            JSONObject data = dataService.getStockDetail(code);
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("获取个股详情失败: " + e.getMessage());
        }
    }

    @GetMapping("/{code}/kline")
    public ApiResponse<?> kline(@PathVariable String code,
                                @RequestParam(defaultValue = "daily") String period,
                                @RequestParam(defaultValue = "250") int days) {
        try {
            JSONArray data = dataService.getStockKLine(code, period, days);
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("获取K线数据失败: " + e.getMessage());
        }
    }

    @GetMapping("/{code}/strategies")
    public ApiResponse<?> strategies(@PathVariable String code) {
        try {
            JSONObject data = dataService.getStockStrategies(code);
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("获取策略评分失败: " + e.getMessage());
        }
    }

    @GetMapping("/search")
    public ApiResponse<?> search(@RequestParam String keyword) {
        try {
            JSONArray data = dataService.searchStock(keyword);
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("搜索失败: " + e.getMessage());
        }
    }
}

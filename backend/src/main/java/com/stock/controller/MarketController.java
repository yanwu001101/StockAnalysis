package com.stock.controller;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/market")
public class MarketController {

    private final DataService dataService;

    public MarketController(DataService dataService) {
        this.dataService = dataService;
    }

    @GetMapping("/summary")
    public ApiResponse<?> summary() {
        try {
            JSONObject data = dataService.getMarketSummary();
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("获取市场数据失败: " + e.getMessage());
        }
    }

    @GetMapping("/top-stocks")
    public ApiResponse<?> topStocks(@RequestParam(defaultValue = "20") int limit) {
        try {
            JSONArray data = dataService.getTopStocks(limit);
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("获取Top股票失败: " + e.getMessage());
        }
    }

    @GetMapping("/sector-rotation")
    public ApiResponse<?> sectorRotation() {
        try {
            JSONArray data = dataService.getSectorRotation();
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("获取板块数据失败: " + e.getMessage());
        }
    }

    @GetMapping("/northbound-flow")
    public ApiResponse<?> northboundFlow(@RequestParam(defaultValue = "30") int days) {
        try {
            JSONArray data = dataService.getNorthboundFlow(days);
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("获取北向资金失败: " + e.getMessage());
        }
    }
}

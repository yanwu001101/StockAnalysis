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
        JSONObject data = dataService.getMarketSummary();
        return ApiResponse.ok(data);
    }

    @GetMapping("/top-stocks")
    public ApiResponse<?> topStocks(@RequestParam(defaultValue = "20") int limit) {
        JSONArray data = dataService.getTopStocks(limit);
        return ApiResponse.ok(data);
    }

    @GetMapping("/sector-rotation")
    public ApiResponse<?> sectorRotation() {
        JSONArray data = dataService.getSectorRotation();
        return ApiResponse.ok(data);
    }

    @GetMapping("/northbound-flow")
    public ApiResponse<?> northboundFlow(@RequestParam(defaultValue = "30") int days) {
        JSONArray data = dataService.getNorthboundFlow(days);
        return ApiResponse.ok(data);
    }

    @GetMapping("/indices")
    public ApiResponse<?> indices() {
        return ApiResponse.ok(dataService.getIndices());
    }

    @GetMapping("/gainers")
    public ApiResponse<?> gainers(@RequestParam(defaultValue = "20") int limit) {
        return ApiResponse.ok(dataService.getGainers(limit));
    }

    @GetMapping("/losers")
    public ApiResponse<?> losers(@RequestParam(defaultValue = "20") int limit) {
        return ApiResponse.ok(dataService.getLosers(limit));
    }

    @GetMapping("/most-active")
    public ApiResponse<?> mostActive(@RequestParam(defaultValue = "20") int limit) {
        return ApiResponse.ok(dataService.getMostActive(limit));
    }
}

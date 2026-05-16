package com.stock.controller;

import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/moneyflow")
public class MoneyFlowController {

    private final DataService dataService;

    public MoneyFlowController(DataService dataService) {
        this.dataService = dataService;
    }

    @GetMapping("/main-rank")
    public ApiResponse<?> mainRank(@RequestParam(defaultValue = "5") int days,
                                    @RequestParam(defaultValue = "50") int limit,
                                    @RequestParam(defaultValue = "inflow") String direction) {
        try {
            return ApiResponse.ok(dataService.getMoneyFlowMainRank(days, limit, direction));
        } catch (Exception e) {
            return ApiResponse.error("获取主力资金榜失败: " + e.getMessage());
        }
    }

    @GetMapping("/northbound-rank")
    public ApiResponse<?> northboundRank(@RequestParam(defaultValue = "5") int days,
                                          @RequestParam(defaultValue = "50") int limit) {
        try {
            return ApiResponse.ok(dataService.getMoneyFlowNorthboundRank(days, limit));
        } catch (Exception e) {
            return ApiResponse.error("获取北向资金榜失败: " + e.getMessage());
        }
    }

    @GetMapping("/sector")
    public ApiResponse<?> sector() {
        try {
            return ApiResponse.ok(dataService.getMoneyFlowSector());
        } catch (Exception e) {
            return ApiResponse.error("获取板块资金失败: " + e.getMessage());
        }
    }

    @GetMapping("/stock/{code}")
    public ApiResponse<?> stockFlow(@PathVariable String code,
                                    @RequestParam(defaultValue = "60") int days) {
        try {
            return ApiResponse.ok(dataService.getMoneyFlowStock(code, days));
        } catch (Exception e) {
            return ApiResponse.error("获取个股资金流失败: " + e.getMessage());
        }
    }
}

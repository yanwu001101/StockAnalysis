package com.stock.controller;

import com.alibaba.fastjson2.JSONArray;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/lhb")
public class LhbController {

    private final DataService dataService;

    public LhbController(DataService dataService) {
        this.dataService = dataService;
    }

    @GetMapping("/recent")
    public ApiResponse<?> recent(@RequestParam(defaultValue = "30") int days,
                                  @RequestParam(required = false) String code) {
        try {
            return ApiResponse.ok(dataService.getLhbRecent(days, code));
        } catch (Exception e) {
            return ApiResponse.error("获取龙虎榜失败: " + e.getMessage());
        }
    }

    @GetMapping("/institution-rank")
    public ApiResponse<?> institutionRank(@RequestParam(defaultValue = "30") int days) {
        try {
            return ApiResponse.ok(dataService.getLhbInstitutionRank(days));
        } catch (Exception e) {
            return ApiResponse.error("获取机构榜失败: " + e.getMessage());
        }
    }

    @GetMapping("/stock-rank")
    public ApiResponse<?> stockRank(@RequestParam(defaultValue = "30") int days) {
        try {
            return ApiResponse.ok(dataService.getLhbStockRank(days));
        } catch (Exception e) {
            return ApiResponse.error("获取个股榜失败: " + e.getMessage());
        }
    }
}

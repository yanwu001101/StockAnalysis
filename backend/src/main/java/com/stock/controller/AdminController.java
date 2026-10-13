package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final DataService dataService;

    public AdminController(DataService dataService) {
        this.dataService = dataService;
    }

    @GetMapping("/health-detail")
    public ApiResponse<?> healthDetail() {
        return ApiResponse.ok(dataService.getAdminHealthDetail());
    }

    @PostMapping("/cache/clear")
    public ApiResponse<?> cacheClear(@RequestParam(required = false) String pattern) {
        return ApiResponse.ok(dataService.adminCacheClear(pattern));
    }

    @PostMapping("/warmup")
    public ApiResponse<?> warmup(@RequestParam(defaultValue = "postmarket") String job) {
        JSONObject data = dataService.adminWarmupStart(job);
        if (data == null) throw new BusinessException("任务提交失败");
        if (data.get("error") != null) throw jobRequestError(data);
        return ApiResponse.ok(data);
    }

    @GetMapping("/warmup/status")
    public ApiResponse<?> warmupStatus(@RequestParam(required = false) String id) {
        JSONObject data = dataService.getAdminWarmupStatus(id);
        if (data == null) throw new BusinessException("查询任务状态失败");
        // A failed/partial run is valid status data, not a failed HTTP request.
        if (data.get("upstream_status") != null && data.get("error") != null) throw jobRequestError(data);
        return ApiResponse.ok(data);
    }

    private static BusinessException jobRequestError(JSONObject data) {
        Integer status = data.getInteger("upstream_status");
        return new BusinessException(status == null ? 400 : status, data.getString("error"));
    }
}

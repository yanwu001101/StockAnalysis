package com.stock.controller;

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
        return ApiResponse.ok(dataService.adminWarmupStart(job));
    }

    @GetMapping("/warmup/status")
    public ApiResponse<?> warmupStatus(@RequestParam(required = false) String id) {
        return ApiResponse.ok(dataService.getAdminWarmupStatus(id));
    }
}

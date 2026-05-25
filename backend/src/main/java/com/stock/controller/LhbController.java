package com.stock.controller;

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
        return ApiResponse.ok(dataService.getLhbRecent(days, code));
    }

    @GetMapping("/institution-rank")
    public ApiResponse<?> institutionRank(@RequestParam(defaultValue = "30") int days) {
        return ApiResponse.ok(dataService.getLhbInstitutionRank(days));
    }

    @GetMapping("/stock-rank")
    public ApiResponse<?> stockRank(@RequestParam(defaultValue = "30") int days) {
        return ApiResponse.ok(dataService.getLhbStockRank(days));
    }
}

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
        return ApiResponse.ok(dataService.getMoneyFlowMainRank(days, limit, direction));
    }

    @GetMapping("/northbound-rank")
    public ApiResponse<?> northboundRank(@RequestParam(defaultValue = "5") int days,
                                          @RequestParam(defaultValue = "50") int limit) {
        return ApiResponse.ok(dataService.getMoneyFlowNorthboundRank(days, limit));
    }

    @GetMapping("/sector")
    public ApiResponse<?> sector() {
        return ApiResponse.ok(dataService.getMoneyFlowSector());
    }

    @GetMapping("/stock/{code}")
    public ApiResponse<?> stockFlow(@PathVariable String code,
                                    @RequestParam(defaultValue = "60") int days) {
        return ApiResponse.ok(dataService.getMoneyFlowStock(code, days));
    }
}

package com.stock.controller;

import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 短线做 T(日内 T+0)建议 — 透传 data-service /api/t。
 *
 *   GET  /api/t/stock/{code}   单只做 T 建议
 *   POST /api/t/batch          批量(自选/持仓){"codes": [...]}
 */
@RestController
@RequestMapping("/api/t")
public class TController {

    private final DataService dataService;

    public TController(DataService dataService) {
        this.dataService = dataService;
    }

    @GetMapping("/stock/{code}")
    public ApiResponse<?> stock(@PathVariable String code) {
        return ApiResponse.ok(dataService.getTSignal(code));
    }

    @PostMapping("/batch")
    public ApiResponse<?> batch(@RequestBody Map<String, Object> body) {
        List<String> codes = new ArrayList<>();
        Object raw = body == null ? null : body.get("codes");
        if (raw instanceof List<?>) {
            for (Object c : (List<?>) raw) {
                if (c != null) codes.add(String.valueOf(c));
            }
        }
        return ApiResponse.ok(dataService.getTSignalBatch(codes));
    }
}

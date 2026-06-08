package com.stock.controller;

import com.stock.model.dto.ApiResponse;
import com.stock.service.PortfolioService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.util.Map;

@RestController
@RequestMapping("/api/portfolio")
public class PortfolioController {

    private final PortfolioService portfolioService;

    public PortfolioController(PortfolioService portfolioService) {
        this.portfolioService = portfolioService;
    }

    @GetMapping("/positions")
    public ApiResponse<?> positions(HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(portfolioService.list(userId));
    }

    @PostMapping("/positions")
    public ApiResponse<?> savePosition(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(portfolioService.upsert(userId, body));
    }

    @PostMapping("/import-text")
    public ApiResponse<?> importText(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(portfolioService.importText(userId, body));
    }

    @DeleteMapping("/positions/{id}")
    public ApiResponse<?> deletePosition(@PathVariable Long id, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        portfolioService.delete(userId, id);
        return ApiResponse.ok("deleted");
    }

    @GetMapping("/advice")
    public ApiResponse<?> advice(@RequestParam(defaultValue = "0") BigDecimal cash,
                                 @RequestParam(defaultValue = "balanced") String mode,
                                 HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(portfolioService.advice(userId, cash, mode));
    }

    @PostMapping("/advice")
    public ApiResponse<?> advicePost(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        BigDecimal cash = new BigDecimal(String.valueOf(body.getOrDefault("cash", "0")));
        String mode = String.valueOf(body.getOrDefault("mode", "balanced"));
        Object strategyConfig = body.get("strategyConfig");
        return ApiResponse.ok(portfolioService.advice(userId, cash, mode, strategyConfig));
    }

    @GetMapping("/sync/ths/status")
    public ApiResponse<?> thsSyncStatus(HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(portfolioService.thsSyncStatus());
    }

    private Long userId(HttpServletRequest request) {
        return (Long) request.getAttribute("userId");
    }
}

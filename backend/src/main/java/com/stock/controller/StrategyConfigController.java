package com.stock.controller;

import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.service.StrategyConfigService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api/user/strategy-config")
public class StrategyConfigController {
    private final StrategyConfigService service;
    public StrategyConfigController(StrategyConfigService service) { this.service = service; }
    private long user(HttpServletRequest request) {
        Object id = request.getAttribute("userId");
        if (!(id instanceof Long)) throw new BusinessException(401, "未登录");
        return (Long) id;
    }
    @GetMapping
    public ApiResponse<?> get(HttpServletRequest request) { return ApiResponse.ok(service.get(user(request))); }
    @PutMapping
    public ApiResponse<?> put(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        return ApiResponse.ok(service.save(user(request), body));
    }
}

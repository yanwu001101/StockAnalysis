package com.stock.controller;

import com.stock.model.dto.ApiResponse;
import com.stock.service.AiAnalysisService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/ai")
public class AiAnalysisController {

    private final AiAnalysisService aiAnalysisService;

    public AiAnalysisController(AiAnalysisService aiAnalysisService) {
        this.aiAnalysisService = aiAnalysisService;
    }

    @GetMapping("/presets")
    public ApiResponse<?> presets() {
        return ApiResponse.ok(aiAnalysisService.presets());
    }

    @GetMapping("/config")
    public ApiResponse<?> getConfig(HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiAnalysisService.getConfig(userId));
    }

    @PostMapping("/config")
    public ApiResponse<?> saveConfig(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiAnalysisService.saveConfig(userId, body));
    }

    @PostMapping("/test")
    public ApiResponse<?> test(HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiAnalysisService.testConfig(userId));
    }

    @PostMapping("/analyze/portfolio")
    public ApiResponse<?> analyzePortfolio(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiAnalysisService.analyzePortfolio(userId, body));
    }

    @GetMapping("/history")
    public ApiResponse<?> history(HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiAnalysisService.history(userId));
    }

    @PostMapping("/history/{id}/feedback")
    public ApiResponse<?> feedback(@PathVariable Long id,
                                   @RequestBody Map<String, Object> body,
                                   HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiAnalysisService.feedback(userId, id, body));
    }

    private Long userId(HttpServletRequest request) {
        return (Long) request.getAttribute("userId");
    }
}

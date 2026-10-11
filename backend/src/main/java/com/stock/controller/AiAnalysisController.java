package com.stock.controller;

import com.stock.model.dto.ApiResponse;
import com.stock.service.AiAnalysisService;
import com.stock.service.AiChatService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/ai")
public class AiAnalysisController {

    private final AiAnalysisService aiAnalysisService;
    private final AiChatService aiChatService;

    public AiAnalysisController(AiAnalysisService aiAnalysisService, AiChatService aiChatService) {
        this.aiAnalysisService = aiAnalysisService;
        this.aiChatService = aiChatService;
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

    // =====================================================================
    // AI 多轮对话（专业金融顾问人设，见 AiChatService）
    // =====================================================================

    @PostMapping("/chat")
    public ApiResponse<?> chat(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        Long sessionId = body.get("sessionId") == null ? null
                : Long.valueOf(String.valueOf(body.get("sessionId")));
        String message = body.get("message") == null ? "" : String.valueOf(body.get("message"));
        return ApiResponse.ok(aiChatService.chat(userId, sessionId, message));
    }

    @GetMapping("/chat/sessions")
    public ApiResponse<?> chatSessions(HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiChatService.sessions(userId));
    }

    @GetMapping("/chat/sessions/{id}/messages")
    public ApiResponse<?> chatMessages(@PathVariable Long id, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiChatService.messages(userId, id));
    }

    @DeleteMapping("/chat/sessions/{id}")
    public ApiResponse<?> deleteChatSession(@PathVariable Long id, HttpServletRequest request) {
        Long userId = userId(request);
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(aiChatService.deleteSession(userId, id));
    }

    private Long userId(HttpServletRequest request) {
        return (Long) request.getAttribute("userId");
    }
}

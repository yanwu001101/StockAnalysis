package com.stock.controller.admin;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.stock.model.dto.ApiResponse;
import com.stock.service.admin.AdminUserService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/admin/users")
public class AdminUserController {

    private final AdminUserService service;

    public AdminUserController(AdminUserService service) {
        this.service = service;
    }

    @GetMapping
    public ApiResponse<IPage<Map<String, Object>>> page(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(required = false) String keyword,
        @RequestParam(required = false) String role,
        @RequestParam(required = false) Integer status) {
        return ApiResponse.ok(service.page(page, size, keyword, role, status));
    }

    @GetMapping("/stats")
    public ApiResponse<Map<String, Object>> stats() {
        return ApiResponse.ok(service.stats());
    }

    @PostMapping("/{id}/toggle-status")
    public ApiResponse<Map<String, Object>> toggleStatus(@PathVariable Long id, HttpServletRequest req) {
        return ApiResponse.ok(service.toggleStatus(id, req));
    }

    @PostMapping("/{id}/role")
    public ApiResponse<Map<String, Object>> setRole(@PathVariable Long id,
                                                    @RequestBody Map<String, String> body,
                                                    HttpServletRequest req) {
        Long operatorId = (Long) req.getAttribute("userId");
        return ApiResponse.ok(service.setRole(id, body.get("role"), operatorId, req));
    }

    @PostMapping("/{id}/reset-password")
    public ApiResponse<Map<String, Object>> resetPassword(@PathVariable Long id, HttpServletRequest req) {
        return ApiResponse.ok(service.resetPassword(id, req));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<String> delete(@PathVariable Long id, HttpServletRequest req) {
        Long operatorId = (Long) req.getAttribute("userId");
        service.softDelete(id, operatorId, req);
        return ApiResponse.ok("deleted");
    }
}

package com.stock.controller;

import com.stock.model.dto.ApiResponse;
import com.stock.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/user")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @PostMapping("/register")
    public ApiResponse<?> register(@RequestBody Map<String, String> body) {
        try {
            return ApiResponse.ok(userService.register(
                body.get("username"), body.get("password"), body.get("nickname")));
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/login")
    public ApiResponse<?> login(@RequestBody Map<String, String> body) {
        try {
            return ApiResponse.ok(userService.login(body.get("username"), body.get("password")));
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @GetMapping("/info")
    public ApiResponse<?> info(HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(userService.getUserById(userId));
    }

    @GetMapping("/watchlists")
    public ApiResponse<?> watchlists(HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(userService.getWatchlists(userId));
    }

    @PostMapping("/watchlists/add")
    public ApiResponse<?> addToWatchlist(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        Long groupId = Long.valueOf(body.get("groupId").toString());
        String code = body.get("code").toString();
        userService.addToWatchlist(userId, groupId, code, null);
        return ApiResponse.ok("添加成功");
    }

    @PostMapping("/watchlists/remove")
    public ApiResponse<?> removeFromWatchlist(@RequestBody Map<String, Object> body) {
        Long groupId = Long.valueOf(body.get("groupId").toString());
        String code = body.get("code").toString();
        userService.removeFromWatchlist(groupId, code);
        return ApiResponse.ok("移除成功");
    }

    @PostMapping("/watchlists/create")
    public ApiResponse<?> createGroup(@RequestBody Map<String, String> body, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(userService.createGroup(userId, body.get("name")));
    }
}

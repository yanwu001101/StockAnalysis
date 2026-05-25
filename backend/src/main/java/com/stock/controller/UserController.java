package com.stock.controller;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import com.stock.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/api/user")
public class UserController {

    private final UserService userService;
    private final DataService dataService;

    public UserController(UserService userService, DataService dataService) {
        this.userService = userService;
        this.dataService = dataService;
    }

    @PostMapping("/register")
    public ApiResponse<?> register(@RequestBody Map<String, String> body) {
        return ApiResponse.ok(userService.register(
            body.get("username"), body.get("password"), body.get("nickname")));
    }

    @PostMapping("/login")
    public ApiResponse<?> login(@RequestBody Map<String, String> body) {
        return ApiResponse.ok(userService.login(body.get("username"), body.get("password")));
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
        List<Map<String, Object>> groups = userService.getWatchlists(userId);
        // Enrich each watchlist stock with spot quote (price / change / industry / name).
        // The Watchlist entity only stores stockCode/stockName; the table view needs
        // live fields whose property names are `code/name/price/changePercent/industry`.
        for (Map<String, Object> g : groups) {
            Object rawStocks = g.get("stocks");
            if (!(rawStocks instanceof List<?> rawList)) continue;
            List<Map<String, Object>> enriched = new ArrayList<>(rawList.size());
            for (Object item : rawList) {
                JSONObject row = JSONObject.from(item);
                String code = row.getString("stockCode");
                if (code == null || code.isEmpty()) continue;
                Map<String, Object> view = new LinkedHashMap<>();
                view.put("code", code);
                view.put("name", row.getString("stockName"));
                view.put("price", null);
                view.put("changePercent", null);
                view.put("industry", "");
                view.put("compositeScore", null);
                try {
                    JSONObject detail = dataService.getStockDetail(code);
                    if (detail != null) {
                        if (view.get("name") == null || view.get("name").toString().isEmpty()) {
                            view.put("name", detail.getString("name"));
                        }
                        view.put("industry", detail.getString("industry"));
                        view.put("price", detail.get("price"));
                        view.put("changePercent", detail.get("changePercent"));
                    }
                } catch (Exception ignored) {}
                enriched.add(view);
            }
            g.put("stocks", enriched);
        }
        return ApiResponse.ok(groups);
    }

    @PostMapping("/watchlists/add")
    public ApiResponse<?> addToWatchlist(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        Object gidObj = body.get("groupId");
        Long groupId = gidObj == null ? 0L : Long.valueOf(gidObj.toString());
        Object codeObj = body.get("code");
        if (codeObj == null) return ApiResponse.error("缺少股票代码");
        userService.addToWatchlist(userId, groupId, codeObj.toString(), null);
        return ApiResponse.ok("添加成功");
    }

    @PostMapping("/watchlists/remove")
    public ApiResponse<?> removeFromWatchlist(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        Object codeObj = body.get("code");
        if (codeObj == null) return ApiResponse.error("缺少股票代码");
        Object gidObj = body.get("groupId");
        Long groupId = gidObj == null ? null : Long.valueOf(gidObj.toString());
        userService.removeFromWatchlist(userId, groupId, codeObj.toString());
        return ApiResponse.ok("移除成功");
    }

    @PostMapping("/watchlists/create")
    public ApiResponse<?> createGroup(@RequestBody Map<String, String> body, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        return ApiResponse.ok(userService.createGroup(userId, body.get("name")));
    }
}

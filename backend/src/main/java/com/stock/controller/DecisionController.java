package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import com.stock.service.PortfolioService;
import com.stock.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 决策层网关:排名快照 / 稳定候选池 / 最终交易决策。
 *
 * <p>今日决策需要用户持仓(含 T+1 锁定)与自选,这里在网关侧按登录用户组装后
 * 透传给 data-service;未登录时只返回不含持仓的候选池与买入建议。
 */
@RestController
@RequestMapping("/api/decision")
public class DecisionController {

    private final DataService dataService;
    private final PortfolioService portfolioService;
    private final UserService userService;

    public DecisionController(DataService dataService, PortfolioService portfolioService, UserService userService) {
        this.dataService = dataService;
        this.portfolioService = portfolioService;
        this.userService = userService;
    }

    @GetMapping("/today")
    public ApiResponse<?> today(@RequestParam(name = "withT", defaultValue = "true") boolean withT,
                                HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        JSONObject body = new JSONObject();
        body.put("with_t", withT);
        if (userId != null) {
            try {
                body.put("positions", portfolioService.positionsForDecision(userId));
            } catch (Exception ignored) {
                body.put("positions", List.of());
            }
            body.put("watchlist", watchlistCodes(userId));
        } else {
            body.put("positions", List.of());
            body.put("watchlist", List.of());
        }
        JSONObject out = dataService.getDecisionToday(body);
        if (out != null) out.put("loggedIn", userId != null);
        return ApiResponse.ok(out);
    }

    @GetMapping("/snapshots")
    public ApiResponse<?> snapshots(@RequestParam(required = false) String date) {
        return ApiResponse.ok(dataService.getDecisionSnapshots(date));
    }

    @GetMapping("/snapshot/{id}")
    public ApiResponse<?> snapshot(@PathVariable String id, @RequestParam(required = false) Integer limit) {
        return ApiResponse.ok(dataService.getDecisionSnapshot(id, limit));
    }

    @GetMapping("/stock/{code}/history")
    public ApiResponse<?> history(@PathVariable String code, @RequestParam(required = false) Integer n) {
        return ApiResponse.ok(dataService.getDecisionStockHistory(code, n));
    }

    /** 手动触发一次快照(冷启动/盘中补跑)。需要登录,避免匿名刷重算。 */
    @PostMapping("/snapshot/run")
    public ApiResponse<?> run(@RequestBody(required = false) Map<String, Object> body, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        JSONObject json = body == null ? new JSONObject() : new JSONObject(body);
        json.put("note", "manual:user" + userId);
        return ApiResponse.ok(dataService.runDecisionSnapshot(json));
    }

    private List<String> watchlistCodes(Long userId) {
        List<String> codes = new ArrayList<>();
        try {
            for (Map<String, Object> g : userService.getWatchlists(userId)) {
                Object stocks = g.get("stocks");
                if (!(stocks instanceof List<?> list)) continue;
                for (Object item : list) {
                    JSONObject row = JSONObject.from(item);
                    String code = row.getString("stockCode");
                    if (code != null && !code.isEmpty() && !codes.contains(code)) codes.add(code);
                }
            }
        } catch (Exception ignored) {
        }
        return codes;
    }
}

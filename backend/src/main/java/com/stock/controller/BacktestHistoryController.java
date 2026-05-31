package com.stock.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.stock.exception.BusinessException;
import com.stock.mapper.BacktestRunMapper;
import com.stock.model.dto.ApiResponse;
import com.stock.model.entity.BacktestRun;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 用户保存的回测历史。挂在 /api/user/backtests —— 注意**不能**用 /api/backtests,
 * 否则会被 AuthInterceptor 白名单前缀 "/api/backtest" 命中而变成匿名公开。
 * /api/user/** 不在白名单 → 自动要求登录;按 id 的取/删一律带 user_id 条件防越权。
 */
@RestController
@RequestMapping("/api/user/backtests")
public class BacktestHistoryController {

    private final BacktestRunMapper mapper;

    public BacktestHistoryController(BacktestRunMapper mapper) {
        this.mapper = mapper;
    }

    /** 保存一次回测快照。body: { name, request, result }(result 为前端持有的扁平结果)。 */
    @PostMapping
    public ApiResponse<?> save(@RequestBody Map<String, Object> body, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");

        JSONObject res = body.get("result") == null ? null : JSONObject.from(body.get("result"));
        if (res == null) throw new BusinessException("缺少回测结果");
        JSONObject req = body.get("request") == null ? null : JSONObject.from(body.get("request"));

        String name = body.get("name") == null ? "" : body.get("name").toString().trim();
        if (name.isEmpty()) name = "未命名回测";
        if (name.length() > 100) name = name.substring(0, 100);

        // strategyId 列 NOT NULL —— 结果里没有就回退到请求,再兜底空串
        String strategyId = res.getString("strategyId");
        if (strategyId == null && req != null) strategyId = req.getString("strategyId");
        if (strategyId == null) strategyId = "";

        BacktestRun row = new BacktestRun();
        row.setUserId(userId);
        row.setName(name);
        // stockCode 只在请求里(结果未回传)
        row.setStockCode(req != null ? req.getString("stockCode") : null);
        row.setStrategyId(strategyId);
        row.setStartDate(res.getString("start"));
        row.setEndDate(res.getString("end"));
        row.setInitialCapital(res.getDouble("initialCapital"));
        row.setTopN(res.getInteger("topN"));
        row.setTotalReturn(res.getDouble("totalReturn"));
        row.setAnnualizedReturn(res.getDouble("annualizedReturn"));
        row.setMaxDrawdown(res.getDouble("maxDrawdown"));
        row.setSharpeRatio(res.getDouble("sharpeRatio"));
        row.setWinRate(res.getDouble("winRate"));
        row.setTradeCount(res.getInteger("tradeCount"));
        row.setRequestJson(req != null ? req.toJSONString() : null);
        row.setResultJson(res.toJSONString());
        mapper.insert(row);

        return ApiResponse.ok(Map.of("id", row.getId()));
    }

    /** 当前用户的回测列表(只取摘要列,不拖 LONGTEXT),新→旧。 */
    @GetMapping
    public ApiResponse<?> list(HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        LambdaQueryWrapper<BacktestRun> w = new LambdaQueryWrapper<BacktestRun>()
            .select(BacktestRun::getId, BacktestRun::getName, BacktestRun::getStockCode,
                    BacktestRun::getStrategyId, BacktestRun::getStartDate, BacktestRun::getEndDate,
                    BacktestRun::getTotalReturn, BacktestRun::getAnnualizedReturn,
                    BacktestRun::getMaxDrawdown, BacktestRun::getSharpeRatio,
                    BacktestRun::getWinRate, BacktestRun::getTradeCount, BacktestRun::getCreatedAt)
            .eq(BacktestRun::getUserId, userId)
            .orderByDesc(BacktestRun::getCreatedAt);
        return ApiResponse.ok(mapper.selectList(w));
    }

    /** 取单条完整快照(还原成前端结果形状),仅限本人。 */
    @GetMapping("/{id}")
    public ApiResponse<?> get(@PathVariable Long id, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        BacktestRun row = mapper.selectOne(new LambdaQueryWrapper<BacktestRun>()
            .eq(BacktestRun::getId, id).eq(BacktestRun::getUserId, userId));
        if (row == null) throw new BusinessException(404, "记录不存在");

        JSONObject view = new JSONObject();
        view.put("id", row.getId());
        view.put("name", row.getName());
        view.put("createdAt", row.getCreatedAt());
        view.put("result", row.getResultJson() != null ? JSON.parseObject(row.getResultJson()) : null);
        view.put("request", row.getRequestJson() != null ? JSON.parseObject(row.getRequestJson()) : null);
        return ApiResponse.ok(view);
    }

    /** 删除单条,仅限本人。 */
    @DeleteMapping("/{id}")
    public ApiResponse<?> delete(@PathVariable Long id, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        if (userId == null) return ApiResponse.error(401, "未登录");
        int n = mapper.delete(new LambdaQueryWrapper<BacktestRun>()
            .eq(BacktestRun::getId, id).eq(BacktestRun::getUserId, userId));
        if (n == 0) throw new BusinessException(404, "记录不存在");
        return ApiResponse.ok("deleted");
    }
}

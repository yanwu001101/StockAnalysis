package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.model.dto.BacktestResultMapper;
import com.stock.service.DataService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.Set;

/**
 * Research jobs pass-through：回测/因子检验的后台任务化。
 *
 * 前端 POST 提交（body 与对应同步端点一致）拿到 job_id，随后轮询
 * GET /api/async/jobs/{id} 直到 DONE/FAILED——不再让 HTTP 请求吊死在
 * 5 分钟 RestTemplate 超时上。计算仍在 data-service（Python）执行，
 * Java 只做鉴权代理（/api/async 不在白名单 → 需登录）。
 */
@RestController
@RequestMapping("/api/async")
public class ResearchJobController {

    private final DataService dataService;

    /** kind → data-service 提交路径（与 data-service/api/research_jobs.py 白名单一致） */
    private static final Map<String, String> KINDS = Map.of(
            "backtest", "/api/async/backtest",
            "factorlab", "/api/async/factorlab",
            "alphalab-backtest", "/api/async/alphalab-backtest",
            "alphalab-factorlab", "/api/async/alphalab-factorlab"
    );

    public ResearchJobController(DataService dataService) {
        this.dataService = dataService;
    }

    @PostMapping("/{kind}")
    public ApiResponse<?> submit(@PathVariable String kind, @RequestBody JSONObject body, HttpServletRequest request) {
        long owner = owner(request);
        if (!KINDS.containsKey(kind)) throw new BusinessException("未知的任务类型: " + kind);
        JSONObject data = dataService.submitResearchJob(KINDS.get(kind), body, owner);
        if (data == null) throw new BusinessException("任务提交失败");
        if (data.get("error") != null) throw requestError(data);
        return ApiResponse.ok(data);
    }

    @GetMapping("/jobs/{jobId}")
    public ApiResponse<?> status(@PathVariable String jobId, HttpServletRequest request) {
        JSONObject data = dataService.getResearchJob(jobId, owner(request));
        if (data == null) throw new BusinessException("查询任务状态失败");
        // 任务对象恒含 "error" 键（QUEUED/RUNNING 时为 null）——不能用 containsKey 判断
        if (data.getString("error") != null) throw requestError(data);
        // A DONE job can still carry a business error (coverage, missing data).
        // Surface it just like the synchronous endpoint, never flatten it away.
        if ("DONE".equals(data.getString("status")) && KINDS_BACKTEST.contains(data.getString("kind"))) {
            JSONObject result = data.getJSONObject("result");
            if (result == null) throw new BusinessException("回测无数据");
            BacktestResultMapper.requireSuccess(result);
            data = new JSONObject(data);
            data.put("result", BacktestResultMapper.toView(result));
        }
        return ApiResponse.ok(data);
    }

    private static final Set<String> KINDS_BACKTEST = Set.of("backtest", "alphalab-backtest");

    private static long owner(HttpServletRequest request) {
        Object id = request.getAttribute("userId");
        if (!(id instanceof Long value) || value <= 0) throw new BusinessException(401, "未登录");
        return value;
    }

    private static BusinessException requestError(JSONObject data) {
        Integer status = data.getInteger("upstream_status");
        return new BusinessException(status == null ? 400 : status, data.getString("error"));
    }

}

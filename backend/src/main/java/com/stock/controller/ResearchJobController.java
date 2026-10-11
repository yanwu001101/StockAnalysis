package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
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
    public ApiResponse<?> submit(@PathVariable String kind, @RequestBody JSONObject body) {
        if (!KINDS.containsKey(kind)) throw new BusinessException("未知的任务类型: " + kind);
        JSONObject data = dataService.submitResearchJob(KINDS.get(kind), body);
        if (data == null) throw new BusinessException("任务提交失败");
        if (data.containsKey("error")) throw new BusinessException(data.getString("error"));
        return ApiResponse.ok(data);
    }

    @GetMapping("/jobs/{jobId}")
    public ApiResponse<?> status(@PathVariable String jobId) {
        JSONObject data = dataService.getResearchJob(jobId);
        if (data == null) throw new BusinessException("查询任务状态失败");
        // 任务对象恒含 "error" 键（QUEUED/RUNNING 时为 null）——不能用 containsKey 判断
        if (data.getString("error") != null) throw new BusinessException(data.getString("error"));
        // 回测类结果做与同步端点相同的 snake_case -> camelCase 扁平化，
        // 保证异步/同步两条路给前端的是同一份数据契约
        if ("DONE".equals(data.getString("status")) && data.getJSONObject("result") != null
                && KINDS_BACKTEST.contains(data.getString("kind"))) {
            data.put("result", flattenBacktest(data.getJSONObject("result")));
        }
        return ApiResponse.ok(data);
    }

    private static final Set<String> KINDS_BACKTEST = Set.of("backtest", "alphalab-backtest");

    /** 与 AlphaLabController/BacktestController 的视图扁平化完全一致。 */
    private static JSONObject flattenBacktest(JSONObject data) {
        JSONObject view = new JSONObject();
        JSONObject m = data.getJSONObject("metrics");
        if (m != null) {
            view.put("totalReturn", m.getOrDefault("total_return", 0));
            view.put("annualizedReturn", m.getOrDefault("annualized_return", 0));
            double dd = m.getDoubleValue("max_drawdown");
            view.put("maxDrawdown", Math.abs(dd));
            view.put("sharpeRatio", m.getOrDefault("sharpe_ratio", 0));
            view.put("calmarRatio", m.getOrDefault("calmar_ratio", 0));
            view.put("winRate", m.getOrDefault("win_rate", 0));
            view.put("tradeCount", m.getOrDefault("trade_count", 0));
            if (m.containsKey("benchmark_return")) view.put("benchmarkReturn", m.get("benchmark_return"));
            if (m.containsKey("excess_return")) view.put("excessReturn", m.get("excess_return"));
            if (m.containsKey("turnover_rate")) view.put("turnoverRate", m.get("turnover_rate"));
            if (m.containsKey("total_costs")) view.put("totalCosts", m.get("total_costs"));
        }
        view.put("equityCurve", data.getJSONArray("equity_curve"));
        view.put("trades", data.getJSONArray("trades"));
        view.put("picks", data.getJSONArray("picks"));
        view.put("mode", data.getString("mode"));
        view.put("expression", data.getString("expression"));
        view.put("start", data.getString("start"));
        view.put("end", data.getString("end"));
        view.put("initialCapital", data.get("initial_capital"));
        view.put("topN", data.get("top_n"));
        view.put("rebalance", data.getString("rebalance"));
        view.put("benchmarkCurve", data.getJSONArray("benchmark_curve"));
        view.put("costs", data.getJSONObject("costs"));
        return view;
    }
}

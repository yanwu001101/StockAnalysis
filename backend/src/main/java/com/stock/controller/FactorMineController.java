package com.stock.controller;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

/**
 * Factor Mining pass-through（因子挖掘）。
 *
 * 计算全部在 data-service（Python）：任务队列/候选生成/快速 IC/去重/完整检验。
 * Java 侧只做鉴权代理（本路由不在白名单 → 默认要求登录，符合"用户研究资产"语义）。
 * 研究载荷保持 snake_case 透传；data-service 的 {"error": ...} 4xx 原样抛给前端。
 *
 * 注意路由前缀：/api/factormine 不与任何白名单前缀（/api/backtest、/api/screen…）
 * 匹配，避免匿名访问漏洞（见 BacktestHistoryController 的前缀陷阱注释）。
 */
@RestController
@RequestMapping("/api/factormine")
public class FactorMineController {

    private final DataService dataService;

    public FactorMineController(DataService dataService) {
        this.dataService = dataService;
    }

    @PostMapping("/mine")
    public ApiResponse<?> mine(@RequestBody JSONObject body) {
        JSONObject data = dataService.fmCreateJob(body);
        if (data == null) throw new BusinessException("创建挖掘任务失败");
        if (data.containsKey("error")) throw new BusinessException(data.getString("error"));
        return ApiResponse.ok(data);
    }

    @GetMapping("/job/{jobId}")
    public ApiResponse<?> job(@PathVariable String jobId) {
        JSONObject data = dataService.fmJobStatus(jobId);
        if (data == null) throw new BusinessException("任务不存在");
        return ApiResponse.ok(data);
    }

    @PostMapping("/job/{jobId}/{action}")
    public ApiResponse<?> jobAction(@PathVariable String jobId, @PathVariable String action) {
        if (!action.equals("pause") && !action.equals("resume") && !action.equals("cancel")) {
            throw new BusinessException("不支持的操作: " + action);
        }
        JSONObject data = dataService.fmJobAction(jobId, action);
        if (data == null) throw new BusinessException("操作失败");
        if (data.containsKey("error")) throw new BusinessException(data.getString("error"));
        return ApiResponse.ok(data);
    }

    @GetMapping("/factors")
    public ApiResponse<?> factors(jakarta.servlet.http.HttpServletRequest request) {
        // 透传原始查询串（job_id/status/verdict/in_library/limit/offset/order），
        // 使前端筛选条件原样到达 data-service
        JSONArray data = dataService.fmFactors(request.getQueryString());
        if (data == null) throw new BusinessException("候选因子获取失败");
        return ApiResponse.ok(data);
    }

    @GetMapping("/factor/{factorId}")
    public ApiResponse<?> factor(@PathVariable String factorId) {
        JSONObject data = dataService.fmFactorDetail(factorId);
        if (data == null) throw new BusinessException("因子不存在");
        if (data.containsKey("error")) throw new BusinessException(data.getString("error"));
        return ApiResponse.ok(data);
    }

    @PostMapping("/factor/{factorId}/library")
    public ApiResponse<?> library(@PathVariable String factorId,
                                  @RequestBody(required = false) JSONObject body) {
        JSONObject data = dataService.fmFactorAction(factorId, "library", body);
        if (data == null) throw new BusinessException("因子库更新失败");
        if (data.containsKey("error")) throw new BusinessException(data.getString("error"));
        return ApiResponse.ok(data);
    }

    @PostMapping("/factor/{factorId}/revalidate")
    public ApiResponse<?> revalidate(@PathVariable String factorId) {
        JSONObject data = dataService.fmRevalidate(factorId);
        if (data == null) throw new BusinessException("重新检验失败");
        if (data.containsKey("error")) throw new BusinessException(data.getString("error"));
        return ApiResponse.ok(data);
    }

    @PostMapping("/factor/{factorId}/screen")
    public ApiResponse<?> screen(@PathVariable String factorId,
                                 @RequestBody(required = false) JSONObject body) {
        JSONObject data = dataService.fmFactorScreen(factorId, body);
        if (data == null) throw new BusinessException("因子选股失败");
        if (data.containsKey("error")) throw new BusinessException(data.getString("error"));
        return ApiResponse.ok(data);
    }

    @GetMapping("/library")
    public ApiResponse<?> libraryList() {
        JSONObject data = dataService.fmLibrary();
        if (data == null) throw new BusinessException("因子库获取失败");
        return ApiResponse.ok(data);
    }

    @GetMapping("/atoms")
    public ApiResponse<?> atoms() {
        JSONObject data = dataService.fmAtoms();
        if (data == null) throw new BusinessException("原子因子目录获取失败");
        return ApiResponse.ok(data);
    }

    @GetMapping("/operators")
    public ApiResponse<?> operators() {
        JSONObject data = dataService.fmOperators();
        if (data == null) throw new BusinessException("算子目录获取失败");
        return ApiResponse.ok(data);
    }

}

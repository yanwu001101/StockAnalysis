package com.stock.controller.admin;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import com.stock.service.admin.AdminAuditService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/admin/tasks")
public class AdminTaskController {

    private final DataService dataService;
    private final AdminAuditService audit;

    public AdminTaskController(DataService dataService, AdminAuditService audit) {
        this.dataService = dataService;
        this.audit = audit;
    }

    @GetMapping("/jobs")
    public ApiResponse<JSONObject> jobs() {
        return ApiResponse.ok(dataService.getAdminSchedulerJobs());
    }

    @PostMapping("/run")
    public ApiResponse<JSONObject> run(@RequestBody Map<String, String> body, HttpServletRequest req) {
        String job = body == null ? null : body.get("job");
        if (job == null || job.isBlank()) job = "postmarket";
        JSONObject resp = dataService.adminWarmupStart(job);
        if (resp == null) throw new BusinessException("任务提交失败");
        if (resp.get("error") != null) throw jobRequestError(resp);
        audit.record(req, "TASK_RUN", "job:" + job, resp);
        return ApiResponse.ok(resp);
    }

    @GetMapping("/runs")
    public ApiResponse<JSONObject> runs(@RequestParam(required = false) String id) {
        JSONObject resp = dataService.getAdminWarmupStatus(id);
        if (resp == null) throw new BusinessException("查询任务状态失败");
        // Preserve the complete result of a failed run (including steps/error).
        // Only an explicit non-2xx marker from DataService is a request failure.
        if (resp.get("upstream_status") != null && resp.get("error") != null) throw jobRequestError(resp);
        return ApiResponse.ok(resp);
    }

    @PostMapping("/cache/clear")
    public ApiResponse<JSONObject> clearCache(@RequestParam(required = false) String pattern,
                                              HttpServletRequest req) {
        if (pattern == null || pattern.isBlank()) pattern = "ds:*";
        JSONObject resp = dataService.adminCacheClear(pattern);
        audit.record(req, "CACHE_CLEAR", "pattern:" + pattern, resp);
        return ApiResponse.ok(resp);
    }

    private static BusinessException jobRequestError(JSONObject data) {
        Integer status = data.getInteger("upstream_status");
        return new BusinessException(status == null ? 400 : status, data.getString("error"));
    }
}

package com.stock.controller.admin;

import com.alibaba.fastjson2.JSONObject;
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
        audit.record(req, "TASK_RUN", "job:" + job, resp);
        return ApiResponse.ok(resp);
    }

    @GetMapping("/runs")
    public ApiResponse<JSONObject> runs(@RequestParam(required = false) String id) {
        return ApiResponse.ok(dataService.getAdminWarmupStatus(id));
    }

    @PostMapping("/cache/clear")
    public ApiResponse<JSONObject> clearCache(@RequestParam(required = false) String pattern,
                                              HttpServletRequest req) {
        if (pattern == null || pattern.isBlank()) pattern = "ds:*";
        JSONObject resp = dataService.adminCacheClear(pattern);
        audit.record(req, "CACHE_CLEAR", "pattern:" + pattern, resp);
        return ApiResponse.ok(resp);
    }
}

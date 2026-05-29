package com.stock.controller.admin;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.stock.config.AccessLogInterceptor;
import com.stock.model.dto.ApiResponse;
import com.stock.model.entity.AdminAuditLog;
import com.stock.service.DataService;
import com.stock.service.admin.AdminAuditService;
import org.springframework.web.bind.annotation.*;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin/monitor")
public class AdminMonitorController {

    private final DataService dataService;
    private final AdminAuditService auditService;

    public AdminMonitorController(DataService dataService, AdminAuditService auditService) {
        this.dataService = dataService;
        this.auditService = auditService;
    }

    @GetMapping("/overview")
    public ApiResponse<Map<String, Object>> overview() {
        Map<String, Object> out = new HashMap<>();

        Runtime rt = Runtime.getRuntime();
        Map<String, Object> jvm = new HashMap<>();
        MemoryMXBean mem = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = mem.getHeapMemoryUsage();
        jvm.put("heapUsedMB", heap.getUsed() / 1024 / 1024);
        jvm.put("heapMaxMB", heap.getMax() / 1024 / 1024);
        jvm.put("processors", rt.availableProcessors());
        jvm.put("uptimeMs", ManagementFactory.getRuntimeMXBean().getUptime());
        out.put("jvm", jvm);

        try {
            out.put("dataService", dataService.getAdminHealthDetail());
        } catch (Exception e) {
            out.put("dataService", Map.of("error", e.getMessage()));
        }

        return ApiResponse.ok(out);
    }

    @GetMapping("/access-log")
    public ApiResponse<List<AccessLogInterceptor.Entry>> accessLog(
        @RequestParam(defaultValue = "200") int limit) {
        return ApiResponse.ok(AccessLogInterceptor.snapshot(limit));
    }

    @GetMapping("/audit-log")
    public ApiResponse<IPage<AdminAuditLog>> auditLog(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "30") int size,
        @RequestParam(required = false) String action) {
        return ApiResponse.ok(auditService.page(page, size, action));
    }
}

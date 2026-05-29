package com.stock.service.admin;

import com.alibaba.fastjson2.JSON;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.stock.mapper.AdminAuditLogMapper;
import com.stock.model.entity.AdminAuditLog;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Service;

import java.util.Map;

@Service
public class AdminAuditService {

    private final AdminAuditLogMapper mapper;

    public AdminAuditService(AdminAuditLogMapper mapper) {
        this.mapper = mapper;
    }

    /** Record one admin action. Safe to call from any admin Service — never throws. */
    public void record(HttpServletRequest req, String action, String target, Object payload) {
        try {
            AdminAuditLog row = new AdminAuditLog();
            row.setAdminId((Long) req.getAttribute("userId"));
            Object name = req.getAttribute("username");
            row.setAdminName(name == null ? "" : name.toString());
            row.setAction(action);
            row.setTarget(target == null ? "" : target);
            row.setPayloadJson(payload == null ? null : JSON.toJSONString(payload));
            row.setIp(clientIp(req));
            mapper.insert(row);
        } catch (Exception ignored) {
            // Audit must not break the actual operation.
        }
    }

    private String clientIp(HttpServletRequest req) {
        String xf = req.getHeader("X-Forwarded-For");
        if (xf != null && !xf.isBlank()) return xf.split(",")[0].trim();
        String real = req.getHeader("X-Real-IP");
        if (real != null && !real.isBlank()) return real;
        return req.getRemoteAddr();
    }

    public IPage<AdminAuditLog> page(int pageNum, int pageSize, String action) {
        LambdaQueryWrapper<AdminAuditLog> w = new LambdaQueryWrapper<AdminAuditLog>()
            .orderByDesc(AdminAuditLog::getCreatedAt);
        if (action != null && !action.isBlank()) {
            w.eq(AdminAuditLog::getAction, action);
        }
        return mapper.selectPage(new Page<>(pageNum, pageSize), w);
    }
}

package com.stock.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.stock.exception.BusinessException;
import com.stock.mapper.AppConfigMapper;
import com.stock.model.dto.ApiResponse;
import com.stock.model.entity.AppConfig;
import com.stock.service.admin.AdminAuditService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin/configs")
public class AdminConfigController {

    private final AppConfigMapper mapper;
    private final AdminAuditService audit;

    public AdminConfigController(AppConfigMapper mapper, AdminAuditService audit) {
        this.mapper = mapper;
        this.audit = audit;
    }

    @GetMapping
    public ApiResponse<List<AppConfig>> list(@RequestParam(required = false) String keyword) {
        LambdaQueryWrapper<AppConfig> w = new LambdaQueryWrapper<AppConfig>()
            .orderByAsc(AppConfig::getK);
        if (keyword != null && !keyword.isBlank()) {
            w.and(q -> q.like(AppConfig::getK, keyword).or().like(AppConfig::getDescription, keyword));
        }
        return ApiResponse.ok(mapper.selectList(w));
    }

    @PutMapping("/{k}")
    public ApiResponse<AppConfig> upsert(@PathVariable String k,
                                         @RequestBody Map<String, String> body,
                                         HttpServletRequest req) {
        if (k == null || k.isBlank()) throw new BusinessException("配置 key 不能为空");
        String v = body.getOrDefault("v", "");
        String description = body.getOrDefault("description", "");
        Long operatorId = (Long) req.getAttribute("userId");

        AppConfig existing = mapper.selectById(k);
        if (existing == null) {
            AppConfig row = new AppConfig();
            row.setK(k);
            row.setV(v);
            row.setDescription(description);
            row.setUpdatedBy(operatorId);
            mapper.insert(row);
            audit.record(req, "CONFIG_CREATE", "k:" + k, Map.of("v", v));
            return ApiResponse.ok(row);
        } else {
            existing.setV(v);
            existing.setDescription(description);
            existing.setUpdatedBy(operatorId);
            mapper.updateById(existing);
            audit.record(req, "CONFIG_UPDATE", "k:" + k, Map.of("v", v));
            return ApiResponse.ok(existing);
        }
    }

    @DeleteMapping("/{k}")
    public ApiResponse<String> delete(@PathVariable String k, HttpServletRequest req) {
        mapper.deleteById(k);
        audit.record(req, "CONFIG_DELETE", "k:" + k, null);
        return ApiResponse.ok("deleted");
    }
}

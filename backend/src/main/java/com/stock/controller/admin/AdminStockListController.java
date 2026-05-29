package com.stock.controller.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.stock.exception.BusinessException;
import com.stock.mapper.StockListMapper;
import com.stock.model.dto.ApiResponse;
import com.stock.model.entity.StockList;
import com.stock.service.admin.AdminAuditService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.Set;

@RestController
@RequestMapping("/api/admin/stock-list")
public class AdminStockListController {

    private static final Set<String> VALID_TYPES = Set.of("whitelist", "blacklist", "pool");

    private final StockListMapper mapper;
    private final AdminAuditService audit;

    public AdminStockListController(StockListMapper mapper, AdminAuditService audit) {
        this.mapper = mapper;
        this.audit = audit;
    }

    @GetMapping
    public ApiResponse<List<StockList>> list(@RequestParam(required = false) String type) {
        LambdaQueryWrapper<StockList> w = new LambdaQueryWrapper<StockList>()
            .orderByDesc(StockList::getId);
        if (type != null && !type.isBlank()) {
            ensureValidType(type);
            w.eq(StockList::getListType, type);
        }
        return ApiResponse.ok(mapper.selectList(w));
    }

    @PostMapping
    public ApiResponse<StockList> add(@RequestBody Map<String, String> body, HttpServletRequest req) {
        String type = body.get("listType");
        String code = body.get("code");
        ensureValidType(type);
        if (code == null || code.isBlank()) throw new BusinessException("code 不能为空");
        StockList row = new StockList();
        row.setListType(type);
        row.setCode(code.trim());
        row.setNote(body.getOrDefault("note", ""));
        row.setCreatedBy((Long) req.getAttribute("userId"));
        try {
            mapper.insert(row);
        } catch (Exception e) {
            throw new BusinessException("已在名单中,无需重复添加");
        }
        audit.record(req, "STOCKLIST_ADD", type + ":" + code,
            Map.of("note", row.getNote()));
        return ApiResponse.ok(row);
    }

    @DeleteMapping("/{id}")
    public ApiResponse<String> delete(@PathVariable Long id, HttpServletRequest req) {
        StockList existing = mapper.selectById(id);
        if (existing == null) throw new BusinessException(404, "记录不存在");
        mapper.deleteById(id);
        audit.record(req, "STOCKLIST_REMOVE",
            existing.getListType() + ":" + existing.getCode(), null);
        return ApiResponse.ok("deleted");
    }

    private void ensureValidType(String type) {
        if (type == null || !VALID_TYPES.contains(type)) {
            throw new BusinessException("listType 必须为 whitelist / blacklist / pool");
        }
    }
}

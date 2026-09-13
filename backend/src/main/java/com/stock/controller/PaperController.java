package com.stock.controller;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

/**
 * Paper trading pass-through to the Python data-service.
 * 每日模拟盘：净值曲线 / 当前持仓 / 调仓记录。
 */
@RestController
@RequestMapping("/api/paper")
public class PaperController {

    private final DataService dataService;

    public PaperController(DataService dataService) {
        this.dataService = dataService;
    }

    @GetMapping
    public ApiResponse<?> overview() {
        JSONObject data = dataService.getPaper();
        if (data == null) throw new BusinessException("模拟盘无数据");
        return ApiResponse.ok(data);
    }

    /** 实盘半自动·里程碑1：委托清单生成（只读，系统不自动下单）。 */
    @GetMapping("/orders")
    public ApiResponse<?> orders(@RequestParam(value = "date", required = false) String date) {
        JSONObject data = dataService.getPaperOrders(date);
        if (data == null) throw new BusinessException("无可生成的委托单");
        return ApiResponse.ok(data);
    }

    @PostMapping("/reset")
    public ApiResponse<?> reset(@RequestBody JSONObject body) {
        JSONObject data = dataService.resetPaper(body);
        if (data == null) throw new BusinessException("重置失败");
        return ApiResponse.ok(data);
    }
}

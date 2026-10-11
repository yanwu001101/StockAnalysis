package com.stock.controller;

import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class ScreenerController {

    private final DataService dataService;

    public ScreenerController(DataService dataService) {
        this.dataService = dataService;
    }

    /**
     * Composite screener — accepts a raw map so any new field the front-end
     * adds (requireTriggered, strategyParams, ...) is passed through to the
     * data-service without needing a DTO update on every iteration. Validation
     * happens downstream.
     */
    @PostMapping("/screen")
    public ApiResponse<?> screen(@RequestBody Map<String, Object> body) {
        JSONObject json = new JSONObject(body);
        JSONArray data = dataService.getScreener(json);
        return ApiResponse.ok(data);
    }

    /**
     * 快照口径的评分选股:从最近一次排名快照按用户权重/过滤重算,
     * 同一快照下多次请求结果一致;响应为 {items, meta, prev}。
     */
    @PostMapping("/screen/snapshot")
    public ApiResponse<?> screenSnapshot(@RequestBody Map<String, Object> body) {
        return ApiResponse.ok(dataService.getScreenerSnapshot(new JSONObject(body)));
    }

    @GetMapping("/strategies-meta")
    public ApiResponse<?> strategiesMeta() {
        // Forward to data-service /api/v2/strategies which returns
        // {id, name, weight, params:[{name, label, default, min, max, step, desc}]}
        return ApiResponse.ok(dataService.getStrategiesMeta());
    }

    @GetMapping("/condition-fields")
    public ApiResponse<?> conditionFields() {
        return ApiResponse.ok(dataService.getConditionFields());
    }

    @PostMapping("/screen/conditions")
    public ApiResponse<?> screenConditions(@RequestBody java.util.Map<String, Object> body) {
        JSONObject json = new JSONObject(body);
        return ApiResponse.ok(dataService.runConditionScreener(json));
    }

    @GetMapping("/expression/help")
    public ApiResponse<?> expressionHelp() {
        return ApiResponse.ok(dataService.getExpressionHelp());
    }

    @PostMapping("/screen/expression")
    public ApiResponse<?> screenExpression(@RequestBody java.util.Map<String, Object> body) {
        JSONObject json = new JSONObject(body);
        Object data = dataService.runExpressionScreener(json);
        return ApiResponse.ok(data);
    }

    @PostMapping("/screen/expression/validate")
    public ApiResponse<?> validateExpression(@RequestBody java.util.Map<String, Object> body) {
        JSONObject json = new JSONObject(body);
        return ApiResponse.ok(dataService.validateExpression(json));
    }
}

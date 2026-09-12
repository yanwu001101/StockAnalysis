package com.stock.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import com.stock.model.dto.ApiResponse;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

/**
 * Factor lab pass-through to the Python data-service (IC / layered test / decay).
 * The research payload stays snake_case — the front-end reads it as-is.
 */
@RestController
@RequestMapping("/api")
public class FactorLabController {

    private final DataService dataService;

    public FactorLabController(DataService dataService) {
        this.dataService = dataService;
    }

    @PostMapping("/factorlab")
    public ApiResponse<?> factorlab(@RequestBody JSONObject body) {
        JSONObject data = dataService.runFactorLab(body);
        if (data == null) throw new BusinessException("因子检验无数据");
        if (data.containsKey("error")) {
            throw new BusinessException("因子检验失败: " + data.getString("error"));
        }
        return ApiResponse.ok(data);
    }
}

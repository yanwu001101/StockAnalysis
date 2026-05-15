package com.stock.controller;

import com.alibaba.fastjson2.JSON;
import com.alibaba.fastjson2.JSONArray;
import com.alibaba.fastjson2.JSONObject;
import com.stock.model.dto.ApiResponse;
import com.stock.model.dto.ScreenerRequest;
import com.stock.service.DataService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api")
public class ScreenerController {

    private final DataService dataService;

    public ScreenerController(DataService dataService) {
        this.dataService = dataService;
    }

    @PostMapping("/screen")
    public ApiResponse<?> screen(@RequestBody ScreenerRequest request) {
        try {
            JSONObject json = (JSONObject) JSON.toJSON(request);
            JSONArray data = dataService.getScreener(json);
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("选股失败: " + e.getMessage());
        }
    }

    @GetMapping("/strategies")
    public ApiResponse<?> strategies() {
        // Return the 10 built-in strategy definitions
        JSONArray strategies = new JSONArray();
        String[][] defs = {
            {"macd_ma", "MACD+均线趋势共振", "MACD金叉配合均线多头排列", "12", "#00D4FF"},
            {"multi_factor", "多因子价值投资", "ROE+负债率+现金流+成长性综合打分", "25", "#2AE8A4"},
            {"momentum_breakout", "动量突破策略", "股价突破N日新高+成交量放大确认", "10", "#FF9F43"},
            {"rsi_rebound", "RSI超卖反弹", "RSI从超卖区回升，捕捉反弹机会", "8", "#A78BFA"},
            {"bollinger_squeeze", "布林带收口突破", "布林带收窄后放量突破上轨", "8", "#FFC312"},
            {"chip_concentration", "筹码集中+机构增持", "股东户数减少+机构持仓增加", "10", "#FF6B81"},
            {"dividend_stability", "股息率+分红稳定性", "高股息+连续多年稳定分红", "8", "#FECA57"},
            {"northbound_flow", "北向资金流入", "外资持续买入的标的", "7", "#48DBFB"},
            {"sector_rotation", "行业轮动策略", "根据动量切换热门行业", "7", "#FF9FF3"},
            {"kdj_rsi_resonance", "KDJ+RSI双指标共振", "两个超买超卖指标同时发出信号", "5", "#54A0FF"},
        };
        for (String[] d : defs) {
            JSONObject s = new JSONObject();
            s.put("id", d[0]);
            s.put("name", d[1]);
            s.put("description", d[2]);
            s.put("weight", Integer.parseInt(d[3]));
            s.put("color", d[4]);
            strategies.add(s);
        }
        return ApiResponse.ok(strategies);
    }
}

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
        // Ten quantitative strategies — see data-service/strategies/__init__.py
        JSONArray strategies = new JSONArray();
        String[][] defs = {
            {"piotroski_f", "Piotroski F-Score", "9项基本面打分筛优质低估股 (Piotroski 2000)", "12", "#2AE8A4"},
            {"magic_formula", "神奇公式 Magic Formula", "ROC + 盈利收益率双排名 (Greenblatt)", "10", "#FFC312"},
            {"quality_factor", "质量因子 Quality", "稳定高ROE+现金流质量+低杠杆", "18", "#00D4FF"},
            {"momentum_12_1", "12-1月动量", "过去12月剔近1月的累计收益 (Jegadeesh-Titman)", "10", "#FF9F43"},
            {"low_volatility", "低波动异象", "60日波动率最低分位+正趋势确认 (BAB)", "8", "#A78BFA"},
            {"pead", "PEAD 盈余惊喜后漂移", "财报YoY增速跳变+近期公告事件触发", "10", "#FF6B81"},
            {"northbound_smart_money", "北向资金追踪", "外资5/10/20日加仓+持股比例提升", "8", "#48DBFB"},
            {"lhb_followup", "龙虎榜机构跟随", "机构席位净买+买入主导比", "8", "#FECA57"},
            {"sector_rotation", "行业动量轮动", "行业排名前20%+个股相对强势", "8", "#FF9FF3"},
            {"technical_resonance", "技术共振", "MACD金叉+均线多头+量价+北向5日加仓", "10", "#54A0FF"},
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

    @GetMapping("/strategies-meta")
    public ApiResponse<?> strategiesMeta() {
        // Forward to data-service /api/v2/strategies which returns
        // {id, name, weight, params:[{name, label, default, min, max, step, desc}]}
        try {
            return ApiResponse.ok(dataService.getStrategiesMeta());
        } catch (Exception e) {
            return ApiResponse.error("加载策略参数失败: " + e.getMessage());
        }
    }

    @GetMapping("/condition-fields")
    public ApiResponse<?> conditionFields() {
        try {
            return ApiResponse.ok(dataService.getConditionFields());
        } catch (Exception e) {
            return ApiResponse.error("加载字段失败: " + e.getMessage());
        }
    }

    @PostMapping("/screen/conditions")
    public ApiResponse<?> screenConditions(@RequestBody java.util.Map<String, Object> body) {
        try {
            JSONObject json = new JSONObject(body);
            return ApiResponse.ok(dataService.runConditionScreener(json));
        } catch (Exception e) {
            return ApiResponse.error("条件选股失败: " + e.getMessage());
        }
    }

    @GetMapping("/expression/help")
    public ApiResponse<?> expressionHelp() {
        try {
            return ApiResponse.ok(dataService.getExpressionHelp());
        } catch (Exception e) {
            return ApiResponse.error("加载帮助失败: " + e.getMessage());
        }
    }

    @PostMapping("/screen/expression")
    public ApiResponse<?> screenExpression(@RequestBody java.util.Map<String, Object> body) {
        try {
            JSONObject json = new JSONObject(body);
            Object data = dataService.runExpressionScreener(json);
            return ApiResponse.ok(data);
        } catch (Exception e) {
            return ApiResponse.error("表达式选股失败: " + e.getMessage());
        }
    }

    @PostMapping("/screen/expression/validate")
    public ApiResponse<?> validateExpression(@RequestBody java.util.Map<String, Object> body) {
        try {
            JSONObject json = new JSONObject(body);
            return ApiResponse.ok(dataService.validateExpression(json));
        } catch (Exception e) {
            return ApiResponse.error("校验失败: " + e.getMessage());
        }
    }
}

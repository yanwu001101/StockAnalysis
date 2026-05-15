package com.stock.model.dto;

import lombok.Data;
import java.util.Map;

@Data
public class BacktestRequest {
    private Map<String, ScreenerRequest.StrategyWeight> strategyConfig;
    private String startDate;
    private String endDate;
    private double initialCapital = 100;
    private int topN = 10;
}

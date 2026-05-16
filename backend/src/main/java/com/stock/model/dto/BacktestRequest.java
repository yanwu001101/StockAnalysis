package com.stock.model.dto;

import lombok.Data;
import java.util.Map;

@Data
public class BacktestRequest {
    /** Selected strategy id (one of the ten in data-service/strategies/__init__.py). */
    private String strategyId;
    /** Optional: when set, switches to single-stock timing backtest. */
    private String stockCode;
    /** Optional per-strategy weights, used when strategyId is absent. */
    private Map<String, ScreenerRequest.StrategyWeight> strategyConfig;
    private String startDate;
    private String endDate;
    private double initialCapital = 1_000_000;
    private int topN = 10;
    private String rebalance = "weekly";
}

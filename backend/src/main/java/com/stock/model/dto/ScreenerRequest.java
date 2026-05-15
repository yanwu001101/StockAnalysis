package com.stock.model.dto;

import lombok.Data;
import java.util.List;
import java.util.Map;

@Data
public class ScreenerRequest {
    private Map<String, StrategyWeight> strategies;
    private ScreenerFilters filters;
    private int limit = 80;

    @Data
    public static class StrategyWeight {
        private boolean enabled = true;
        private int weight = 10;
    }

    @Data
    public static class ScreenerFilters {
        private int minScore = 60;
        private double minMarketCap = 200;
        private double maxDebtRatio = 50;
        private double minRoe = 15;
        private List<String> industries;
    }
}

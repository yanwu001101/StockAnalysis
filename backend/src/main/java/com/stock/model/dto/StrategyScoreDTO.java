package com.stock.model.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class StrategyScoreDTO {
    private String strategyName;
    private double score;
    private String signal; // bullish, bearish, neutral
    private Object details;
    private boolean triggered;
}

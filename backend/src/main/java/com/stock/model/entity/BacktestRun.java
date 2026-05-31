package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

/**
 * 用户保存的回测快照。摘要字段单列存储(列表/排序无需解析大 JSON),
 * request_json / result_json 存全量以便原样回看。见 BacktestHistoryController。
 */
@Data
@TableName("backtest_run")
public class BacktestRun {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String name;
    private String stockCode;
    private String strategyId;
    private String startDate;
    private String endDate;
    private Double initialCapital;
    private Integer topN;
    private Double totalReturn;
    private Double annualizedReturn;
    private Double maxDrawdown;
    private Double sharpeRatio;
    private Double winRate;
    private Integer tradeCount;
    private String requestJson;
    private String resultJson;
    private LocalDateTime createdAt;
}

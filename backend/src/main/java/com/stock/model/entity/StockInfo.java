package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("stock_info")
public class StockInfo {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String code;
    private String name;
    private String industry;
    private BigDecimal marketCap;
    private BigDecimal latestPrice;
    private BigDecimal roe;
    private BigDecimal debtRatio;
    private BigDecimal revenueGrowth;
    private BigDecimal profitGrowth;
    private BigDecimal cashFlow;
    private BigDecimal grossMargin;
    private LocalDateTime updatedAt;
}

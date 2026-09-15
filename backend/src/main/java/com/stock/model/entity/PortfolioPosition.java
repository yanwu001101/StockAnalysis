package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

@Data
@TableName("portfolio_position")
public class PortfolioPosition {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String code;
    private String name;
    private BigDecimal shares;
    private BigDecimal availableShares;
    private BigDecimal avgCost;
    /** 最近一次买入日期;与 lockedShares 一起实现 A 股 T+1:当日买入部分当日不可卖 */
    private LocalDate lastBuyDate;
    /** lastBuyDate 当天买入的股数(当日锁定;次一交易日自动解锁) */
    private BigDecimal lockedShares;
    private BigDecimal targetWeight;
    private String source;
    private String notes;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    @TableLogic
    private Integer deleted;
}

package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.math.BigDecimal;
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
    private BigDecimal targetWeight;
    private String source;
    private String notes;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    @TableLogic
    private Integer deleted;
}

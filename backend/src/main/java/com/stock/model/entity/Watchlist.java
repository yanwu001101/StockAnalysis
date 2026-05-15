package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("watchlist")
public class Watchlist {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private Long groupId;
    private String stockCode;
    private String stockName;
    private LocalDateTime createdAt;
    @TableLogic
    private Integer deleted;
}

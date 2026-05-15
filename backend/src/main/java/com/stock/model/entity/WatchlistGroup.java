package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("watchlist_group")
public class WatchlistGroup {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String name;
    private LocalDateTime createdAt;
    @TableLogic
    private Integer deleted;
}

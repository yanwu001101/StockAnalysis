package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("user_strategy")
public class UserStrategy {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String name;
    private String configJson;
    private String filterJson;
    private Integer isDefault;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
    @TableLogic
    private Integer deleted;
}

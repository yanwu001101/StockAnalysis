package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("app_config")
public class AppConfig {
    @TableId(type = IdType.INPUT)
    private String k;
    private String v;
    private String description;
    private LocalDateTime updatedAt;
    private Long updatedBy;
}

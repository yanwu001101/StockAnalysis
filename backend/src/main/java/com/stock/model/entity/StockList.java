package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;
import java.time.LocalDateTime;

@Data
@TableName("stock_list")
public class StockList {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String listType;
    private String code;
    private String note;
    private LocalDateTime createdAt;
    private Long createdBy;
}

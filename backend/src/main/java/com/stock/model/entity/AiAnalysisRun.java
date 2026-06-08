package com.stock.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("ai_analysis_run")
public class AiAnalysisRun {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String scope;
    private String requestJson;
    private String resultText;
    private String model;
    private String feedback;
    private String feedbackNote;
    private LocalDateTime createdAt;
}

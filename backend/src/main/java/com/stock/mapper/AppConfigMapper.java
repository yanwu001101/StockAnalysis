package com.stock.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.stock.model.entity.AppConfig;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface AppConfigMapper extends BaseMapper<AppConfig> {
}

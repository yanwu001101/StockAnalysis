package com.stock.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.stock.model.entity.BacktestRun;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface BacktestRunMapper extends BaseMapper<BacktestRun> {
}

package com.stock.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.stock.model.entity.StockList;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface StockListMapper extends BaseMapper<StockList> {
}

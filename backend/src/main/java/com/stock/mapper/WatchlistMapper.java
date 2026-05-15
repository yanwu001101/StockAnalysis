package com.stock.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.stock.model.entity.Watchlist;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface WatchlistMapper extends BaseMapper<Watchlist> {
}

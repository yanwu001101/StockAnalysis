package com.stock.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.stock.model.entity.Watchlist;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface WatchlistMapper extends BaseMapper<Watchlist> {

    /**
     * Find any watchlist row by (group, code) ignoring the @TableLogic
     * `deleted` filter — so soft-deleted rows are also returned. Needed to
     * revive a soft-deleted entry instead of hitting the (group_id, stock_code)
     * UNIQUE index on insert.
     */
    @Select("SELECT id, user_id, group_id, stock_code, stock_name, created_at, deleted " +
            "FROM watchlist WHERE group_id = #{groupId} AND stock_code = #{code} LIMIT 1")
    Watchlist findByGroupAndCodeRaw(@Param("groupId") Long groupId,
                                     @Param("code") String code);

    /** Resurrect a soft-deleted row (deleted=1 → 0). Returns affected rows. */
    @Update("UPDATE watchlist SET deleted = 0, stock_name = COALESCE(#{name}, stock_name) " +
            "WHERE id = #{id}")
    int revive(@Param("id") Long id, @Param("name") String name);
}

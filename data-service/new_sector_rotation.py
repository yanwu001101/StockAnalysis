#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Updated sector_rotation function for app.py
Replaces lines 905-930 approximately
"""

def sector_rotation():
    """板块涨跌 (使用数据库行业数据)"""
    try:
        from sector_data import fetch_sector_rotation_from_db

        # 获取spot数据
        spot = fetch_spot()
        if spot is None or spot.empty:
            logger.warning("sector_rotation: no spot data")
            return jsonify([])

        # 使用新的sector_data模块
        sectors = fetch_sector_rotation_from_db(spot)

        # 添加flow和momentum字段（兼容前端）
        for i, sector in enumerate(sectors):
            sector['flow'] = 0
            sector['momentum'] = 0
            sector['rank'] = i + 1

        return jsonify(sectors)

    except Exception as e:
        logger.error(f"sector_rotation failed: {e}", exc_info=True)
        traceback.print_exc()
        return jsonify([])

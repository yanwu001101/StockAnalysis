# -*- coding: utf-8 -*-
"""
板块涨跌数据获取模块
从数据库获取行业信息，结合spot数据计算板块涨跌幅
"""
import pandas as pd
from typing import List, Dict
from db import get_engine
from core.trace import logger


def fetch_sector_rotation_from_db(spot_df: pd.DataFrame) -> List[Dict]:
    """
    从数据库获取行业信息，结合spot数据计算板块涨跌

    Args:
        spot_df: spot数据DataFrame，必须包含code, price, change, pct_change等字段

    Returns:
        板块涨跌列表，按涨跌幅排序
    """
    try:
        # 标准化列名（兼容中英文列名）
        column_mapping = {
            '代码': 'code',
            '名称': 'name',
            '最新价': 'price',
            '涨跌幅': 'pct_change',
            '涨跌额': 'change',
        }

        # 重命名列
        spot_df = spot_df.rename(columns=column_mapping)

        # 确保必要的列存在
        required_cols = ['code', 'pct_change']
        missing = [c for c in required_cols if c not in spot_df.columns]
        if missing:
            logger.error(f"Missing required columns: {missing}, available: {list(spot_df.columns)}")
            return []

        # 1. 从数据库获取股票-行业映射
        engine = get_engine()
        if engine is None:
            logger.error("Database engine not available")
            return []
        query = """
        SELECT code, name, industry
        FROM stock_info
        WHERE industry IS NOT NULL
          AND industry != ''
          AND industry != '-'
          AND industry != '其他'
        """

        industry_df = pd.read_sql(query, engine)
        logger.info(f"Loaded {len(industry_df)} stocks with industry info")

        if industry_df.empty:
            logger.warning("No industry data found in database")
            return []

        # 2. 合并spot数据和行业数据
        merged = spot_df.merge(
            industry_df[['code', 'industry']],
            on='code',
            how='inner'
        )

        if merged.empty:
            logger.warning("No matching stocks after merge")
            return []

        logger.info(f"Merged {len(merged)} stocks with industry")

        # 3. 按行业分组统计
        sector_stats = merged.groupby('industry').agg({
            'code': 'count',  # 股票数量
            'pct_change': ['mean', 'sum'],  # 平均涨跌幅、总涨跌幅
            'price': 'sum',  # 总市值代理
        }).reset_index()

        # 重命名列
        sector_stats.columns = ['industry', 'stock_count', 'avg_change', 'total_change', 'total_price']

        # 4. 统计涨跌家数
        up_count = merged[merged['pct_change'] > 0].groupby('industry').size()
        down_count = merged[merged['pct_change'] < 0].groupby('industry').size()

        sector_stats['up_count'] = sector_stats['industry'].map(up_count).fillna(0).astype(int)
        sector_stats['down_count'] = sector_stats['industry'].map(down_count).fillna(0).astype(int)

        # 5. 计算涨跌比例
        sector_stats['up_ratio'] = (sector_stats['up_count'] / sector_stats['stock_count'] * 100).round(2)

        # 6. 过滤股票数量少的板块（至少5只股票）
        sector_stats = sector_stats[sector_stats['stock_count'] >= 5]

        # 7. 按平均涨跌幅排序
        sector_stats = sector_stats.sort_values('avg_change', ascending=False)

        # 8. 转换为API返回格式
        result = []
        for _, row in sector_stats.iterrows():
            result.append({
                'name': row['industry'],
                'change': round(row['avg_change'], 2),
                'stockCount': int(row['stock_count']),
                'upCount': int(row['up_count']),
                'downCount': int(row['down_count']),
                'upRatio': float(row['up_ratio']),
                'totalChange': round(row['total_change'], 2),
            })

        logger.info(f"Generated {len(result)} sector rotation records")
        return result

    except Exception as e:
        logger.error(f"Failed to fetch sector rotation: {e}", exc_info=True)
        return []


def get_top_sectors(spot_df: pd.DataFrame, limit: int = 20) -> List[Dict]:
    """
    获取涨幅前N的板块

    Args:
        spot_df: spot数据
        limit: 返回数量

    Returns:
        板块列表
    """
    sectors = fetch_sector_rotation_from_db(spot_df)
    return sectors[:limit]


def get_sector_stocks(spot_df: pd.DataFrame, sector_name: str, limit: int = 10) -> List[Dict]:
    """
    获取指定板块的股票列表

    Args:
        spot_df: spot数据
        sector_name: 板块名称
        limit: 返回数量

    Returns:
        股票列表
    """
    try:
        # 从数据库获取该板块的股票
        engine = get_engine()
        if engine is None:
            logger.error("Database engine not available")
            return []
        query = f"""
        SELECT code, name, industry
        FROM stock_info
        WHERE industry = '{sector_name}'
        """

        industry_df = pd.read_sql(query, engine)

        if industry_df.empty:
            return []

        # 合并spot数据
        merged = spot_df.merge(industry_df[['code']], on='code', how='inner')

        # 按涨跌幅排序
        merged = merged.sort_values('pct_change', ascending=False)

        # 返回前N只
        result = []
        for _, row in merged.head(limit).iterrows():
            result.append({
                'code': row['code'],
                'name': row['name'],
                'price': float(row.get('price', 0)),
                'change': float(row.get('pct_change', 0)),
            })

        return result

    except Exception as e:
        logger.error(f"Failed to get sector stocks: {e}")
        return []


if __name__ == '__main__':
    # 测试代码
    from app import fetch_spot

    print("Testing sector rotation...")
    spot = fetch_spot()
    print(f"Loaded {len(spot)} stocks")

    sectors = fetch_sector_rotation_from_db(spot)
    print(f"\nTop 10 sectors:")
    for i, sector in enumerate(sectors[:10], 1):
        print(f"{i}. {sector['name']}: {sector['change']:+.2f}% "
              f"({sector['upCount']}/{sector['stockCount']})")

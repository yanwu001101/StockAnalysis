# -*- coding: utf-8 -*-
"""Runtime schema migrations (idempotent).

MySQL's `CREATE TABLE IF NOT EXISTS` won't add columns to existing tables, and
Spring's schema init only covers fresh installs — so additive changes for
already-provisioned databases live here and run on every startup.
"""
from __future__ import annotations

from sqlalchemy import text

import db
from core.trace import logger

INDEX_KLINE_DDL = """
CREATE TABLE IF NOT EXISTS `index_kline_daily` (
    `code` VARCHAR(10) NOT NULL COMMENT '指数代码，如 000300',
    `trade_date` DATE NOT NULL,
    `open` DECIMAL(12,3),
    `close` DECIMAL(12,3),
    `high` DECIMAL(12,3),
    `low` DECIMAL(12,3),
    `volume` DECIMAL(20,2),
    `amount` DECIMAL(20,2),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `trade_date`),
    INDEX `idx_ikl_date` (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

PAPER_TABLES_DDL = """CREATE TABLE IF NOT EXISTS `paper_account` (
    `id` VARCHAR(40) PRIMARY KEY,
    `initial_capital` DECIMAL(20,2) NOT NULL,
    `top_n` INT NOT NULL DEFAULT 10,
    `rebalance` VARCHAR(16) NOT NULL DEFAULT 'weekly',
    `cash` DECIMAL(20,2) NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS `paper_positions` (
    `account_id` VARCHAR(40) NOT NULL,
    `code` VARCHAR(10) NOT NULL,
    `shares` DECIMAL(20,4) NOT NULL,
    `avg_cost` DECIMAL(12,3) NOT NULL,
    `buy_date` DATE,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`account_id`, `code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS `paper_trades` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `account_id` VARCHAR(40) NOT NULL,
    `trade_date` DATE NOT NULL,
    `code` VARCHAR(10) NOT NULL,
    `side` VARCHAR(8) NOT NULL,
    `shares` DECIMAL(20,4),
    `price` DECIMAL(12,3),
    `amount` DECIMAL(20,2),
    `cost` DECIMAL(20,2),
    `reason` VARCHAR(40),
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_ptrade_acc` (`account_id`, `trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS `paper_equity` (
    `account_id` VARCHAR(40) NOT NULL,
    `trade_date` DATE NOT NULL,
    `cash` DECIMAL(20,2),
    `positions_value` DECIMAL(20,2),
    `equity` DECIMAL(20,2),
    `benchmark_close` DECIMAL(12,3),
    PRIMARY KEY (`account_id`, `trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"""


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(
        text("SELECT COUNT(*) FROM information_schema.COLUMNS "
             "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"),
        {"t": table, "c": column},
    ).fetchone()
    return bool(row and row[0])


def ensure_schema() -> list[str]:
    """Apply additive migrations. Returns list of applied change descriptions."""
    applied: list[str] = []
    eng = db.get_engine()
    if eng is None:
        return applied
    try:
        with eng.begin() as conn:
            if not _column_exists(conn, "stock_fundamental", "ann_date"):
                conn.execute(text(
                    "ALTER TABLE stock_fundamental "
                    "ADD COLUMN ann_date DATE NULL "
                    "COMMENT '公告日期（point-in-time 可知时间）' AFTER report_date"
                ))
                applied.append("stock_fundamental.ann_date")
            conn.execute(text(INDEX_KLINE_DDL))
            # MySQL 驱动不支持一次执行分号分隔的多语句 — 逐条执行
            for stmt in [x.strip() for x in PAPER_TABLES_DDL.split(";") if x.strip()]:
                conn.execute(text(stmt))
        if applied:
            logger.info("[migrations] applied: %s", ", ".join(applied))
    except Exception as e:
        logger.warning("[migrations] ensure_schema failed: %s", e)
    return applied

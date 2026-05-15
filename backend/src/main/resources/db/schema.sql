-- A股智能选股平台 数据库建表
CREATE DATABASE IF NOT EXISTS stock_screener DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE stock_screener;

SET NAMES utf8mb4;

-- 用户表
CREATE TABLE IF NOT EXISTS `user` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `username` VARCHAR(50) NOT NULL,
    `password` VARCHAR(255) NOT NULL,
    `nickname` VARCHAR(100) NOT NULL DEFAULT '',
    `avatar` VARCHAR(500) NOT NULL DEFAULT '',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `deleted` TINYINT DEFAULT 0,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    INDEX `idx_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 自选股分组表
CREATE TABLE IF NOT EXISTS `watchlist_group` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `name` VARCHAR(100) NOT NULL DEFAULT 'default',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `deleted` TINYINT DEFAULT 0,
    PRIMARY KEY (`id`),
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 自选股表
CREATE TABLE IF NOT EXISTS `watchlist` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `group_id` BIGINT NOT NULL,
    `stock_code` VARCHAR(10) NOT NULL,
    `stock_name` VARCHAR(50) NOT NULL DEFAULT '',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `deleted` TINYINT DEFAULT 0,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_group_code` (`group_id`, `stock_code`),
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 用户策略配置表
CREATE TABLE IF NOT EXISTS `user_strategy` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `config_json` TEXT NOT NULL,
    `filter_json` TEXT,
    `is_default` TINYINT DEFAULT 0,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `deleted` TINYINT DEFAULT 0,
    PRIMARY KEY (`id`),
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 回测记录表
CREATE TABLE IF NOT EXISTS `backtest_record` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `user_id` BIGINT NOT NULL,
    `strategy_id` BIGINT,
    `start_date` DATE NOT NULL,
    `end_date` DATE NOT NULL,
    `initial_capital` DECIMAL(15,2) NOT NULL,
    `top_n` INT DEFAULT 10,
    `total_return` DECIMAL(10,4),
    `annualized_return` DECIMAL(10,4),
    `max_drawdown` DECIMAL(10,4),
    `sharpe_ratio` DECIMAL(10,4),
    `win_rate` DECIMAL(10,4),
    `trade_count` INT DEFAULT 0,
    `equity_curve_json` LONGTEXT,
    `trades_json` LONGTEXT,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `deleted` TINYINT DEFAULT 0,
    PRIMARY KEY (`id`),
    INDEX `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 股票基础信息缓存表
CREATE TABLE IF NOT EXISTS `stock_info` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(10) NOT NULL,
    `name` VARCHAR(50) NOT NULL,
    `industry` VARCHAR(50) NOT NULL DEFAULT '',
    `market_cap` DECIMAL(15,2) DEFAULT 0,
    `latest_price` DECIMAL(10,2) DEFAULT 0,
    `roe` DECIMAL(10,2) DEFAULT 0,
    `debt_ratio` DECIMAL(10,2) DEFAULT 0,
    `revenue_growth` DECIMAL(10,2) DEFAULT 0,
    `profit_growth` DECIMAL(10,2) DEFAULT 0,
    `cash_flow` DECIMAL(10,4) DEFAULT 0,
    `gross_margin` DECIMAL(10,2) DEFAULT 0,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE INDEX `idx_code` (`code`),
    INDEX `idx_industry` (`industry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------- K 线 / 财务历史持久化（Phase 2 添加） ----------

CREATE TABLE IF NOT EXISTS `stock_kline_daily` (
    `code` VARCHAR(10) NOT NULL,
    `trade_date` DATE NOT NULL,
    `open` DECIMAL(10,3),
    `close` DECIMAL(10,3),
    `high` DECIMAL(10,3),
    `low` DECIMAL(10,3),
    `volume` BIGINT,
    `amount` DECIMAL(20,2),
    `pct_change` DECIMAL(8,4),
    `turnover` DECIMAL(8,4),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `trade_date`),
    INDEX `idx_kdaily_date` (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `stock_kline_weekly` (
    `code` VARCHAR(10) NOT NULL,
    `trade_date` DATE NOT NULL,
    `open` DECIMAL(10,3),
    `close` DECIMAL(10,3),
    `high` DECIMAL(10,3),
    `low` DECIMAL(10,3),
    `volume` BIGINT,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `trade_date`),
    INDEX `idx_kweekly_date` (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

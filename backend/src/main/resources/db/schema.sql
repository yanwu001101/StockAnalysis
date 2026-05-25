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

-- ---------- Phase 3: 多源数据扩展（分钟K/财务/资金流/北向/龙虎榜/股东/分红/概念/公告） ----------

-- 分钟级 K 线（5/15/30/60min）
CREATE TABLE IF NOT EXISTS `stock_kline_minute` (
    `code` VARCHAR(10) NOT NULL,
    `dt` DATETIME NOT NULL,
    `period` VARCHAR(8) NOT NULL DEFAULT '5min',
    `open` DECIMAL(10,3),
    `close` DECIMAL(10,3),
    `high` DECIMAL(10,3),
    `low` DECIMAL(10,3),
    `volume` BIGINT,
    `amount` DECIMAL(20,2),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `dt`, `period`),
    INDEX `idx_kmin_dt` (`dt`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 财务三表 + 关键比率（合并视图，季度/年度）
CREATE TABLE IF NOT EXISTS `stock_fundamental` (
    `code` VARCHAR(10) NOT NULL,
    `report_date` DATE NOT NULL,
    `period_type` VARCHAR(8) NOT NULL DEFAULT 'Q',
    `revenue` DECIMAL(20,2),
    `net_profit` DECIMAL(20,2),
    `op_cashflow` DECIMAL(20,2),
    `ebit` DECIMAL(20,2),
    `total_assets` DECIMAL(20,2),
    `total_liab` DECIMAL(20,2),
    `total_equity` DECIMAL(20,2),
    `current_assets` DECIMAL(20,2),
    `current_liab` DECIMAL(20,2),
    `fixed_assets` DECIMAL(20,2),
    `roe` DECIMAL(10,4),
    `gross_margin` DECIMAL(10,4),
    `debt_ratio` DECIMAL(10,4),
    `current_ratio` DECIMAL(10,4),
    `revenue_yoy` DECIMAL(10,4),
    `net_profit_yoy` DECIMAL(10,4),
    `eps` DECIMAL(10,4),
    `bvps` DECIMAL(10,4),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `report_date`, `period_type`),
    INDEX `idx_fund_date` (`report_date`),
    INDEX `idx_fund_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 个股资金流（主力 + 超大/大/中/小单净额，单位：万元）
CREATE TABLE IF NOT EXISTS `stock_moneyflow` (
    `code` VARCHAR(10) NOT NULL,
    `trade_date` DATE NOT NULL,
    `super_large_net` DECIMAL(20,2),
    `large_net` DECIMAL(20,2),
    `medium_net` DECIMAL(20,2),
    `small_net` DECIMAL(20,2),
    `main_net` DECIMAL(20,2),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `trade_date`),
    INDEX `idx_mf_date` (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 沪深股通持股明细（北向资金）
CREATE TABLE IF NOT EXISTS `stock_northbound` (
    `code` VARCHAR(10) NOT NULL,
    `trade_date` DATE NOT NULL,
    `hold_shares` BIGINT,
    `hold_market_cap` DECIMAL(20,2),
    `hold_ratio` DECIMAL(10,4),
    `net_buy` DECIMAL(20,2),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `trade_date`),
    INDEX `idx_nb_date` (`trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 龙虎榜（每个上榜原因 + 席位为一行）
CREATE TABLE IF NOT EXISTS `stock_lhb` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(10) NOT NULL,
    `trade_date` DATE NOT NULL,
    `reason` VARCHAR(200) NOT NULL DEFAULT '',
    `buy_amount` DECIMAL(20,2),
    `sell_amount` DECIMAL(20,2),
    `net_amount` DECIMAL(20,2),
    `seat_type` VARCHAR(20) DEFAULT '',
    `seat_name` VARCHAR(200) DEFAULT '',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_lhb_seat` (`code`, `trade_date`, `reason`, `seat_name`),
    INDEX `idx_lhb_date` (`trade_date`),
    INDEX `idx_lhb_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 股东户数 + 集中度
CREATE TABLE IF NOT EXISTS `stock_shareholder` (
    `code` VARCHAR(10) NOT NULL,
    `report_date` DATE NOT NULL,
    `holder_count` BIGINT,
    `top10_ratio` DECIMAL(10,4),
    `institution_ratio` DECIMAL(10,4),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `report_date`),
    INDEX `idx_sh_date` (`report_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 分红送转
CREATE TABLE IF NOT EXISTS `stock_dividend` (
    `code` VARCHAR(10) NOT NULL,
    `ann_date` DATE NOT NULL,
    `ex_date` DATE,
    `cash_per_10` DECIMAL(10,4),
    `share_per_10` DECIMAL(10,4),
    `transfer_per_10` DECIMAL(10,4),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `ann_date`),
    INDEX `idx_div_ex_date` (`ex_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 概念板块成分
CREATE TABLE IF NOT EXISTS `stock_concept` (
    `concept_code` VARCHAR(20) NOT NULL,
    `concept_name` VARCHAR(100) NOT NULL,
    `code` VARCHAR(10) NOT NULL,
    `weight` DECIMAL(10,4),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`concept_code`, `code`),
    INDEX `idx_concept_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 公告
CREATE TABLE IF NOT EXISTS `stock_announcement` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(10) NOT NULL,
    `ann_date` DATE NOT NULL,
    `title` VARCHAR(500) NOT NULL,
    `type` VARCHAR(50) DEFAULT '',
    `url` VARCHAR(500) DEFAULT '',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ann_code_title` (`code`, `ann_date`, `title`(190)),
    INDEX `idx_ann_date` (`ann_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 策略评分 (预扫描结果) — 给仪表盘各策略 Top 榜用,毫秒级 SELECT
CREATE TABLE IF NOT EXISTS `stock_strategy_score` (
    `code`        VARCHAR(10)  NOT NULL,
    `strategy_id` VARCHAR(40)  NOT NULL,
    `score`       DECIMAL(6,2) NOT NULL,
    `signal_type` VARCHAR(10)  DEFAULT 'neutral',
    `triggered`   TINYINT(1)   DEFAULT 0,
    `computed_at` DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `strategy_id`),
    KEY `idx_strat_score` (`strategy_id`, `score`),
    KEY `idx_computed` (`computed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

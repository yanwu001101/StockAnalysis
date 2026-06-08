package com.stock.config;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.util.List;

/**
 * Phase 4 admin module schema migration. Idempotent — safe on every boot.
 * Uses information_schema probes (works on MySQL 5.7+ unlike ADD COLUMN IF NOT EXISTS).
 */
@Component
public class SchemaMigration {

    private static final Logger log = LoggerFactory.getLogger(SchemaMigration.class);

    private final JdbcTemplate jdbc;

    public SchemaMigration(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
    }

    @PostConstruct
    public void apply() {
        try {
            addUserAdminColumns();
            seedFirstAdmin();
            createAppConfigTable();
            createStockListTable();
            createAdminAuditLogTable();
            createBacktestRunTable();
            createPortfolioPositionTable();
            createUserAiConfigTable();
            createAiAnalysisRunTable();
            log.info("[migration] Phase4 admin schema applied");
        } catch (Exception e) {
            log.error("[migration] Phase4 admin schema failed: {}", e.getMessage(), e);
        }
    }

    private void addUserAdminColumns() {
        ensureColumn("user", "role", "VARCHAR(20) NOT NULL DEFAULT 'USER'", "avatar");
        ensureColumn("user", "status", "TINYINT NOT NULL DEFAULT 1", "role");
        ensureColumn("user", "last_login_at", "DATETIME NULL", "status");
        ensureColumn("user", "must_change_password", "TINYINT NOT NULL DEFAULT 0", "last_login_at");
    }

    private void seedFirstAdmin() {
        Integer cnt = jdbc.queryForObject(
            "SELECT COUNT(*) FROM `user` WHERE role = 'ADMIN'", Integer.class);
        if (cnt != null && cnt > 0) return;
        Integer firstId = jdbc.query(
            "SELECT id FROM `user` ORDER BY id ASC LIMIT 1",
            rs -> rs.next() ? rs.getInt(1) : null);
        if (firstId == null) return;
        jdbc.update("UPDATE `user` SET role = 'ADMIN' WHERE id = ? AND role = 'USER'", firstId);
        log.info("[migration] promoted user id={} to ADMIN", firstId);
    }

    private void createAppConfigTable() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS `app_config` (" +
            "`k` VARCHAR(64) NOT NULL," +
            "`v` TEXT NOT NULL," +
            "`description` VARCHAR(255) DEFAULT ''," +
            "`updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP," +
            "`updated_by` BIGINT," +
            "PRIMARY KEY (`k`)" +
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    }

    private void createStockListTable() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS `stock_list` (" +
            "`id` BIGINT NOT NULL AUTO_INCREMENT," +
            "`list_type` VARCHAR(20) NOT NULL," +
            "`code` VARCHAR(10) NOT NULL," +
            "`note` VARCHAR(255) DEFAULT ''," +
            "`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP," +
            "`created_by` BIGINT," +
            "PRIMARY KEY (`id`)," +
            "UNIQUE KEY `uk_type_code` (`list_type`, `code`)" +
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    }

    private void createAdminAuditLogTable() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS `admin_audit_log` (" +
            "`id` BIGINT NOT NULL AUTO_INCREMENT," +
            "`admin_id` BIGINT NOT NULL," +
            "`admin_name` VARCHAR(50) NOT NULL," +
            "`action` VARCHAR(64) NOT NULL," +
            "`target` VARCHAR(255) DEFAULT ''," +
            "`payload_json` TEXT," +
            "`ip` VARCHAR(64) DEFAULT ''," +
            "`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP," +
            "PRIMARY KEY (`id`)," +
            "INDEX `idx_admin_time` (`admin_id`, `created_at`)," +
            "INDEX `idx_action` (`action`)" +
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    }

    /** Per-user saved backtest runs (full snapshot). See BacktestHistoryController. */
    private void createBacktestRunTable() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS `backtest_run` (" +
            "`id` BIGINT NOT NULL AUTO_INCREMENT," +
            "`user_id` BIGINT NOT NULL," +
            "`name` VARCHAR(100) NOT NULL DEFAULT ''," +
            "`stock_code` VARCHAR(10) DEFAULT ''," +          // 空 = 组合回测
            "`strategy_id` VARCHAR(64) NOT NULL," +
            "`start_date` VARCHAR(10)," +
            "`end_date` VARCHAR(10)," +
            "`initial_capital` DOUBLE," +
            "`top_n` INT," +
            "`total_return` DOUBLE," +
            "`annualized_return` DOUBLE," +
            "`max_drawdown` DOUBLE," +
            "`sharpe_ratio` DOUBLE," +
            "`win_rate` DOUBLE," +
            "`trade_count` INT," +
            "`request_json` LONGTEXT," +                      // 原始请求(便于以后重跑)
            "`result_json` LONGTEXT," +                       // 扁平后的完整结果
            "`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP," +
            "PRIMARY KEY (`id`)," +
            "INDEX `idx_user_time` (`user_id`, `created_at`)" +
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    }

    /** Per-user manual/imported holdings used by the portfolio advice assistant. */
    private void createPortfolioPositionTable() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS `portfolio_position` (" +
            "`id` BIGINT NOT NULL AUTO_INCREMENT," +
            "`user_id` BIGINT NOT NULL," +
            "`code` VARCHAR(10) NOT NULL," +
            "`name` VARCHAR(50) NOT NULL DEFAULT ''," +
            "`shares` DECIMAL(18,2) NOT NULL DEFAULT 0," +
            "`available_shares` DECIMAL(18,2) NOT NULL DEFAULT 0," +
            "`avg_cost` DECIMAL(12,4) NOT NULL DEFAULT 0," +
            "`target_weight` DECIMAL(8,2) NOT NULL DEFAULT 20," +
            "`source` VARCHAR(20) NOT NULL DEFAULT 'manual'," +
            "`notes` VARCHAR(255) NOT NULL DEFAULT ''," +
            "`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP," +
            "`updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP," +
            "`deleted` TINYINT DEFAULT 0," +
            "PRIMARY KEY (`id`)," +
            "INDEX `idx_portfolio_code` (`user_id`, `code`)," +
            "INDEX `idx_portfolio_user` (`user_id`, `updated_at`)" +
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    }

    private void createUserAiConfigTable() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS `user_ai_config` (" +
            "`id` BIGINT NOT NULL AUTO_INCREMENT," +
            "`user_id` BIGINT NOT NULL," +
            "`provider` VARCHAR(40) NOT NULL DEFAULT 'openai-compatible'," +
            "`base_url` VARCHAR(255) NOT NULL DEFAULT ''," +
            "`model` VARCHAR(80) NOT NULL DEFAULT ''," +
            "`api_key_cipher` TEXT," +
            "`api_key_mask` VARCHAR(40) NOT NULL DEFAULT ''," +
            "`temperature` DECIMAL(4,2) NOT NULL DEFAULT 0.20," +
            "`enabled` TINYINT NOT NULL DEFAULT 0," +
            "`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP," +
            "`updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP," +
            "PRIMARY KEY (`id`)," +
            "UNIQUE KEY `uk_ai_user` (`user_id`)" +
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    }

    private void createAiAnalysisRunTable() {
        jdbc.execute(
            "CREATE TABLE IF NOT EXISTS `ai_analysis_run` (" +
            "`id` BIGINT NOT NULL AUTO_INCREMENT," +
            "`user_id` BIGINT NOT NULL," +
            "`scope` VARCHAR(40) NOT NULL DEFAULT 'portfolio'," +
            "`request_json` LONGTEXT," +
            "`result_text` LONGTEXT," +
            "`model` VARCHAR(80) NOT NULL DEFAULT ''," +
            "`feedback` VARCHAR(20) NOT NULL DEFAULT ''," +
            "`feedback_note` VARCHAR(500) NOT NULL DEFAULT ''," +
            "`created_at` DATETIME DEFAULT CURRENT_TIMESTAMP," +
            "PRIMARY KEY (`id`)," +
            "INDEX `idx_ai_user_time` (`user_id`, `created_at`)" +
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    }

    private void ensureColumn(String table, String column, String columnDef, String afterColumn) {
        List<String> existing = jdbc.queryForList(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS " +
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ? AND COLUMN_NAME = ?",
            String.class, table, column);
        if (!existing.isEmpty()) return;
        String sql = String.format("ALTER TABLE `%s` ADD COLUMN `%s` %s AFTER `%s`",
            table, column, columnDef, afterColumn);
        jdbc.execute(sql);
        log.info("[migration] added column {}.{}", table, column);
    }
}

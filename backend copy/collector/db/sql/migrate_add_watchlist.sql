-- Migration: Add user_watchlist table (2026-06-10)
-- For existing databases that were initialized before v4.1
-- Usage: psql -U quant_user -d quant_trading -f migrate_add_watchlist.sql

CREATE TABLE IF NOT EXISTS user_watchlist (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    code VARCHAR(10) NOT NULL,
    group_name VARCHAR(64) DEFAULT '默认分组',
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_watchlist_user_code ON user_watchlist(user_id, code);
CREATE INDEX IF NOT EXISTS idx_user_watchlist_user_id ON user_watchlist(user_id);

SELECT 'user_watchlist migration completed' AS status;
-- Migration: Add 14 technical indicator pattern columns to stock_daily_snapshot (2026-06-16)
-- For existing databases that were initialized before v4.2
-- Usage: psql -U quant_user -d quant_trading -f migrate_add_tech_patterns.sql

-- MA patterns
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS ma_long_align BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS ma_short_align BOOLEAN DEFAULT FALSE;

-- MACD patterns
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS macd_low_golden_cross BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS macd_bottom_divergence BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS macd_high_death_cross BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS macd_top_divergence BOOLEAN DEFAULT FALSE;

-- BOLL patterns
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS boll_break_upper BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS boll_break_middle_up BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS boll_break_middle_down BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS boll_break_lower BOOLEAN DEFAULT FALSE;

-- RSI patterns
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS rsi_low_golden_cross BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS rsi_high_death_cross BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS rsi_top_divergence BOOLEAN DEFAULT FALSE;
ALTER TABLE stock_daily_snapshot ADD COLUMN IF NOT EXISTS rsi_bottom_divergence BOOLEAN DEFAULT FALSE;

SELECT '14 technical pattern columns migration completed' AS status;

-- Migration: Support multi-group watchlist (2026-07-08)
-- Change: UNIQUE constraint (user_id, code) → (user_id, code, group_name)
--         Add is_system column for system-managed groups
-- Usage: psql -U quant_user -d quant_trading -f migrate_watchlist_multi_group.sql

BEGIN;

-- 1. Drop old unique constraint
ALTER TABLE user_watchlist DROP CONSTRAINT IF EXISTS uq_user_watchlist_user_code;
DROP INDEX IF EXISTS uq_user_watchlist_user_code;

-- 2. Add is_system column (system groups like 全部/沪深/港股/美股 are not deletable)
ALTER TABLE user_watchlist ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT FALSE;

-- 3. Add new unique constraint on (user_id, code, group_name)
--    This allows the same stock in multiple groups
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_watchlist_user_code_group
    ON user_watchlist(user_id, code, group_name);

-- 4. Migrate existing data: set is_system = TRUE for "默认分组" (treated as system default)
UPDATE user_watchlist SET is_system = TRUE WHERE group_name = '默认分组';

COMMIT;

SELECT 'watchlist multi-group migration completed' AS status;
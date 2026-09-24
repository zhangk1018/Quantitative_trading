-- =====================================================================
-- V014: 多用户账号体系 - 新增 users 表 + migration_flags 表
-- 协作单: [42.0-AUTH-20260924]
-- 幂等性: CREATE TABLE IF NOT EXISTS，可重复执行。
-- 数据库: PostgreSQL 18.6
-- 兼容性: 新增表，不影响既有表。
-- =====================================================================
-- 破坏性声明: DROP TABLE users 不可逆、执行前需备份库；
-- 老自选股（user_id='default'）迁移在应用首启 bootstrap 执行（见 §6），
-- 回滚无法还原为 default，需一并知晓。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. users 表
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id             SERIAL PRIMARY KEY,
    username       VARCHAR(64)  NOT NULL UNIQUE,      -- 登录名，天然唯一索引
    password_hash  VARCHAR(128) NOT NULL,             -- pbkdf2: salt$iterations$hash
    display_name   VARCHAR(64),
    role           VARCHAR(16)  NOT NULL DEFAULT 'user',  -- admin | user
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    token_version  INT          NOT NULL DEFAULT 1,       -- 改密/重置/禁用时 +1
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    last_login_at  TIMESTAMP
);

-- 用户名唯一索引（登录查询走该索引）
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON users(username);

-- ---------------------------------------------------------------------
-- 2. migration_flags 表（bootstrap 一次性迁移标记，防重复执行）
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS migration_flags (
    flag_name    VARCHAR(64) PRIMARY KEY,
    executed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 校验：确认 users 表结构
-- =====================================================================
SELECT c.column_name, c.data_type
FROM information_schema.columns c
WHERE c.table_schema = 'public' AND c.table_name = 'users'
ORDER BY c.ordinal_position;
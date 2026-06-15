-- ==========================================
-- 数据迁移脚本：v2.x / v3.0 / v3.1 → v3.2
-- ==========================================
-- 目的：将已部署的数据库（支持 v2.x / v3.0 / v3.1）升级到 v3.2
--       自动检测版本并执行相应的迁移步骤
-- 适用起点：
--   - stock_quotes / stock_indicators 已是月度分区表
--   - 字段名已统一为 trade_datetime（v3.x）或 trade_date（v2.x）
-- 数据库要求：
--   - PostgreSQL >= 11（项目实际生产版本）
--   - 推荐在低峰期执行
-- 涉及变更（v3.2 核心修正）：
--   1) ACTION-1：sync_checkpoints 加 last_continuous_sync_datetime / is_continuous 列
--   2) ACTION-4：stock_quotes / stock_indicators 加 idx_*_code_time 跨周期扫描索引
--   3) RULE-3.1：移除 BIGSERIAL id，改用 (code, cycle, trade_datetime) 联合主键
--   4) RULE-3.2：stock_quotes_dirty.raw_data 从 JSONB 降级为 JSON
--   5) ACTION-2 / ACTION-3 是 process 层/代码层修正，无需 schema 迁移
--      （process 修正见 scripts/partition_maintenance.sql v3.2 封版；
--        代码修正见 src/utils/data_sync_utils.py v1.3 封版）
-- 执行方式（生产推荐）：
--   psql -h <host> -p 5432 -U quant_user -d quant_trading 
--        -v ON_ERROR_STOP=1 -f scripts/migrate_v3_to_v3.2.sql
-- 幂等性：可重复执行，不会重复加列/加索引/重建约束
-- 大表注意事项：
--   stock_quotes / stock_indicators 已有上亿行记录
--   本脚本使用 CREATE INDEX CONCURRENTLY 避免锁表，但执行时间较长
--   建议先执行 EXPLAIN 分析，并在低峰期执行
-- 作者：量量（AI 助手）
-- 日期：2026-06-02
-- 关联文档：
--   - data/DATA_SCHEMA.md（v3.2 变更记录）
--   - backend/collector/db/sql/init_db.sql（v3.2 封版基线）
-- ==========================================

\set ON_ERROR_STOP on
SET client_min_messages = WARNING;

-- ==========================================
-- 1. 前置检查与版本检测
-- ==========================================
-- 全局变量：检测到的数据库版本
\set db_version 'unknown'

DO $$
DECLARE
    v_pg_version INTEGER;
    v_quotes_exists BOOLEAN;
    v_indicators_exists BOOLEAN;
    v_checkpoint_exists BOOLEAN;
    v_dirty_exists BOOLEAN;
    v_min_pg_version CONSTANT INTEGER := 110000;
BEGIN
    v_pg_version := current_setting('server_version_num')::INTEGER;
    IF v_pg_version < v_min_pg_version THEN
        RAISE EXCEPTION '当前 PG 版本 % 低于要求的最低版本 %', v_pg_version, v_min_pg_version;
    END IF;
    RAISE NOTICE '[CHECK] PG 版本检查通过: %', v_pg_version;

    SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'stock_quotes')
        INTO v_quotes_exists;
    SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'stock_indicators')
        INTO v_indicators_exists;
    SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'sync_checkpoints')
        INTO v_checkpoint_exists;
    SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'stock_quotes_dirty')
        INTO v_dirty_exists;

    IF NOT v_quotes_exists THEN
        RAISE EXCEPTION '前置表 stock_quotes 不存在';
    END IF;
    IF NOT v_indicators_exists THEN
        RAISE EXCEPTION '前置表 stock_indicators 不存在';
    END IF;

    -- 版本检测逻辑
    IF v_checkpoint_exists AND v_dirty_exists THEN
        RAISE NOTICE '[CHECK] 检测到 v3.x 版本（sync_checkpoints 和 stock_quotes_dirty 已存在）';
        PERFORM set_config('my.db_version', 'v3', false);
    ELSE
        RAISE NOTICE '[CHECK] 检测到 v2.x 版本（缺少 sync_checkpoints 或 stock_quotes_dirty）';
        PERFORM set_config('my.db_version', 'v2', false);
    END IF;

    RAISE NOTICE '[CHECK] 前置表齐全: stock_quotes / stock_indicators';
END;
$$;

-- 获取检测到的版本
SELECT current_setting('my.db_version') AS detected_db_version;

-- ==========================================
-- 2. v2.x → v3.0 升级：创建缺失的表
-- ==========================================
-- 如果是 v2.x 版本，需要创建 v3.0 新增的表
DO $$
DECLARE
    v_db_version TEXT;
BEGIN
    v_db_version := current_setting('my.db_version');
    
    IF v_db_version = 'v2' THEN
        RAISE NOTICE '[v2->v3] 开始从 v2.x 升级到 v3.0...';
        
        -- 2.1 创建 stock_quotes_dirty 表（死信表）
        IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'stock_quotes_dirty') THEN
            CREATE TABLE stock_quotes_dirty (
                id BIGSERIAL PRIMARY KEY,
                code VARCHAR(10),
                cycle VARCHAR(10),
                trade_datetime TIMESTAMPTZ,
                raw_data JSON, -- [RULE-3.2] 降级为 JSON，极速写入
                error_type VARCHAR(50) NOT NULL,
                error_message TEXT NOT NULL,
                error_codes VARCHAR(200),
                source VARCHAR(50),
                fetch_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'pending',
                resolve_time TIMESTAMPTZ,
                resolve_note TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
            RAISE NOTICE '[v2->v3] 已创建 stock_quotes_dirty 表';
        ELSE
            RAISE NOTICE '[v2->v3] stock_quotes_dirty 表已存在，跳过';
        END IF;

        -- 2.2 创建 sync_checkpoints 表（水位线表）
        IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'sync_checkpoints') THEN
            CREATE TABLE sync_checkpoints (
                id BIGSERIAL PRIMARY KEY,
                code VARCHAR(10) NOT NULL,
                cycle VARCHAR(10) NOT NULL,
                last_sync_datetime TIMESTAMPTZ NOT NULL,
                last_continuous_sync_datetime TIMESTAMPTZ, -- [RULE-4.1] 连续水位线
                is_continuous BOOLEAN DEFAULT TRUE,
                sync_status VARCHAR(20) DEFAULT 'success',
                sync_count INTEGER DEFAULT 0,
                fail_reason TEXT,
                task_id VARCHAR(50),
                source VARCHAR(50),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(code, cycle)
            );
            RAISE NOTICE '[v2->v3] 已创建 sync_checkpoints 表';
        ELSE
            RAISE NOTICE '[v2->v3] sync_checkpoints 表已存在，跳过';
        END IF;

        RAISE NOTICE '[v2->v3] v2.x → v3.0 升级完成';
    END IF;
END;
$$;

-- ==========================================
-- 3. 字段升级：添加 trade_datetime（如果不存在）
-- ==========================================
-- 兼容 v2.x（无 trade_datetime）和 v3.x（已有 trade_datetime）
-- ⚠️ WARNING: 时间回填逻辑使用 trade_date::TIMESTAMP，不添加固定时间偏移
--             分钟线数据的具体时间应在数据同步时从数据源获取
--             此处仅做日期到时间戳的基础转换，避免破坏分钟线的精确时间
DO $$
DECLARE
    v_has_trade_datetime BOOLEAN;
    v_updated BIGINT := 0;
BEGIN
    RAISE NOTICE '[FIELD] 检查并添加 trade_datetime 字段...';
    
    -- 检查 stock_quotes 是否已有 trade_datetime 字段
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stock_quotes' AND column_name = 'trade_datetime'
    ) INTO v_has_trade_datetime;
    
    IF NOT v_has_trade_datetime THEN
        -- 添加 trade_datetime 字段（允许为空，后续回填）
        ALTER TABLE stock_quotes ADD COLUMN trade_datetime TIMESTAMPTZ;
        RAISE NOTICE '[FIELD] stock_quotes 已添加 trade_datetime 字段';
        
        -- 单次 UPDATE 回填数据（DO 块内不能用 COMMIT）
        -- ⚠️ 注意：使用 trade_date::TIMESTAMP 而非 + INTERVAL '09:30:00'
        --    分钟线数据需要保留精确时间，不能用固定开盘时间覆盖
        UPDATE stock_quotes
        SET trade_datetime = trade_date::TIMESTAMP
        WHERE trade_datetime IS NULL;
        
        GET DIAGNOSTICS v_updated = ROW_COUNT;
        ALTER TABLE stock_quotes ALTER COLUMN trade_datetime SET NOT NULL;
        RAISE NOTICE '[FIELD] stock_quotes trade_datetime 字段升级完成，共更新 % 行', v_updated;
    ELSE
        RAISE NOTICE '[FIELD] stock_quotes 已有 trade_datetime 字段，跳过';
    END IF;
    
    -- 检查 stock_indicators 是否已有 trade_datetime 字段
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'stock_indicators' AND column_name = 'trade_datetime'
    ) INTO v_has_trade_datetime;
    
    IF NOT v_has_trade_datetime THEN
        -- 添加 trade_datetime 字段（允许为空，后续回填）
        ALTER TABLE stock_indicators ADD COLUMN trade_datetime TIMESTAMPTZ;
        RAISE NOTICE '[FIELD] stock_indicators 已添加 trade_datetime 字段';
        
        -- 单次 UPDATE 回填数据
        UPDATE stock_indicators
        SET trade_datetime = trade_date::TIMESTAMP
        WHERE trade_datetime IS NULL;
        
        GET DIAGNOSTICS v_updated = ROW_COUNT;
        ALTER TABLE stock_indicators ALTER COLUMN trade_datetime SET NOT NULL;
        RAISE NOTICE '[FIELD] stock_indicators trade_datetime 字段升级完成，共更新 % 行', v_updated;
    ELSE
        RAISE NOTICE '[FIELD] stock_indicators 已有 trade_datetime 字段，跳过';
    END IF;
    
    RAISE NOTICE '[FIELD] 字段升级完成';
END;
$$;

-- ==========================================
-- 4. RULE-3.1：主键与唯一约束重构
-- ==========================================
-- 目标：
--   - 移除 BIGSERIAL id 列（节省 8 字节/行 + 1 个 B-Tree 索引）
--   - 使用 (code, cycle, trade_datetime) 作为联合主键
--   - 删除旧的唯一约束 uq_quotes_code_cycle_time / uq_indicators_code_cycle_time
-- ==========================================

-- 2.1 删除 stock_quotes 的旧主键约束
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'stock_quotes'::regclass 
        AND conname = 'stock_quotes_pkey'
    ) THEN
        ALTER TABLE stock_quotes DROP CONSTRAINT stock_quotes_pkey;
        RAISE NOTICE '[RULE-3.1] 已删除 stock_quotes 旧主键约束';
    ELSE
        RAISE NOTICE '[RULE-3.1] stock_quotes 旧主键约束不存在，跳过';
    END IF;
END;
$$;

-- 2.2 删除 stock_quotes 的旧唯一约束
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'stock_quotes'::regclass 
        AND conname = 'uq_quotes_code_cycle_time'
    ) THEN
        ALTER TABLE stock_quotes DROP CONSTRAINT uq_quotes_code_cycle_time;
        RAISE NOTICE '[RULE-3.1] 已删除 stock_quotes 旧唯一约束 uq_quotes_code_cycle_time';
    ELSE
        RAISE NOTICE '[RULE-3.1] stock_quotes 旧唯一约束不存在，跳过';
    END IF;
END;
$$;

-- 2.3 删除 stock_indicators 的旧主键约束
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'stock_indicators'::regclass 
        AND conname = 'stock_indicators_pkey'
    ) THEN
        ALTER TABLE stock_indicators DROP CONSTRAINT stock_indicators_pkey;
        RAISE NOTICE '[RULE-3.1] 已删除 stock_indicators 旧主键约束';
    ELSE
        RAISE NOTICE '[RULE-3.1] stock_indicators 旧主键约束不存在，跳过';
    END IF;
END;
$$;

-- 2.4 删除 stock_indicators 的旧唯一约束
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'stock_indicators'::regclass 
        AND conname = 'uq_indicators_code_cycle_time'
    ) THEN
        ALTER TABLE stock_indicators DROP CONSTRAINT uq_indicators_code_cycle_time;
        RAISE NOTICE '[RULE-3.1] 已删除 stock_indicators 旧唯一约束 uq_indicators_code_cycle_time';
    ELSE
        RAISE NOTICE '[RULE-3.1] stock_indicators 旧唯一约束不存在，跳过';
    END IF;
END;
$$;

-- 2.5 为 stock_quotes 建立新主键 (code, cycle, trade_datetime)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'stock_quotes'::regclass 
        AND conname = 'stock_quotes_pkey'
        AND conkey = ARRAY[
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_quotes'::regclass AND attname = 'code'),
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_quotes'::regclass AND attname = 'cycle'),
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_quotes'::regclass AND attname = 'trade_datetime')
        ]
    ) THEN
        ALTER TABLE stock_quotes ADD PRIMARY KEY (code, cycle, trade_datetime);
        RAISE NOTICE '[RULE-3.1] 已为 stock_quotes 建立新主键 (code, cycle, trade_datetime)';
    ELSE
        RAISE NOTICE '[RULE-3.1] stock_quotes 新主键已存在，跳过';
    END IF;
END;
$$;

-- 2.6 为 stock_indicators 建立新主键 (code, cycle, trade_datetime)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'stock_indicators'::regclass 
        AND conname = 'stock_indicators_pkey'
        AND conkey = ARRAY[
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_indicators'::regclass AND attname = 'code'),
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_indicators'::regclass AND attname = 'cycle'),
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_indicators'::regclass AND attname = 'trade_datetime')
        ]
    ) THEN
        ALTER TABLE stock_indicators ADD PRIMARY KEY (code, cycle, trade_datetime);
        RAISE NOTICE '[RULE-3.1] 已为 stock_indicators 建立新主键 (code, cycle, trade_datetime)';
    ELSE
        RAISE NOTICE '[RULE-3.1] stock_indicators 新主键已存在，跳过';
    END IF;
END;
$$;

-- 2.7 物理删除冗余的 id 列（在新主键建立后执行）
ALTER TABLE stock_quotes DROP COLUMN IF EXISTS id;
ALTER TABLE stock_indicators DROP COLUMN IF EXISTS id;

-- ==========================================
-- 3. RULE-3.2：死信表字段类型降级 (JSONB → JSON)
-- ==========================================
-- 目标：将 stock_quotes_dirty.raw_data 从 JSONB 降级为 JSON
--   - JSON 写入时不做格式校验和 TOAST 压缩
--   - 符合死信表"极速旁路写入"的设计初衷
-- ==========================================

DO $$
DECLARE
    v_current_type TEXT;
BEGIN
    -- 检查当前字段类型
    SELECT data_type INTO v_current_type
    FROM information_schema.columns
    WHERE table_name = 'stock_quotes_dirty'
    AND column_name = 'raw_data';

    IF v_current_type = 'jsonb' THEN
        -- JSONB → JSON 转换（需要中间步骤）
        ALTER TABLE stock_quotes_dirty 
        ALTER COLUMN raw_data TYPE JSON 
        USING raw_data::text::json;
        RAISE NOTICE '[RULE-3.2] 已将 stock_quotes_dirty.raw_data 从 JSONB 降级为 JSON';
    ELSIF v_current_type = 'json' THEN
        RAISE NOTICE '[RULE-3.2] stock_quotes_dirty.raw_data 已是 JSON 类型，跳过';
    ELSE
        RAISE WARNING '[RULE-3.2] stock_quotes_dirty.raw_data 类型未知: %', v_current_type;
    END IF;
END;
$$;

-- ==========================================
-- 4. ACTION-1：sync_checkpoints 表结构升级
-- ==========================================
-- 新增两个字段：
--   - last_continuous_sync_datetime：最后连续同步时间（无断层的最远点）
--   - is_continuous：是否连续（默认 TRUE）
-- ==========================================

-- 4.1 添加新列（PG 9.6+ 支持 IF NOT EXISTS）
ALTER TABLE sync_checkpoints
ADD COLUMN IF NOT EXISTS last_continuous_sync_datetime TIMESTAMPTZ;

ALTER TABLE sync_checkpoints
ADD COLUMN IF NOT EXISTS is_continuous BOOLEAN DEFAULT TRUE;

-- 4.2 补全字段注释（重复执行会被 PG 覆盖，无副作用）
COMMENT ON COLUMN sync_checkpoints.last_continuous_sync_datetime
IS '最后连续同步时间，记录无数据断层的最远同步点（ACTION-1）';

COMMENT ON COLUMN sync_checkpoints.is_continuous
IS '是否连续：TRUE-数据连续，FALSE-存在断层（ACTION-1，断层时 last_sync_datetime 不推进）';

-- 4.3 数据回填：把已有记录视为"连续"，并把 last_sync_datetime 同步到 last_continuous_sync_datetime
--     边界处理：仅对 last_continuous_sync_datetime IS NULL 的记录做回填（幂等）
UPDATE sync_checkpoints
SET last_continuous_sync_datetime = last_sync_datetime
WHERE last_continuous_sync_datetime IS NULL;

-- 4.4 触发表结构健康检查
DO $$
DECLARE
    v_continuous_count BIGINT;
    v_total_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_total_count FROM sync_checkpoints;
    SELECT COUNT(*) INTO v_continuous_count
    FROM sync_checkpoints WHERE last_continuous_sync_datetime IS NOT NULL;
    
    IF v_total_count > 0 AND v_continuous_count < v_total_count THEN
        RAISE WARNING '[ACTION-1] 回填未完成: total=%, filled=%', v_total_count, v_continuous_count;
    ELSE
        RAISE NOTICE '[ACTION-1] sync_checkpoints 升级完成: total=%, filled=%', v_total_count, v_continuous_count;
    END IF;
END;
$$;

-- ==========================================
-- 5. ACTION-4：跨周期时间范围扫描专用索引（单独事务执行）
-- ==========================================
-- ⚠️ 重要：CREATE INDEX CONCURRENTLY 不能在事务块中执行
--   因此这部分单独放在 DO 块外面执行
--   使用 IF NOT EXISTS 保证幂等性（PG 11+ 原生支持）
-- ==========================================

-- 5.1 stock_quotes 索引（使用 CONCURRENTLY，避免锁表）
\echo '[ACTION-4] 创建 idx_quotes_code_time (CONCURRENTLY)...'
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_quotes_code_time 
    ON stock_quotes (code, trade_datetime);
\echo '[ACTION-4] idx_quotes_code_time 创建完成或已存在'

-- 5.2 stock_indicators 索引（使用 CONCURRENTLY，避免锁表）
\echo '[ACTION-4] 创建 idx_indicators_code_time (CONCURRENTLY)...'
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_indicators_code_time 
    ON stock_indicators (code, trade_datetime);
\echo '[ACTION-4] idx_indicators_code_time 创建完成或已存在'

-- ==========================================
-- 6. 后置验证
-- ==========================================
DO $$
DECLARE
    v_col_continuous BOOLEAN;
    v_col_is_cont BOOLEAN;
    v_idx_quotes BOOLEAN;
    v_idx_indicators BOOLEAN;
    v_new_pkey_quotes BOOLEAN;
    v_new_pkey_indicators BOOLEAN;
    v_raw_data_type TEXT;
BEGIN
    -- 列存在性
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sync_checkpoints'
        AND column_name = 'last_continuous_sync_datetime'
    ) INTO v_col_continuous;
    
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sync_checkpoints'
        AND column_name = 'is_continuous'
    ) INTO v_col_is_cont;

    -- 索引存在性
    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'idx_quotes_code_time'
    ) INTO v_idx_quotes;

    SELECT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'idx_indicators_code_time'
    ) INTO v_idx_indicators;

    -- 新主键存在性
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'stock_quotes'::regclass
        AND contype = 'p'
        AND conkey = ARRAY[
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_quotes'::regclass AND attname = 'code'),
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_quotes'::regclass AND attname = 'cycle'),
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_quotes'::regclass AND attname = 'trade_datetime')
        ]
    ) INTO v_new_pkey_quotes;

    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'stock_indicators'::regclass
        AND contype = 'p'
        AND conkey = ARRAY[
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_indicators'::regclass AND attname = 'code'),
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_indicators'::regclass AND attname = 'cycle'),
            (SELECT attnum FROM pg_attribute WHERE attrelid = 'stock_indicators'::regclass AND attname = 'trade_datetime')
        ]
    ) INTO v_new_pkey_indicators;

    -- raw_data 类型
    SELECT data_type INTO v_raw_data_type
    FROM information_schema.columns
    WHERE table_name = 'stock_quotes_dirty'
    AND column_name = 'raw_data';

    -- 综合验证
    IF NOT (v_col_continuous AND v_col_is_cont AND v_idx_quotes AND v_idx_indicators 
            AND v_new_pkey_quotes AND v_new_pkey_indicators AND v_raw_data_type = 'json') THEN
        RAISE WARNING '[VERIFY] 迁移未完整: cols(continuous=%, is_cont=%), idx(quotes=%, indicators=%), pkey(quotes=%, indicators=%), raw_data_type=%',
            v_col_continuous, v_col_is_cont, v_idx_quotes, v_idx_indicators, 
            v_new_pkey_quotes, v_new_pkey_indicators, v_raw_data_type;
    ELSE
        RAISE NOTICE '[VERIFY] ✅ v3.0 → v3.2 迁移全部完成';
        RAISE NOTICE '[VERIFY]   - RULE-3.1: 主键重构完成 (移除 id，使用联合主键)';
        RAISE NOTICE '[VERIFY]   - RULE-3.2: stock_quotes_dirty.raw_data 降级为 JSON';
        RAISE NOTICE '[VERIFY]   - ACTION-1: sync_checkpoints 新增 2 列 + 回填完成';
        RAISE NOTICE '[VERIFY]   - ACTION-4: stock_quotes / stock_indicators 各加 1 个跨周期索引 (CONCURRENTLY)';
        RAISE NOTICE '[VERIFY]   - ACTION-2 / ACTION-3 为 process/代码层修正，无需 schema 迁移';
    END IF;
END;
$$;

-- ==========================================
-- 7. ROLLBACK 段（如需回滚，按顺序手动执行下列语句）
-- ==========================================
-- ⚠️ 警告：回滚前请先备份数据！
-- 7.1 删除 ACTION-4 新增的索引
-- DROP INDEX CONCURRENTLY IF EXISTS idx_indicators_code_time;
-- DROP INDEX CONCURRENTLY IF EXISTS idx_quotes_code_time;

-- 7.2 删除 RULE-3.1 新增的主键（恢复旧主键需要重建 id 列，复杂操作）
-- ALTER TABLE stock_indicators DROP CONSTRAINT stock_indicators_pkey;
-- ALTER TABLE stock_quotes DROP CONSTRAINT stock_quotes_pkey;
-- ALTER TABLE stock_indicators ADD PRIMARY KEY (id, trade_datetime);
-- ALTER TABLE stock_quotes ADD PRIMARY KEY (id, trade_datetime);
-- ALTER TABLE stock_indicators ADD CONSTRAINT uq_indicators_code_cycle_time UNIQUE (code, cycle, trade_datetime);
-- ALTER TABLE stock_quotes ADD CONSTRAINT uq_quotes_code_cycle_time UNIQUE (code, cycle, trade_datetime);

-- 7.3 删除 RULE-3.2 的字段类型变更（JSON → JSONB）
-- ALTER TABLE stock_quotes_dirty ALTER COLUMN raw_data TYPE JSONB USING raw_data::jsonb;

-- 7.4 删除 ACTION-1 新增的列
-- ALTER TABLE sync_checkpoints DROP COLUMN IF EXISTS is_continuous;
-- ALTER TABLE sync_checkpoints DROP COLUMN IF EXISTS last_continuous_sync_datetime;

-- 7.5 验证回滚结果
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'sync_checkpoints'
--   AND column_name IN ('last_continuous_sync_datetime', 'is_continuous');
-- 预期：返回 0 行

-- SELECT indexname FROM pg_indexes
-- WHERE indexname IN ('idx_quotes_code_time', 'idx_indicators_code_time');
-- 预期：返回 0 行
-- ==========================================

SELECT 'migrate_v3_to_v3.2.sql 执行完毕' AS final_status;
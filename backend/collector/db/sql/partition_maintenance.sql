-- ==========================================
-- 分区维护脚本（v3.2 最终封版）
-- ==========================================

CREATE OR REPLACE FUNCTION pg_version_supports_concurrent_detach() RETURNS BOOLEAN LANGUAGE sql AS $$
SELECT current_setting('server_version_num')::INTEGER >= 140000;
$$;

CREATE OR REPLACE FUNCTION validate_identifier_length(p_identifier TEXT) RETURNS BOOLEAN LANGUAGE plpgsql AS $$
BEGIN RETURN length(p_identifier) <= 63; END;
$$;

-- ==========================================
-- 1. 添加单个月度分区
-- ==========================================
CREATE OR REPLACE PROCEDURE add_month_partition(
    p_table_name TEXT, p_year INTEGER, p_month INTEGER, p_silent BOOLEAN DEFAULT FALSE
) LANGUAGE plpgsql AS $$
DECLARE
    v_partition_name TEXT;
    v_start_date TIMESTAMPTZ;
    v_end_date TIMESTAMPTZ;
    v_pg_version INTEGER;
BEGIN
    v_month_str := LPAD(p_month::TEXT, 2, '0');
    v_partition_name := p_table_name || '_y' || p_year || 'm' || v_month_str;
    v_pg_version := current_setting('server_version_num')::INTEGER;

    IF NOT validate_identifier_length(v_partition_name) THEN
        RAISE EXCEPTION 'Partition name "%" exceeds maximum length of 63 characters', v_partition_name;
    END IF;

    v_start_date := make_timestamptz(p_year, p_month, 1, 0, 0, 0, 'Asia/Shanghai');
    v_end_date := v_start_date + INTERVAL '1 month';

    IF NOT EXISTS (
        SELECT 1 FROM pg_inherits JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        WHERE parent.relname = p_table_name AND child.relname = v_partition_name
    ) THEN
        IF NOT p_silent THEN RAISE NOTICE 'Creating partition %', v_partition_name; END IF;
        
        EXECUTE format('CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)', v_partition_name, p_table_name, v_start_date, v_end_date);
        
        -- [ACTION-2] 仅在 PG 10 环境下显式绑定子分区触发器，PG 11+ 依赖父表自动传播
        IF v_pg_version < 110000 THEN
            IF EXISTS (
                SELECT 1 FROM pg_trigger t JOIN pg_class c ON t.tgrelid = c.oid
                WHERE c.relname = p_table_name AND t.tgname = ('trg_' || p_table_name || '_updated_at')
            ) THEN
                EXECUTE format('CREATE TRIGGER trg_%I_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at()', v_partition_name, v_partition_name);
            END IF;
        END IF;
    ELSE
        IF NOT p_silent THEN RAISE NOTICE 'Partition % already exists', v_partition_name; END IF;
    END IF;
END;
$$;

-- ==========================================
-- 2. 批量添加月度分区
-- ==========================================
CREATE OR REPLACE PROCEDURE add_month_partitions(
    p_table_name TEXT, p_start_year INTEGER, p_start_month INTEGER, p_end_year INTEGER, p_end_month INTEGER
) LANGUAGE plpgsql AS $$
DECLARE
    v_current_year INTEGER := p_start_year;
    v_current_month INTEGER := p_start_month;
    v_count INTEGER := 0;
BEGIN
    WHILE v_current_year < p_end_year OR (v_current_year = p_end_year AND v_current_month <= p_end_month) LOOP
        CALL add_month_partition(p_table_name, v_current_year, v_current_month, TRUE);
        v_count := v_count + 1;
        v_current_month := v_current_month + 1;
        IF v_current_month > 12 THEN v_current_month := 1; v_current_year := v_current_year + 1; END IF;
    END LOOP;
    RAISE NOTICE 'Batch add completed. Processed % partitions', v_count;
END;
$$;

-- ==========================================
-- 3 & 7. 预添加未来分区
-- ==========================================
CREATE OR REPLACE PROCEDURE pre_add_future_partitions(p_table_name TEXT) LANGUAGE plpgsql AS $$
DECLARE
    v_end_year INTEGER := EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER + 2;
BEGIN
    CALL add_month_partitions(p_table_name, EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER, EXTRACT(MONTH FROM CURRENT_DATE)::INTEGER, v_end_year, 12);
END;
$$;

CREATE OR REPLACE PROCEDURE pre_add_future_partitions_all() LANGUAGE plpgsql AS $$
DECLARE v_table_name TEXT;
BEGIN
    FOR v_table_name IN SELECT relname::TEXT FROM pg_class WHERE relkind = 'p' AND relnamespace = 'public'::regnamespace LOOP
        CALL pre_add_future_partitions(v_table_name);
    END LOOP;
END;
$$;

-- ==========================================
-- 4. 删除单个月度分区
-- ==========================================
CREATE OR REPLACE PROCEDURE drop_month_partition(p_table_name TEXT, p_year INTEGER, p_month INTEGER) LANGUAGE plpgsql AS $$
DECLARE
    v_partition_name TEXT := p_table_name || '_y' || p_year || 'm' || LPAD(p_month::TEXT, 2, '0');
BEGIN
    IF EXISTS (SELECT 1 FROM pg_inherits JOIN pg_class parent ON pg_inherits.inhparent = parent.oid JOIN pg_class child ON pg_inherits.inhrelid = child.oid WHERE parent.relname = p_table_name AND child.relname = v_partition_name) THEN
        -- [PATCH-2.1] 移除 CONCURRENTLY，避免在 Procedure 事务块中触发 PG 物理限制报错
        EXECUTE format('ALTER TABLE %I DETACH PARTITION %I', p_table_name, v_partition_name);
        EXECUTE format('DROP TABLE %I', v_partition_name);
        RAISE NOTICE 'Partition % dropped', v_partition_name;
    END IF;
END;
$$;

-- ==========================================
-- 5. 查看分区状态
-- ==========================================
CREATE OR REPLACE FUNCTION get_partition_status(p_table_name TEXT) RETURNS TABLE (partition_name TEXT, parent_table TEXT, partition_start TIMESTAMPTZ, partition_end TIMESTAMPTZ, row_count BIGINT, table_size TEXT) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY SELECT child.relname::TEXT, parent.relname::TEXT,
        (regexp_matches(pg_get_expr(child.relpartbound, child.oid), 'FROM \(''([^'']+)''\)'))[1]::TIMESTAMPTZ,
        (regexp_matches(pg_get_expr(child.relpartbound, child.oid), 'TO \(''([^'']+)''\)'))[1]::TIMESTAMPTZ,
        COALESCE(stat.n_live_tup, 0), pg_size_pretty(pg_total_relation_size(child.oid))
        FROM pg_inherits JOIN pg_class parent ON pg_inherits.inhparent = parent.oid JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        LEFT JOIN pg_stat_user_tables stat ON child.relname = stat.relname WHERE parent.relname = p_table_name ORDER BY partition_start;
END;
$$;

-- 初始化调用
CALL pre_add_future_partitions_all();
-- ==========================================
-- 分钟线表月度分区维护脚本
-- 用途：在生产环境中动态添加/删除月度分区
-- ==========================================

-- ==========================================
-- 1. 添加单月度分区（幂等执行）
-- ==========================================
CREATE OR REPLACE PROCEDURE add_month_partition(
    p_table_name TEXT,
    p_year INTEGER,
    p_month INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_partition_name TEXT;
    v_start_date TEXT;
    v_end_date TEXT;
BEGIN
    v_partition_name := p_table_name || '_' || p_year::TEXT || LPAD(p_month::TEXT, 2, '0');
    v_start_date := p_year::TEXT || '-' || LPAD(p_month::TEXT, 2, '0') || '-01';
    v_end_date := (p_year + CASE WHEN p_month = 12 THEN 1 ELSE 0 END)::TEXT || '-' ||
                  LPAD(CASE WHEN p_month = 12 THEN 1 ELSE p_month + 1 END::TEXT, 2, '0') || '-01';

    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = v_partition_name) THEN
        RAISE NOTICE '分区 % 已存在，跳过创建', v_partition_name;
        RETURN;
    END IF;

    EXECUTE format(
        'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
        v_partition_name,
        p_table_name,
        v_start_date,
        v_end_date
    );

    RAISE NOTICE '成功创建分区: %', v_partition_name;
END;
$$;

-- ==========================================
-- 2. 批量添加连续月度分区
-- ==========================================
CREATE OR REPLACE PROCEDURE add_month_partitions(
    p_table_name TEXT,
    p_start_year INTEGER,
    p_start_month INTEGER,
    p_end_year INTEGER,
    p_end_month INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_year INTEGER;
    v_current_month INTEGER;
    v_end_month INTEGER;
BEGIN
    v_current_year := p_start_year;
    v_current_month := p_start_month;

    WHILE v_current_year < p_end_year OR (v_current_year = p_end_year AND v_current_month <= p_end_month) LOOP
        CALL add_month_partition(p_table_name, v_current_year, v_current_month);

        v_current_month := v_current_month + 1;
        IF v_current_month > 12 THEN
            v_current_month := 1;
            v_current_year := v_current_year + 1;
        END IF;
    END LOOP;
END;
$$;

-- ==========================================
-- 3. 删除月度分区（幂等执行）
-- ==========================================
CREATE OR REPLACE PROCEDURE drop_month_partition(
    p_table_name TEXT,
    p_year INTEGER,
    p_month INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_partition_name TEXT;
BEGIN
    v_partition_name := p_table_name || '_' || p_year::TEXT || LPAD(p_month::TEXT, 2, '0');

    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = v_partition_name) THEN
        RAISE NOTICE '分区 % 不存在，跳过删除', v_partition_name;
        RETURN;
    END IF;

    EXECUTE format('DROP TABLE %I', v_partition_name);

    RAISE NOTICE '成功删除分区: %', v_partition_name;
END;
$$;

-- ==========================================
-- 4. 查看分区状态
-- ==========================================
CREATE OR REPLACE FUNCTION get_minute_partition_status(p_table_name TEXT)
RETURNS TABLE(partition_name TEXT, partition_range TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        child.relname::TEXT AS partition_name,
        pg_get_expr(child.relpartbound, child.oid)::TEXT AS partition_range
    FROM pg_inherits
    JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
    JOIN pg_class child ON child.oid = pg_inherits.inhrelid
    WHERE parent.relname = p_table_name
    ORDER BY child.relname;
END;
$$;

-- ==========================================
-- 5. 使用示例
-- ==========================================
-- -- 添加单个月度分区
-- CALL add_month_partition('stock_quotes_minute', 2027, 1);
--
-- -- 批量添加多个月度分区（2027-01 ~ 2027-12）
-- CALL add_month_partitions('stock_quotes_minute', 2027, 1, 2027, 12);
--
-- -- 查看分区状态
-- SELECT * FROM get_minute_partition_status('stock_quotes_minute');
--
-- -- 删除分区（谨慎使用！）
-- -- CALL drop_month_partition('stock_quotes_minute', 2025, 1);
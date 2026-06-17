-- ==========================================
-- docker/postgres/init/01-init.sql
-- 首次启动时由 postgres 镜像自动执行（以 superuser 运行）
-- 执行顺序：按文件名字母顺序，01 在 02 之前
-- ==========================================

-- 创建普通用户 quant_user（镜像已通过 POSTGRES_USER 环境变量创建）
-- 确保 quant_trading 数据库的所有者正确
ALTER DATABASE quant_trading OWNER TO quant_user;

-- 设置默认 search_path
ALTER ROLE quant_user SET search_path TO public;

-- Grant usage on public schema
GRANT USAGE ON SCHEMA public TO quant_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO quant_user;

\echo '[INIT] 01-init.sql 完成：用户与权限配置'

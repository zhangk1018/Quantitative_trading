#!/usr/bin/env python3
"""
轻量 SQL 迁移执行器（港美股改造 V1 引入，方案 §5）

按版本号顺序执行 backend/db/migrations/ 下的 *.sql 迁移文件，
通过 schema_migrations 表记录已应用版本（幂等：自动跳过已应用）。
每个迁移在单个事务中执行，失败自动回滚该迁移并中断。

用法:
    PG_PASSWORD=xxx venv/bin/python backend/db/run_migrations.py            # 应用全部待执行迁移
    PG_PASSWORD=xxx venv/bin/python backend/db/run_migrations.py --list     # 仅列出状态
    PG_PASSWORD=xxx venv/bin/python backend/db/run_migrations.py --version  # 当前已应用的最新版本

目录约定:
    backend/db/migrations/common/  公共数据表迁移（V008 起）
    backend/db/migrations/pdca/    PDCA 业务迁移（V001-V007，沿用人工 psql，可选纳入）

说明:
    pdca 目录历史迁移(V001-V007)此前均人工 psql 执行、未写入 schema_migrations，
    本执行器对所有目标迁移做"版本号驱动的幂等登记"；若 pdca 已人工应用过，
    建议通过 --mark-applied 登记以避免重复，或用 --skip-dir pdca 只跑 common。
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import psycopg2

# 项目根（本脚本在 backend/db/ 下）
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / "backend"))

try:
    from utils.logger import setup_logger
    logger = setup_logger("migration_runner")
except Exception:  # 日志组件不可用时降级到根 logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("migration_runner")

MIGRATION_DIRS = {
    "common": BASE_DIR / "backend/db/migrations/common",
    "pdca": BASE_DIR / "backend/db/migrations/pdca",
}

VERSION_RE = re.compile(r"^V(\d+)[^0-9]*\.sql$", re.IGNORECASE)


def _load_dotenv() -> None:
    """读取项目根 .env（未设置环境变量时兜底），不覆盖已存在的环境变量"""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _make_dsn() -> str:
    """构造连接串；优先 DATABASE_URL，否则拼 PG_* 环境变量"""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    required = ["PG_HOST", "PG_PORT", "PG_DATABASE", "PG_USER", "PG_PASSWORD"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"缺少数据库连接配置: {', '.join(missing)}（可设置 DATABASE_URL 或 PG_HOST/PG_PORT/PG_DATABASE/PG_USER/PG_PASSWORD）")
    return (
        f"host={os.environ.get('PG_HOST', 'localhost')} "
        f"port={os.environ.get('PG_PORT', '5432')} "
        f"dbname={os.environ['PG_DATABASE']} "
        f"user={os.environ['PG_USER']} "
        f"password={os.environ['PG_PASSWORD']}"
    )


def _ensure_schema_migrations(conn) -> None:
    """保证 schema_migrations 登记表存在"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                dir         TEXT NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()


def _applied_versions(conn) -> set[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def _discover_migrations(skip_dirs: set[str], only_dirs: set[str] | None) -> list[dict]:
    """扫描迁移文件，返回按版本排序的 [{version, name, dir, path}]"""
    files: list[dict] = []
    for dir_key, dir_path in MIGRATION_DIRS.items():
        if dir_key in skip_dirs or (only_dirs and dir_key not in only_dirs):
            continue
        if not dir_path.exists():
            continue
        for f in sorted(dir_path.glob("*.sql")):
            m = VERSION_RE.match(f.name)
            if not m:
                logger.warning(f"跳过未匹配版本号的文件: {f.name}")
                continue
            files.append({
                "version": int(m.group(1)),
                "name": f.name,
                "dir": dir_key,
                "path": f,
            })
    files.sort(key=lambda x: x["version"])
    return files


def _apply(conn, migration: dict) -> None:
    sql = migration["path"].read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO schema_migrations (version, name, dir) VALUES (%s, %s, %s)",
            (migration["version"], migration["name"], migration["dir"]),
        )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="轻量 SQL 迁移执行器")
    parser.add_argument("--list", action="store_true", help="仅列出迁移状态，不执行")
    parser.add_argument("--version", action="store_true", help="显示当前已应用的最新版本")
    parser.add_argument("--skip-dir", nargs="*", default=[], help="跳过的目录，如 pdca common")
    parser.add_argument("--only-dir", nargs="*", default=[], help="仅执行指定目录，如 common")
    parser.add_argument("--mark-applied", nargs="*", metavar="VERSION", help="登记指定版本为已应用（不执行 SQL）")
    args = parser.parse_args()

    _load_dotenv()
    if not os.environ.get("PG_PASSWORD") and not os.environ.get("DATABASE_URL"):
        logger.error("未提供数据库凭据：请设置 PG_PASSWORD（或完整 PG_* / DATABASE_URL）")
        return 2

    conn = psycopg2.connect(_make_dsn())
    try:
        _ensure_schema_migrations(conn)
        applied = _applied_versions(conn)
        migrations = _discover_migrations(
            set(args.skip_dir or []), set(args.only_dir or []) or None
        )

        if args.mark_applied:
            for v in args.mark_applied:
                v = int(v)
                if v in applied:
                    logger.info(f"版本 {v} 已登记，跳过")
                    continue
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO schema_migrations (version, name, dir) VALUES (%s, %s, %s)",
                        (v, f"V{v:03d}.sql (marked)", "manual"),
                    )
                conn.commit()
                logger.info(f"版本 {v} 已标记为已应用")
            return 0

        if args.version:
            print(max(applied) if applied else 0)
            return 0

        # --list / 列表状态
        for m in migrations:
            state = "applied" if m["version"] in applied else "pending"
            print(f"V{m['version']:03d}  {state:<8} {m['dir']:<8} {m['name']}")
        if args.list:
            return 0

        # 应用待执行迁移
        pending = [m for m in migrations if m["version"] not in applied]
        if not pending:
            logger.info("无待执行迁移，全部已应用")
            return 0
        for m in pending:
            logger.info(f"▶ 执行 V{m['version']:03d} {m['dir']}/{m['name']}")
            _apply(conn, m)
            logger.info(f"✅ V{m['version']:03d} 已应用")
        logger.info(f"共应用 {len(pending)} 个迁移")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
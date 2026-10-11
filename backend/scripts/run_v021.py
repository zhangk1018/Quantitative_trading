#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐段执行 V021（cn total_mv 元→万元 回填）。

为什么要单独的执行器：V021 第 3 步要更新约 120 万行 `stock_daily_snapshot`（含 8 个索引维护），
单事务执行容易触发 `statement_timeout` 并**整体回滚**（实测 900s 超时）。按 `-- STEP`
分段、每段独立提交，既避免整体回滚，也让每段可单独重跑（各段均幂等）。

用法：
    ./venv/bin/python backend/scripts/run_v021.py [--timeout 3600]
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

SQL_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'db', 'migrations', 'common', 'V021_cn_total_mv_yuan_to_wan.sql')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeout', type=int, default=3600, help='每段 statement_timeout（秒）')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), '.env'))
    sql = open(SQL_FILE, encoding='utf-8').read()
    # 按 `-- STEP` 分段（保留注释行，便于日志对照）
    chunks = [c.strip() for c in re.split(r'(?m)^(?=-- STEP)', sql) if c.strip()]
    chunks = [c for c in chunks if re.search(r'(?im)^\s*(UPDATE|INSERT|WITH)\b', c)]

    conn = psycopg2.connect(
        host='localhost', port=5432, dbname=os.environ.get('PG_DATABASE', 'quant_trading'),
        user=os.environ.get('PG_USER', 'quant_user'), password=os.environ.get('PG_PASSWORD', ''))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET statement_timeout = %s", (f'{args.timeout}s',))

    print(f'共 {len(chunks)} 段，timeout={args.timeout}s，dry_run={args.dry_run}', flush=True)
    for i, chunk in enumerate(chunks, 1):
        title = chunk.splitlines()[0][:70]
        t = time.time()
        if args.dry_run:
            print(f'[{i}/{len(chunks)}] DRY {title}', flush=True)
            continue
        try:
            cur.execute(chunk)
            print(f'[{i}/{len(chunks)}] ✅ {time.time()-t:6.1f}s rc={cur.rowcount} | {title}', flush=True)
        except Exception as e:  # noqa: BLE001 - 逐段报错，便于定位
            print(f'[{i}/{len(chunks)}] ❌ {time.time()-t:6.1f}s {type(e).__name__}: {e}', flush=True)
            conn.close()
            return 1
    conn.close()
    print('V021 全部段落完成', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())

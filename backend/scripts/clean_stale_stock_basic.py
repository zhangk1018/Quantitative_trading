#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_basic 陈旧/已退市条目清理器（协作单 63.0）

■ 背景
`stock_basic` 的美股清单来自静态核心池 `backend/config/us_core_universe.json`
（K 批示精简版）。成分股会因并购/更名/私有化而停止交易（如 PX=Praxair 早并入 LIN、
K=Kellanova 被 Mars 收购、EA 被私有化），但清单不会自动剔除，于是这些代码：

  - 每天仍被 `import_us_daily` 逐只请求 → 必然「拉取为空」，既浪费限流额度，
    又让失败清单长期噪声化（真正该关注的限流缺口被淹没）；
  - 仍计入**覆盖率分母**（stock_basic 总数）→ 覆盖率永远差一截，
    看板/门禁长期偏低。

本脚本负责把「已确认不再交易」的条目标记为退市（`delist_date`），而**不是物理删除**：
- `delist_date IS NOT NULL` 已被下游统一识别（看板覆盖率分母、缺失股票清单、
  形态聚合门禁、feature_service 选股域均按 `delist_date IS NULL` 过滤）；
- 历史行情（`stock_quotes` 等）与自选股引用保持完整，不产生悬空引用。

■ 安全设计
- **默认 dry-run**：仅列出候选（含「最后行情日」「已入库行数」供人工判断）。
- **必须显式传 `--codes`** 才会写入；不带 `--codes` 的 `--apply` 直接拒绝。
  因为「长期无行情」也可能是**数据源截断/限流**而非退市（实测 MMC=Fox 仍在市但源只到
  2026-01-13），机器无法可靠区分，故把最终判断权留给人工。
- 仅更新 `delist_date IS NULL` 的行，重复执行幂等。

■ 用法
    # 巡检：列出各市场「长期无行情」的候选
    venv/bin/python backend/scripts/clean_stale_stock_basic.py --market us --stale-days 60

    # 确认后标记退市（delist_date 取该股最后行情日；无行情记录则取今天）
    venv/bin/python backend/scripts/clean_stale_stock_basic.py --market us --apply --codes K,EA

    # 指定退市日（用于厂外证据明确的场景，如 PX 源末交易日 2026-02-10）
    venv/bin/python backend/scripts/clean_stale_stock_basic.py --market us --apply \
        --codes PX --delist-date 2026-02-10

退出码：0=正常；1=参数/执行错误。
"""
import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASE_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from utils.alerting import append_alerts
    from utils.logger import setup_logger
except Exception:  # 日志/告警组件不可用时降级
    import logging
    logging.basicConfig(level=logging.INFO)
    append_alerts = None
    setup_logger = lambda name: logging.getLogger(name)  # noqa: E731

logger = setup_logger('clean_stale_stock_basic')

STALE_DAYS_DEFAULT = 60


# ==================== 数据库 ====================
def _load_dotenv() -> None:
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def _connect():
    import psycopg2
    _load_dotenv()
    if os.environ.get('DATABASE_URL'):
        return psycopg2.connect(os.environ['DATABASE_URL'])
    return psycopg2.connect(
        host=os.environ['PG_HOST'], port=os.environ['PG_PORT'],
        dbname=os.environ['PG_DATABASE'], user=os.environ['PG_USER'],
        password=os.environ['PG_PASSWORD'],
    )


# ==================== 候选检测 ====================
_SQL_STALE = """
    SELECT b.code,
           MAX(q.trade_date) AS last_dt,
           COUNT(q.trade_date) AS rows
    FROM stock_basic b
    LEFT JOIN stock_quotes q
           ON q.market = b.market AND q.code = b.code AND q.cycle = '1d'
    WHERE b.market = %s
      AND b.delist_date IS NULL
    GROUP BY b.code
    HAVING MAX(q.trade_date) IS NULL OR MAX(q.trade_date) < %s
    ORDER BY MAX(q.trade_date) NULLS FIRST, b.code
"""


def find_stale_codes(conn, market: str, stale_days: int) -> List[Dict[str, Any]]:
    """列出「在市但长期无行情」的标的（候选，需人工确认）。

    Args:
        market: cn/hk/us
        stale_days: 超过该天数无新行情即视为候选（0 表示只看「从未有行情」）

    Returns:
        [{code, last_dt, rows}]，按「从未有行情 → 最久无行情」排序
    """
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=max(0, stale_days))
    with conn.cursor() as cur:
        cur.execute(_SQL_STALE, (market, cutoff))
        rows = cur.fetchall()
    return [{'code': r[0], 'last_dt': r[1], 'rows': int(r[2] or 0)} for r in rows]


# ==================== 标记退市 ====================
def mark_delisted(conn, market: str, codes: List[str],
                  delist_date: Optional[date] = None) -> int:
    """把指定代码标记为退市。`delist_date` 缺省取该股最后行情日，无行情则取今天。

    Returns:
        实际更新行数（幂等：已标记的不重复更新）
    """
    if not codes:
        return 0
    # 注意：这里**不能**用 `delist_date or date.today()` 兜底——那会让传参恒非空，
    # SQL 里的 COALESCE 永远取不到「该股最后行情日」。缺省一律传 None，交给 SQL 决定。
    marker = delist_date
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE stock_basic b
               SET delist_date = COALESCE(%s::date,
                                          (SELECT MAX(q.trade_date) FROM stock_quotes q
                                            WHERE q.market = b.market AND q.code = b.code
                                              AND q.cycle = '1d'),
                                          CURRENT_DATE),
                   updated_at = NOW()
             WHERE b.market = %s AND b.code = ANY(%s) AND b.delist_date IS NULL
            """,
            (marker, market, list(codes)),
        )
        updated = cur.rowcount
    conn.commit()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(
        description='stock_basic 陈旧/已退市条目清理（默认 dry-run，写入需显式 --codes）')
    parser.add_argument('--market', default='us', choices=['cn', 'hk', 'us'])
    parser.add_argument('--stale-days', type=int, default=STALE_DAYS_DEFAULT,
                        help=f'超过该天数无行情即列为候选（默认 {STALE_DAYS_DEFAULT}）')
    parser.add_argument('--apply', action='store_true',
                        help='实际写入 delist_date（必须同时提供 --codes）')
    parser.add_argument('--codes', type=str, default=None,
                        help='逗号分隔的代码清单，如 PX,K,EA（人工确认后填写）')
    parser.add_argument('--delist-date', type=str, default=None,
                        help='统一指定退市日 YYYY-MM-DD；缺省取该股最后行情日')
    args = parser.parse_args()

    codes = [c.strip().upper() for c in (args.codes or '').split(',') if c.strip()]
    delist_date = None
    if args.delist_date:
        try:
            delist_date = datetime.strptime(args.delist_date, '%Y-%m-%d').date()
        except ValueError:
            print(f'[ERROR] --delist-date 格式应为 YYYY-MM-DD，收到 {args.delist_date!r}')
            return 1
    if args.apply and not codes:
        print('[ERROR] --apply 必须配合 --codes（人工确认后才可写入；'
              '「长期无行情」也可能是数据源截断而非退市）')
        return 1

    try:
        conn = _connect()
    except Exception as e:
        print(f'[ERROR] 数据库连接失败: {e}')
        return 1

    try:
        candidates = find_stale_codes(conn, args.market, args.stale_days)
        print('=' * 74)
        print(f'stock_basic 陈旧条目巡检 | market={args.market} | '
              f'阈值 {args.stale_days} 天无行情 | {datetime.now():%Y-%m-%d %H:%M:%S}')
        print('=' * 74)
        if not candidates:
            print('  ✅ 无陈旧条目（全部在市标的近期均有行情）')
        for c in candidates:
            last_dt = c['last_dt'].isoformat() if c['last_dt'] else '—'
            tag = '从未有行情' if c['rows'] == 0 else f"最后 {last_dt}"
            print(f"  {c['code']:<8} {tag:<22} 已入库 {c['rows']:>6} 行")
        print('-' * 74)

        if not args.apply:
            if candidates:
                print('  ℹ️ dry-run：以上仅为候选。确认已退市后，用 --apply --codes ... 标记。')
                print('     ⚠️ 「长期无行情」也可能是数据源截断（如 MMC 仍在市但源只到旧日），')
                print('        请先核对行情源（akshare 直连）再决定；切勿批量标记。')
            return 0

        unknown = [c for c in codes if c not in {x['code'] for x in candidates}]
        if unknown:
            print(f'  ⚠️ 以下代码不在本次候选清单内（可能今日已有行情或已标记）：{unknown}')
            print('     仍将按 --codes 显式清单执行（尊重人工判断）。')

        updated = mark_delisted(conn, args.market, codes, delist_date)
        print(f'  ✅ 已标记退市 {updated} 行：{codes}')
        if updated and append_alerts:
            append_alerts([{
                'level': 'WARNING',
                'market': args.market,
                'message': f"[stock_basic 清理] 标记退市 {updated} 只：{codes}"
                           f"（delist_date={delist_date or '最后行情日'}，"
                           f"不再参与下载与覆盖率分母）",
            }])
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())

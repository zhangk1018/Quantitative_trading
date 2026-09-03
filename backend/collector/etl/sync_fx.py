#!/usr/bin/env python3
"""
汇率 ETL 脚本（M4.5，港股/美股改造汇率层）

从 Yahoo Finance 拉取非人民币兑人民币汇率（HKDCNY=X / USDCNY=X），
按自然日做前向填充（ffill）后写入 fx_rates 表，保证每个自然日都有汇率可查。

写入口径：
- pair 约定为 `HKDCNY=X` / `USDCNY=X`（yfinance 用 `f"{ccy}CNY=X"` 拉取）。
- rate 取当日收盘价：表示 1 单位外币兑多少 CNY，base_currency 固定 'CNY'。
- fx_rates 主键 (pair, trade_date)，写入采用 ON CONFLICT ... DO UPDATE upsert。
- 每日 ffill：yfinance 只在外汇交易日（周一~周五）返回数据，周末/节假日无报价，
  但股票可能在除外汇交易日之外的日子也有行情。因此把拉到的汇率按自然日期重索引 +
  ffill，写满区间内每个自然日，保证股票价格换算时"当日或最近有效汇率"随时可查。

用法：
    python sync_fx.py                                      # 默认拉最近 30 天（当天为终点）
    python sync_fx.py --start 2026-08-01 --end 2026-08-31  # 区间回溯
    python sync_fx.py --pairs HKDCNY=X USDCNY=X            # 指定货币对
    python sync_fx.py --dry-run                            # 试运行：拉取打印、不落库
"""
import os
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# 保证 `import utils.logger` 可解析（脚本独立运行时）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger('fx_sync')

# 项目根目录（.env 所在处）
BASE_DIR = Path(__file__).resolve().parents[3]

DEFAULT_PAIRS = ['HKDCNY=X', 'USDCNY=X']  # 默认拉取的人民币相关货币对
BASE_CURRENCY = 'CNY'                     # 统一以 CNY 为基准币种
DEFAULT_LOOKBACK_DAYS = 30                # 未指定 --start 时的默认回溯天数


# ==================== 网络环境清理（Yahoo 需直连） ====================
def _clear_proxy_env() -> None:
    """清除外部代理环境变量，确保 yfinance 通过直连出口访问。

    网络由运维打通为直连；HTTP(S)_PROXY / ALL_PROXY 残留会致使 yfinance 走代理出错。
    """
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
                'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy'):
        os.environ.pop(key, None)


# ==================== 数据库连接（独立 psycopg2 路径） ====================
def _load_dotenv() -> None:
    """读取项目根 .env（未设置环境变量时兜底），不覆盖已存在的环境变量。"""
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _make_dsn() -> str:
    """构造 PostgreSQL 连接串（优先 DATABASE_URL，否则拼接 PG_*）。"""
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    required = ['PG_HOST', 'PG_PORT', 'PG_DATABASE', 'PG_USER', 'PG_PASSWORD']
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"缺少数据库连接配置: {', '.join(missing)}")
    return (
        f"host={os.environ['PG_HOST']} port={os.environ['PG_PORT']} "
        f"dbname={os.environ['PG_DATABASE']} user={os.environ['PG_USER']} "
        f"password={os.environ['PG_PASSWORD']}"
    )


def _connect() -> psycopg2.extensions.connection:
    """建立连接（连接失败时抛异常，由调用方捕获）。"""
    _load_dotenv()
    return psycopg2.connect(_make_dsn())


# ==================== 数据拉取 ====================
def _fetch_fx_rates(pairs: List[str], start: str, end: str) -> Dict[str, pd.DataFrame]:
    """从 Yahoo 拉取各货币对汇率历史。

    Args:
        pairs: Yahoo 货币对代码列表（如 HKDCNY=X）
        start/end: 日期区间（YYYY-MM-DD，含 start 不含 end）

    Returns:
        {pair: DataFrame}，DataFrame 为 Yahoo 原生日线（含 Close 列），失败返回空 DataFrame。
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance 未安装，无法拉取汇率（安装：./venv/bin/pip install yfinance）")
        return {}
    _clear_proxy_env()
    result: Dict[str, pd.DataFrame] = {}
    for pair in pairs:
        try:
            df = yf.Ticker(pair).history(
                start=start, end=end, interval='1d', auto_adjust=False, prepost=False
            )
            if df is None or df.empty:
                logger.warning(f"⚠️ {pair}: 拉取为空（可能限流或区间无数据）")
                result[pair] = pd.DataFrame()
                continue
            logger.info(f"✅ {pair}: 拉取 {len(df)} 条，最新 {df.index[-1].date() if hasattr(df.index[-1], 'date') else df.index[-1]}")
            result[pair] = df
        except Exception as e:  # noqa: BLE001 - 网络异常统一降级为单货币对失败
            logger.warning(f"⚠️ {pair}: 拉取失败: {e}")
            result[pair] = pd.DataFrame()
    return result


# ==================== 每日 ffill ====================
def _build_daily_rates(pair: str, df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """把 Yahoo 汇率日线转为『每个自然日都有值』的汇率序列。

    思路：仅取 Close 收盘价，按自然日重索引后前向填充（ffill）。
    周末/节假日外汇无报价，但股票价格可能在这些自然日存在，故需补齐缺失自然日，
    保证 `fx_rates` 中"当日或最近有效汇率"随时可查。

    Args:
        pair: 货币对代码（如 HKDCNY=X）
        df: Yahoo 拉取的日线（含 Close 列，索引为日期）
        start/end: 自然日区间（YYYY-MM-DD，含两端）

    Returns:
        DataFrame 列 [pair, trade_date, rate, base_currency]，已按自然日排序。
    """
    if df.empty:
        return pd.DataFrame(columns=['pair', 'trade_date', 'rate', 'base_currency'])
    # 规范化索引为无时区纯日期，取 Close
    close = df['Close'].copy()
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)
    close.index = close.index.tz_localize(None).normalize() if close.index.tz is not None else close.index.normalize()
    close = close.dropna()

    date_idx = pd.date_range(start=start, end=end, freq='D')
    # 重索引到自然日 + 前向填充；首部缺失（无更早数据）NaN 会被下面剔除
    filled = close.reindex(date_idx, method='ffill').dropna()

    rows = pd.DataFrame({
        'pair': pair,
        'trade_date': filled.index.date,
        'rate': filled.round(6).astype(float),
        'base_currency': BASE_CURRENCY,
    })
    return rows.reset_index(drop=True)


# ==================== 写入 ====================
def write_fx_rates(conn: psycopg2.extensions.connection, df: pd.DataFrame, pair: str) -> int:
    """批量写入 fx_rates（execute_values + ON CONFLICT (pair, trade_date)）。"""
    if df is None or df.empty:
        return 0
    values = [tuple(r) for r in df[['pair', 'trade_date', 'rate', 'base_currency']].itertuples(index=False, name=None)]
    try:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO fx_rates (pair, trade_date, rate, base_currency)
                VALUES %s
                ON CONFLICT (pair, trade_date) DO UPDATE SET
                    rate = EXCLUDED.rate,
                    base_currency = EXCLUDED.base_currency
            """, values, page_size=2000)
        conn.commit()
        logger.info(f"  {pair}: 写入 fx_rates {len(values)} 条")
        return len(values)
    except psycopg2.Error as e:  # noqa: BLE001 - 数据库错误
        conn.rollback()
        logger.error(f"  {pair}: 写入 fx_rates 失败: {e}")
        raise


# ==================== 入口 ====================
def run_sync(pairs: List[str], start: str, end: str, dry_run: bool = False) -> Dict[str, int]:
    """拉取并（可选）写入指定货币对的汇率。

    Args:
        pairs: 货币对代码列表
        start/end: 日期区间（YYYY-MM-DD）
        dry_run: 试运行模式（拉取打印、不落库）

    Returns:
        {pair: 写入条数}
    """
    stats: Dict[str, int] = {}
    logger.info(f"🚀 拉取汇率 {pairs}，区间 {start} ~ {end}，dry_run={dry_run}")

    fetched = _fetch_fx_rates(pairs, start, end)

    conn = None if dry_run else _connect()
    try:
        for pair in pairs:
            df_raw = fetched.get(pair, pd.DataFrame())
            daily = _build_daily_rates(pair, df_raw, start, end)
            if daily.empty:
                logger.warning(f"  {pair}: 无可写入数据")
                stats[pair] = 0
                continue
            if dry_run:
                logger.info(f"[DRY-RUN] {pair}: 待写入 {len(daily)} 条（自然日 ffill）")
                logger.info(daily.head(3).to_string(index=False))
                logger.info(daily.tail(3).to_string(index=False))
                stats[pair] = len(daily)
            else:
                stats[pair] = write_fx_rates(conn, daily, pair)
    finally:
        if conn is not None:
            conn.close()
    logger.info(f"✅ 汇率同步完成: {stats}")
    return stats


def _build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(description='汇率 ETL（Yahoo -> fx_rates）')
    parser.add_argument('--start', type=str, default=None, help='起始日期 YYYY-MM-DD（默认：end-30 天）')
    parser.add_argument('--end', type=str, default=None, help='结束日期 YYYY-MM-DD（默认：今天）')
    parser.add_argument('--pairs', nargs='+', default=None,
                        help='货币对列表（如 HKDCNY=X USDCNY=X，默认：%s）' % ' '.join(DEFAULT_PAIRS))
    parser.add_argument('--dry-run', action='store_true', help='试运行模式（拉取打印、不落库）')
    return parser


def main() -> None:
    """命令行入口。"""
    args = _build_parser().parse_args()

    end = args.end or date.today().isoformat()
    if args.start:
        start = args.start
    else:
        start = (date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()

    pairs = args.pairs or DEFAULT_PAIRS
    raise SystemExit(0 if _run(pairs, start, end, args.dry_run) else 1)


def _run(pairs: List[str], start: str, end: str, dry_run: bool) -> bool:
    """执行同步并返回退出码是否成功。"""
    try:
        stats = run_sync(pairs, start, end, dry_run=dry_run)
        total = sum(stats.values())
        if total == 0:
            logger.error("❌ 所有货币对均无数据写入")
            return False
        return True
    except Exception as e:  # noqa: BLE001 - 顶层兜底
        logger.error(f"程序异常: {e}")
        return False


if __name__ == '__main__':
    main()
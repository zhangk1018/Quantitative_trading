#!/usr/bin/env python3
"""
数据质量监控告警系统（协作单 30.0 V6 / ② 监控扩展 market 维度）

对 cn / hk / us 三市场分别统计数据完整性、缺失值比例、新鲜度，并按各市场独立门槛校验，
异常统一走 utils.alerting 落 `logs/monitoring/alerts.log`，供看板与晨检读取。

各市场监控指标：
1. stock_quotes：最新交易日覆盖股票数 + 新鲜度（最后更新距今周数/天数）
2. stock_indicators：技术指标缺失率（ma5/macd）
3. stock_basic：上市公司总数
4. 触发条件（阈值按市场差异，见 MARKET_SPECS）：
   - 覆盖数 < min_stocks → WARNING
   - 新鲜度 > max_freshness_days → CRITICAL/WARNING
   - 指标缺失率 > max_null_pct → WARNING

用法：
    ./venv/bin/python backend/monitoring/data_quality_monitor.py               # 全部市场
    ./venv/bin/python backend/monitoring/data_quality_monitor.py --market cn
"""
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector.storage.postgresql_storage import PostgreSQLStorage  # noqa: E402
from utils.config import config  # noqa: E402
from utils.logger import setup_logger  # noqa: E402
from utils.alerting import append_alerts  # noqa: E402

logger = setup_logger('data_quality_monitor')


@dataclass
class MarketSpec:
    """单市场监控阈值与标识。"""
    market: str
    label: str
    min_stocks: int = 0          # 最新交易日最低覆盖股票数
    max_freshness_days: int = 3  # 数据最多可存续天数
    max_null_pct: float = 5.0    # 指标缺失率上限(%)
    enable_indicator_check: bool = True  # 是否启用指标缺失率校验（仅 cn）


MARKET_SPECS: Dict[str, MarketSpec] = {
    'cn': MarketSpec(market='cn', label='A股', min_stocks=5000, max_freshness_days=3, max_null_pct=5.0, enable_indicator_check=True),
    'hk': MarketSpec(market='hk', label='港股', min_stocks=2000, max_freshness_days=3, max_null_pct=50.0, enable_indicator_check=False),  # 铺全量前指标覆盖率低，仅统计不告警
    'us': MarketSpec(market='us', label='美股', min_stocks=200, max_freshness_days=7, max_null_pct=50.0, enable_indicator_check=False),    # 美股收盘=北京次日凌晨，7天容忍节假日
}


def _get_storage() -> Optional[PostgreSQLStorage]:
    """建立数据库连接。"""
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'user': db_config.get('user', 'postgres'),
        'password': db_config.get('password', ''),
    })
    return storage if storage.connect() else None


def _scalar(cursor, sql: str, params: tuple = ()) -> Optional[object]:
    """执行单值查询（容错返回 None）。"""
    try:
        cur = cursor
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"❌ 查询失败: {e} | SQL: {sql[:120]}")
        return None


def get_market_metrics(storage, spec: MarketSpec) -> Dict[str, object]:
    """统计单市场数据质量指标。"""
    mkt = spec.market
    metrics: Dict[str, object] = {'market': mkt, 'label': spec.label}
    cursor = storage.conn.cursor()

    # 1. stock_quotes：最新交易日覆盖数 + 最近更新日期
    latest_date = _scalar(cursor, "SELECT MAX(trade_date) FROM stock_quotes WHERE cycle='1d' AND market=%s", (mkt,))
    metrics['quotes_latest'] = str(latest_date) if latest_date else None
    if latest_date:
        covered = _scalar(
            cursor,
            "SELECT COUNT(DISTINCT code) FROM stock_quotes WHERE cycle='1d' AND market=%s AND trade_date=%s",
            (mkt, latest_date),
        )
        metrics['quotes_covered'] = covered or 0
        latest_dt = latest_date if isinstance(latest_date, datetime) else datetime.combine(latest_date, datetime.min.time())
        metrics['quotes_freshness_days'] = (datetime.now() - latest_dt).days
    else:
        metrics['quotes_covered'] = 0
        metrics['quotes_freshness_days'] = None

    # 2. stock_indicators：缺失率（cn 启用）
    null_pct = None
    if spec.enable_indicator_check:
        total = _scalar(cursor, "SELECT COUNT(*) FROM stock_indicators WHERE market=%s", (mkt,)) or 0
        if total:
            ma5_nums = _scalar(cursor, "SELECT COUNT(*) FROM stock_indicators WHERE market=%s AND ma5 IS NULL", (mkt,)) or 0
            macd_nums = _scalar(cursor, "SELECT COUNT(*) FROM stock_indicators WHERE market=%s AND macd IS NULL", (mkt,)) or 0
            null_pct = (ma5_nums + macd_nums) / total * 100
    metrics['indicator_null_pct'] = null_pct

    # 3. stock_basic：上市公司总数
    metrics['basic_count'] = _scalar(cursor, "SELECT COUNT(*) FROM stock_basic WHERE market=%s AND delist_date IS NULL", (mkt,)) or 0

    cursor.close()
    return metrics


def check_market_alerts(metrics: Dict[str, object], spec: MarketSpec) -> List[Dict[str, str]]:
    """对单市场指标执行告警判定。"""
    alerts: List[Dict[str, str]] = []
    mkt = metrics['market']
    label = metrics['label']

    def _warn(message: str, level: str = 'WARNING') -> None:
        alerts.append({'level': level, 'market': mkt, 'message': f"[{label}] {message}"})

    # 覆盖数不足
    covered = metrics.get('quotes_covered') or 0
    if metrics.get('quotes_latest') and covered < spec.min_stocks:
        _warn(f"最新交易日 {metrics['quotes_latest']} 覆盖 {covered} 只 < 阈值 {spec.min_stocks} 只")

    # 新鲜度
    freshness = metrics.get('quotes_freshness_days')
    if freshness is not None and freshness > spec.max_freshness_days:
        level = 'CRITICAL' if freshness > spec.max_freshness_days + 1 else 'WARNING'
        _warn(f"行情数据已 {freshness} 天未更新（最新 {metrics['quotes_latest']}，阈值 {spec.max_freshness_days} 天）", level)

    # 指标缺失率（cn）
    null_pct = metrics.get('indicator_null_pct')
    if spec.enable_indicator_check and null_pct is not None and null_pct > spec.max_null_pct:
        _warn(f"技术指标缺失率过高: {null_pct:.2f}%（阈值 {spec.max_null_pct:.0f}%）")

    return alerts


def check_adj_factor_jumps(storage, spec: MarketSpec, max_rows: int = 50) -> List[Dict[str, str]]:
    """复权跳变告警（③）：同一只股票相邻除权日的 adj_factor 比值 >1.5 或 <0.5 触发告警。

    stock_adj_factor 仅在除权日有行，故"较昨日"= 该股票上一个除权日（LAG by trade_date）。
    正常除息因子变动通常在百分之几；>1.5/<0.5 的跳变多为数据异常或未清洗的巨幅拆送。
    """
    alerts: List[Dict[str, str]] = []
    mkt = spec.market
    if mkt == 'cn':
        return alerts  # 仅针对 hk/us（方案 §P0 口径）
    cursor = storage.conn.cursor()
    sql = """
        SELECT t.code, t.trade_date::text, t.prev_date::text,
               t.adj_factor, t.prev_factor, (t.adj_factor / t.prev_factor) AS ratio
        FROM (
            SELECT code, trade_date, adj_factor,
                   LAG(adj_factor) OVER (PARTITION BY code ORDER BY trade_date) AS prev_factor,
                   LAG(trade_date)  OVER (PARTITION BY code ORDER BY trade_date) AS prev_date
            FROM stock_adj_factor
            WHERE market = %s AND adj_factor IS NOT NULL
        ) t
        WHERE t.prev_factor IS NOT NULL
          AND (t.adj_factor / t.prev_factor > 1.5 OR t.adj_factor / t.prev_factor < 0.5)
        ORDER BY t.trade_date DESC
        LIMIT %s
    """
    try:
        cursor.execute(sql, (mkt, max_rows))
        for code, trade_date, prev_date, factor, prev_factor, ratio in cursor.fetchall():
            direction = "骤增" if ratio > 1.5 else "骤降"
            alerts.append({
                'level': 'WARNING',
                'market': mkt,
                'message': (
                    f"复权因子{direction}异常: {code} 于 {trade_date} "
                    f"adj_factor={factor} (前值 {prev_factor}@{prev_date})，比值为 {ratio:.3f}（正常除息应接近1）"
                ),
            })
    except Exception as e:
        logger.error(f"❌ 复权跳变检测失败: {e}")
    finally:
        cursor.close()
    return alerts


def generate_report(metrics_all: List[Dict[str, object]], alerts_all: List[Dict[str, str]]) -> str:
    """渲染文本报告（终端/日志）。"""
    lines = ["=" * 70, f"📊 数据质量监控报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "=" * 70]
    for m in metrics_all:
        lines.append(
            f"  📦 [{m['market']}] {m['label']}: 最新 {m.get('quotes_latest')} · 覆盖 {m.get('quotes_covered')} 只"
            f" · 存续 {m.get('quotes_freshness_days')} 天 · 上市 {m.get('basic_count')} 只"
            + (f" · 指标缺失率 {m.get('indicator_null_pct'):.2f}%" if m.get('indicator_null_pct') is not None else " · 指标缺失率 -")
        )
    lines.append("-" * 70)
    if alerts_all:
        lines.append(f"🔔 告警列表（{len(alerts_all)} 条）:")
        for a in alerts_all:
            icon = '🔴' if a['level'] == 'CRITICAL' else '🟡'
            lines.append(f"  {icon} [{a['level']}] [{a['market']}] {a['message']}")
    else:
        lines.append("✅ 所有市场数据正常，无告警")
    lines.append("=" * 70)
    logger.info("=" * 70)
    logger.info("🚀 开始数据质量监控（market 维度）")
    return "\n".join(lines)


def main() -> None:
    """主函数：遍历市场统计 + 判定告警 + 落 alerts.log。"""
    import argparse
    parser = argparse.ArgumentParser(description='数据质量监控（cn/hk/us）')
    parser.add_argument('--market', default='', help='只检查指定市场(cn/hk/us)，空=全部')
    args = parser.parse_args()

    markets = [args.market] if args.market else list(MARKET_SPECS.keys())
    spec_list = [MARKET_SPECS[m] for m in markets if m in MARKET_SPECS]

    storage = _get_storage()
    if not storage:
        logger.error("❌ 数据库连接失败")
        return

    metrics_all: List[Dict[str, object]] = []
    alerts_all: List[Dict[str, str]] = []
    try:
        for spec in spec_list:
            metrics = get_market_metrics(storage, spec)
            metrics_all.append(metrics)
            alerts_all.extend(check_market_alerts(metrics, spec))
            # ③ 复权跳变告警（hk/us）
            alerts_all.extend(check_adj_factor_jumps(storage, spec))
    finally:
        storage.disconnect()

    report = generate_report(metrics_all, alerts_all)
    print(report, file=sys.stdout)
    logger.info(report)

    if alerts_all:
        append_alerts(alerts_all)
        logger.warning(f"🌡️ 数据质量监控发现 {len(alerts_all)} 条告警，已写入 alerts.log")
    else:
        logger.info("✅ 所有市场数据质量正常，无告警")


if __name__ == '__main__':
    main()
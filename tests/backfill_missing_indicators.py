"""
补跑无指标股票的程序

逻辑：
- 找出 stock_quotes 有、stock_indicators 没有的股票
- 优先使用 2025-01-01 起算；如果 2025 后无数据则用该股票最后 60 天数据范围
"""
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

from datetime import datetime
from collector.storage.postgresql_storage import PostgreSQLStorage
from clean.processor.technical_indicator import TechnicalIndicator
from utils.config import config
from utils.logger import setup_logger
import pandas as pd
import traceback

logger = setup_logger('indicator_backfill')

db_config = config.get('database', {})
storage = PostgreSQLStorage({
    'host': db_config.get('host', 'localhost'),
    'port': db_config.get('port', 5432),
    'database': db_config.get('database', 'quant_trading'),
    'username': db_config.get('username', 'quant_user'),
    'password': db_config.get('password', ''),
})
storage.connect()

# 找出所有无指标的股票
query = """
    SELECT q.code, MAX(q.trade_date) as last_quote
    FROM stock_quotes q
    WHERE q.cycle = '1d'
      AND NOT EXISTS (SELECT 1 FROM stock_indicators i WHERE i.code = q.code AND i.cycle='1d')
    GROUP BY q.code
    ORDER BY q.code
"""
cur = storage.conn.cursor()
cur.execute(query)
rows = cur.fetchall()
all_missing = [(r[0], r[1]) for r in rows]
logger.info(f"无指标的股票总数: {len(all_missing)}")

# 分类：可补跑(2025后) + 边缘(2024年) = 真正需要补跑
to_backfill = [(c, d) for c, d in all_missing if d and d >= datetime(2024, 1, 1).date()]
unavailable = [(c, d) for c, d in all_missing if not d or d < datetime(2024, 1, 1).date()]
logger.info(f"  可补跑（2024年起有数据）: {len(to_backfill)} 只")
logger.info(f"  不可补跑（2024年前已停）: {len(unavailable)} 只")

success, fail, total_records = 0, 0, 0
fail_codes = []
for i, (code, last_q) in enumerate(to_backfill):
    try:
        # 优先从 2025-01-01 取数；如果该股票 2025 后数据 < 60 天，则用最后 60 天数据
        end_date = datetime.now().strftime('%Y-%m-%d')
        # 先用 2025-01-01
        quotes_df = storage.get_quotes(code=code, cycle='daily', start_date='2025-01-01', end_date=end_date)
        if len(quotes_df) < 60:
            # 2025后数据不足，改用更早
            quotes_df = storage.get_quotes(code=code, cycle='daily', start_date='2024-01-01', end_date=end_date)
        if len(quotes_df) < 60:
            # 仍不足，放弃
            fail += 1
            fail_codes.append((code, f"data<60 days: {len(quotes_df)}"))
            continue

        quotes_df['adjust_type'] = 'qfq'
        quotes_df['adjust_factor'] = 1.0
        for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
            if col in quotes_df.columns:
                quotes_df[col] = quotes_df[col].astype(float)

        indicators_df = TechnicalIndicator.calculate_all(quotes_df, require_adjust=False)
        if indicators_df.empty:
            fail += 1
            fail_codes.append((code, "calculate_all returned empty"))
            continue

        # 构造 save_df
        save_df = pd.DataFrame()
        save_df['code'] = indicators_df['code'] if 'code' in indicators_df.columns else code
        save_df['cycle'] = '1d'
        save_df['trade_date'] = indicators_df['trade_date']

        indicator_mapping = {
            'MA5': 'ma5', 'MA10': 'ma10', 'MA20': 'ma20', 'MA60': 'ma60',
            'MACD_HIST': 'macd', 'MACD': 'dif', 'MACD_SIGNAL': 'dea'
        }
        for src_col, dst_col in indicator_mapping.items():
            if src_col in indicators_df.columns:
                save_df[dst_col] = indicators_df[src_col].fillna(0)
            else:
                save_df[dst_col] = 0

        for window, col_name in [(6, 'rsi6'), (12, 'rsi12'), (24, 'rsi24')]:
            try:
                rsi_df = TechnicalIndicator.calculate_rsi(quotes_df.copy(), window=window, require_adjust=False)
                if 'RSI' in rsi_df.columns:
                    save_df[col_name] = rsi_df['RSI'].fillna(0)
                else:
                    save_df[col_name] = 0
            except Exception:
                save_df[col_name] = 0

        save_df['trade_time'] = save_df['trade_date'].apply(
            lambda x: f"{x.strftime('%Y-%m-%d')} 15:00:00" if hasattr(x, 'strftime') else f"{str(x)[:10]} 15:00:00"
        )
        save_df['trade_datetime'] = save_df['trade_time']

        count = storage.save_indicators(save_df)
        if count > 0:
            success += 1
            total_records += count
            logger.info(f"[{i+1}/{len(to_backfill)}] {code} ✅ 写入 {count} 条")
        else:
            fail += 1
            fail_codes.append((code, "save_indicators returned 0"))
    except Exception as e:
        fail += 1
        fail_codes.append((code, str(e)))
        logger.error(f"[{i+1}/{len(to_backfill)}] {code} ❌ 失败: {e}")

    if (i + 1) % 20 == 0:
        logger.info(f"进度: {i+1}/{len(to_backfill)}, 成功 {success}, 失败 {fail}, 记录 {total_records}")

logger.info("=" * 60)
logger.info(f"补跑完成: 成功 {success}, 失败 {fail}, 总记录 {total_records}")
if fail_codes:
    logger.info("失败列表:")
    for code, reason in fail_codes[:20]:
        logger.info(f"  {code}: {reason}")
logger.info("=" * 60)

storage.disconnect()

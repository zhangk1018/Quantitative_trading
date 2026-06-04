#!/usr/bin/env python3
"""
快速下载程序 v2.0 - 使用 Akshare 数据源
支持增量更新股票数据
"""
import pandas as pd
import os
import glob
from datetime import datetime, timedelta
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 尝试导入 Akshare
HAS_AKSHARE = False
AKSHARE_FETCHER = None

try:
    from akshare_fetcher import AkshareFetcher
    AKSHARE_FETCHER = AkshareFetcher()
    HAS_AKSHARE = True
    logger.info('✅ 已启用 Akshare 数据源（免费无限制）')
except ImportError:
    logger.error('❌ 未安装 Akshare，请先安装: pip install akshare')
    exit(1)
except Exception as e:
    logger.error(f'❌ Akshare 初始化失败: {e}')
    exit(1)


def load_stock_list():
    """加载股票列表"""
    local_path = 'data/metadata/stock_list.parquet'
    if os.path.exists(local_path):
        return pd.read_parquet(local_path)
    else:
        logger.error(f'❌ 找不到股票列表文件: {local_path}')
        return None


def is_trading_time():
    """判断是否在交易时间内"""
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:
        return False
    current_time = now.time()
    morning_start = timedelta(hours=9, minutes=30)
    afternoon_end = timedelta(hours=15, minutes=0)
    current_timedelta = timedelta(hours=current_time.hour, minutes=current_time.minute)
    return morning_start <= current_timedelta <= afternoon_end


def get_local_stocks():
    """获取本地已有的股票列表"""
    files = glob.glob('data/price/daily/*.parquet')
    return [os.path.basename(f).replace('.parquet', '') for f in files]


def get_latest_date(stock_code):
    """获取股票最新日期"""
    filepath = f'data/price/daily/{stock_code}.parquet'
    if os.path.exists(filepath):
        df = pd.read_parquet(filepath)
        if not df.empty:
            latest_date = df['trade_date'].max()
            # 确保返回字符串格式 'YYYYMMDD'
            if isinstance(latest_date, pd.Timestamp):
                return latest_date.strftime('%Y%m%d')
            return str(latest_date).replace('-', '')
    return None


def download_stock_data(stock_code, start_date, end_date):
    """从 Akshare 获取单只股票的日线数据"""
    try:
        logger.debug(f'⏳ 拉取 {stock_code}: {start_date} - {end_date}')
        df = AKSHARE_FETCHER.fetch_daily_data(stock_code, start_date, end_date)
        return df
    except Exception as e:
        logger.error(f'❌ 拉取失败 {stock_code}: {e}')
        return None


def get_trading_calendar(start_date, end_date):
    """从 Akshare 获取交易日历"""
    try:
        logger.info(f'📅 获取交易日历: {start_date} - {end_date}')
        df = AKSHARE_FETCHER.fetch_trade_calendar(start_date, end_date)
        if df is not None and not df.empty:
            return df['trade_date'].tolist()
        return []
    except Exception as e:
        logger.error(f'❌ 获取交易日历失败: {e}')
        return []


def main():
    logger.info('='*70)
    logger.info('🚀 快速批量拉取模式（Akshare）')
    logger.info('='*70)

    if not is_trading_time():
        logger.warning('⏰ 当前非交易时段，仅检查已有数据')

    stock_list = load_stock_list()
    if stock_list is None or stock_list.empty:
        logger.error('❌ 股票列表为空')
        return

    local_stocks = get_local_stocks()
    logger.info(f'✅ 本地已有 {len(local_stocks)} 只股票')

    target_stocks = [s for s in stock_list['ts_code'].tolist() if s in local_stocks]
    logger.info(f'🎯 目标更新 {len(target_stocks)} 只股票')

    today = datetime.now().strftime('%Y%m%d')
    start_date = '20250101'

    trading_dates = get_trading_calendar(start_date, today)
    logger.info(f'📅 待处理交易日: {len(trading_dates)} 个')

    success_count = 0
    fail_count = 0

    for stock_code in target_stocks:
        try:
            latest_date = get_latest_date(stock_code)

            # 确定需要获取的日期范围
            if latest_date:
                need_dates = [d for d in trading_dates if d > latest_date]
            else:
                need_dates = trading_dates

            if not need_dates:
                logger.debug(f'✅ {stock_code} 已是最新')
                success_count += 1
                continue

            # 获取数据
            df = download_stock_data(stock_code, min(need_dates), max(need_dates))

            if df is None or df.empty:
                logger.warning(f'⚠️ {stock_code} 没有新数据')
                fail_count += 1
                continue

            # 保存数据
            filepath = f'data/price/daily/{stock_code}.parquet'
            if os.path.exists(filepath):
                existing_df = pd.read_parquet(filepath)
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['trade_date'], keep='last')
                combined_df = combined_df.sort_values('trade_date')
            else:
                combined_df = df

            os.makedirs('data/price/daily', exist_ok=True)
            combined_df.to_parquet(filepath)
            logger.info(f'💾 {stock_code}: 更新 {len(df)} 条记录')
            success_count += 1

            # 避免请求过于频繁
            time.sleep(0.3)

        except Exception as e:
            logger.error(f'❌ 处理失败 {stock_code}: {e}')
            fail_count += 1

    logger.info('='*70)
    logger.info(f'✅ 完成！成功: {success_count}, 失败: {fail_count}')
    logger.info('='*70)


if __name__ == '__main__':
    main()

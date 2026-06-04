#!/usr/bin/env python3
"""
批量下载程序 v2.0 - 使用 Akshare 数据源
支持按日期批量获取股票数据
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


def get_trading_calendar(start_date, end_date):
    """从 Akshare 获取交易日历"""
    try:
        logger.info('Getting trading calendar: %s - %s', start_date, end_date)
        df = AKSHARE_FETCHER.fetch_trade_calendar(start_date, end_date)
        if df is not None and not df.empty:
            return df['trade_date'].tolist()
        return []
    except Exception as e:
        logger.error('Failed to get calendar: %s', e)
        return []


def download_date_data(trade_date):
    """从 Akshare 获取指定日期的所有股票数据"""
    try:
        logger.info('Downloading %s...', trade_date)
        # Akshare 没有按日期批量获取的接口，这里使用替代方案
        # 我们会在主循环中逐个股票获取
        return None
    except Exception as e:
        logger.error('Failed %s: %s', trade_date, e)
        return None


def download_stock_data(stock_code, start_date, end_date):
    """从 Akshare 获取单只股票的日线数据"""
    try:
        logger.debug('Downloading %s: %s - %s', stock_code, start_date, end_date)
        df = AKSHARE_FETCHER.fetch_daily_data(stock_code, start_date, end_date)
        return df
    except Exception as e:
        logger.error('Download failed %s: %s', stock_code, e)
        return None


def update_stock_data(stock_code, new_df):
    """更新单只股票的数据"""
    try:
        filepath = 'data/price/daily/' + stock_code + '.parquet'

        if os.path.exists(filepath):
            existing_df = pd.read_parquet(filepath)
            # Ensure trade_date is consistent type (string)
            existing_df['trade_date'] = existing_df['trade_date'].astype(str)
            new_df['trade_date'] = new_df['trade_date'].astype(str)

            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['trade_date'], keep='last')
            combined_df = combined_df.sort_values('trade_date')
        else:
            combined_df = new_df.copy()
            combined_df['trade_date'] = combined_df['trade_date'].astype(str)

        if not combined_df.empty:
            os.makedirs('data/price/daily', exist_ok=True)
            combined_df.to_parquet(filepath)
            return True

        return False
    except Exception as e:
        logger.error('Update failed %s: %s', stock_code, e)
        return False


def get_stock_latest_date(stock_code):
    """获取股票最新日期"""
    try:
        filepath = 'data/price/daily/' + stock_code + '.parquet'
        if os.path.exists(filepath):
            df = pd.read_parquet(filepath)
            if not df.empty:
                latest_date = df['trade_date'].max()
                if pd.isna(latest_date):
                    return None
                if isinstance(latest_date, pd.Timestamp):
                    return latest_date.strftime('%Y%m%d')
                return str(latest_date).replace('-', '')
    except Exception as e:
        logger.error('Get latest date failed %s: %s', stock_code, e)
    return None


def get_local_trading_dates(stock_codes):
    """从本地股票文件中收集所有交易日期"""
    all_dates = set()
    for stock_code in stock_codes:
        try:
            filepath = 'data/price/daily/' + stock_code + '.parquet'
            if os.path.exists(filepath):
                df = pd.read_parquet(filepath)
                if not df.empty and 'trade_date' in df.columns:
                    # 确保日期格式统一
                    for date in df['trade_date']:
                        if isinstance(date, pd.Timestamp):
                            date_str = date.strftime('%Y%m%d')
                        else:
                            date_str = str(date).replace('-', '')
                        all_dates.add(date_str)
        except Exception as e:
            logger.error('Collect dates failed %s: %s', stock_code, e)
    # 排序返回
    return sorted(list(all_dates))


def main():
    logger.info('='*70)
    logger.info('Smart Bulk Download Mode (Akshare)')
    logger.info('='*70)

    stock_files = glob.glob('data/price/daily/*.parquet')
    stock_codes = [os.path.basename(f).replace('.parquet', '') for f in stock_files]
    logger.info('Local stocks: %d', len(stock_codes))

    if not stock_codes:
        logger.error('No local stocks found!')
        return

    # 获取日期范围
    today = datetime.now().strftime('%Y%m%d')
    start_date = '20250101'

    # 找到所有股票中最早需要更新的日期
    earliest_needed_date = None
    for stock_code in stock_codes:
        latest_date = get_stock_latest_date(stock_code)
        if latest_date:
            if not earliest_needed_date or latest_date < earliest_needed_date:
                earliest_needed_date = latest_date
        else:
            earliest_needed_date = '20250101'
            break

    if earliest_needed_date:
        start_date = earliest_needed_date
        logger.info('Starting from %s (oldest local data)', start_date)
    else:
        logger.info('No local data, starting from %s', start_date)

    # 获取交易日历
    trading_dates = get_trading_calendar(start_date, today)

    # 如果API失败，使用本地交易日期
    if not trading_dates and stock_codes:
        logger.info('API failed, using local trading dates...')
        local_dates = get_local_trading_dates(stock_codes)
        trading_dates = [d for d in local_dates if start_date <= d <= today]
        if today not in trading_dates:
            trading_dates.append(today)
            trading_dates.sort()

    if not trading_dates:
        logger.error('No trading dates found')
        return

    logger.info('Trading days to process: %d', len(trading_dates))
    logger.info('Most recent dates first')

    # 按日期倒序处理（先处理最近的日期）
    success_count = 0
    fail_count = 0

    for stock_code in stock_codes:
        try:
            latest_date = get_stock_latest_date(stock_code)
            
            # 确定需要获取的日期范围
            if latest_date:
                # 只获取最新日期之后的数据
                need_dates = [d for d in trading_dates if d > latest_date]
            else:
                need_dates = trading_dates

            if not need_dates:
                logger.debug('%s is up to date', stock_code)
                success_count += 1
                continue

            # 获取数据
            df = download_stock_data(stock_code, min(need_dates), max(need_dates))

            if df is None or df.empty:
                logger.warning('No new data for %s', stock_code)
                fail_count += 1
                continue

            # 更新数据
            if update_stock_data(stock_code, df):
                logger.info('✅ %s updated: %d new records', stock_code, len(df))
                success_count += 1
            else:
                logger.warning('⚠️ %s update failed', stock_code)
                fail_count += 1

            # 避免请求过于频繁
            time.sleep(0.5)

        except Exception as e:
            logger.error('❌ Process failed %s: %s', stock_code, e)
            fail_count += 1

    logger.info('='*70)
    logger.info(f'Done! Success: {success_count}, Fail: {fail_count}')
    logger.info('='*70)


if __name__ == '__main__':
    main()

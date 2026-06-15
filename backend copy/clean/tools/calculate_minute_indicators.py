#!/usr/bin/env python3
"""
分钟线技术指标计算脚本

功能：
- 从 stock_quotes_minute 表读取分钟K线数据
- 计算 MA/MACD/RSI 指标
- 写入 stock_indicators 表
- 利用 task_progress 记录状态

用法：
    python scripts/calculate_minute_indicators.py                    # 全量计算
    python scripts/calculate_minute_indicators.py --code 000001      # 单股票计算
    python scripts/calculate_minute_indicators.py --cycle 5m        # 指定周期计算
    python scripts/calculate_minute_indicators.py --date 2026-01-15  # 指定日期计算
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import argparse
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from tqdm import tqdm

from base_importer import BaseDataImporter
from clean.processor.technical_indicator import TechnicalIndicator
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('minute_indicators')


class MinuteIndicatorCalculator(BaseDataImporter):
    """分钟线指标计算器 - 继承 BaseDataImporter"""

    def __init__(self):
        super().__init__()
        # 从配置加载参数
        self.ma_windows = config.indicators.get('ma_windows', [5, 10, 20, 60])
        self.rsi_windows = config.indicators.get('rsi_windows', [6, 12, 24])
        self.macd_span = config.indicators.get('macd_span', [12, 26, 9])
        self.default_cycles = config.minute_data.get('default_cycles', ['5m', '15m', '30m', '60m'])
        self.max_batch_size = config.indicators.get('max_batch_size', 5000)

    def fetch_minute_quotes(self, code: str, cycle: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """从 stock_quotes_minute 表读取数据"""
        try:
            cursor = self.storage.conn.cursor()
            cursor.execute("""
                SELECT code, cycle, trade_date, trade_time,
                       open, high, low, close, volume, amount, adjust_type
                FROM stock_quotes_minute
                WHERE code = %s AND cycle = %s
                  AND trade_date >= %s AND trade_date <= %s
                ORDER BY trade_time
            """, (code, cycle, start_date, end_date))

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            if not rows:
                logger.warning(f"读取数据为空: {code} {cycle} {start_date}~{end_date}")
                return None

            df = pd.DataFrame(rows, columns=columns)
            return df
        except Exception as e:
            logger.error(f"读取数据失败: {code} {cycle} - {e}")
            return None

    @staticmethod
    def calculate_rsi_wilder(series: pd.Series, window: int) -> pd.Series:
        """计算符合行业标准（Wilder）的 RSI
        
        处理边界情况：
        - 当 avg_loss == 0 时，RSI = 100（无损失，全部为上涨）
        - 当 avg_gain == 0 时，RSI = 0（无增益，全部为下跌）
        """
        delta = series.diff(1)
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(alpha=1/window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/window, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        # 安全向量化赋值，避免 .loc 警告
        rsi = rsi.where(avg_loss > 0, 100.0)
        rsi = rsi.where(avg_gain > 0, 0.0)
        
        return rsi

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        if df is None or len(df) == 0:
            return df

        # 提前过滤空值，减少后续计算量和内存复制
        df = df.dropna(subset=['close']).copy()
        if df.empty:
            return df

        result = df
        try:
            result['adjust_type'] = 'qfq'
            result['adjust_factor'] = 1.0
            result['created_at'] = datetime.now()

            for window in self.ma_windows:
                result[f'ma{window}'] = result['close'].rolling(window=window).mean()

            ema_fast = result['close'].ewm(span=self.macd_span[0], adjust=False).mean()
            ema_slow = result['close'].ewm(span=self.macd_span[1], adjust=False).mean()
            result['dif'] = ema_fast - ema_slow
            result['dea'] = result['dif'].ewm(span=self.macd_span[2], adjust=False).mean()
            result['macd'] = 2 * (result['dif'] - result['dea'])

            for window in self.rsi_windows:
                result[f'rsi{window}'] = self.calculate_rsi_wilder(result['close'], window)

            return result
        except Exception as e:
            logger.error(f"计算指标失败: {e}")
            raise

    def calculate_stock(self, code: str, cycles: List[str], start_date: str, end_date: str):
        total_records = 0
        total_expected = len(cycles)

        for cycle in cycles:
            self.update_task_progress('running', int(total_records / total_expected * 100) if total_expected > 0 else 0,
                                      f"正在计算 {code} {cycle}")

            df = self.fetch_minute_quotes(code, cycle, start_date, end_date)
            if df is None or len(df) < max(self.ma_windows):
                continue

            df = self.calculate_indicators(df)
            # 使用基类通用批量写入方法
            write_cols = ['code', 'cycle', 'trade_date', 'trade_time',
                          'ma5', 'ma10', 'ma20', 'ma60',
                          'macd', 'dif', 'dea',
                          'rsi6', 'rsi12', 'rsi24', 'created_at']
            update_cols = ['ma5', 'ma10', 'ma20', 'ma60',
                          'macd', 'dif', 'dea',
                          'rsi6', 'rsi12', 'rsi24']
            inserted = self.batch_write_to_db(df, 'stock_indicators', write_cols, update_cols, self.max_batch_size)
            total_records += inserted

            logger.info(f"计算完成: {code} {cycle} - {inserted} 条")

        self.update_task_progress('completed', 100, f"计算完成: {total_records} 条")
        return total_records

    def run(self, codes: List[str] = None, cycles: List[str] = None,
            start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        task_name = f"分钟线指标计算_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.create_task(task_name)

        if not cycles:
            cycles = self.default_cycles

        if not end_date:
            end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        if not codes:
            codes = self.get_stock_list()

        logger.info(f"开始计算: {len(codes)} 只股票, 周期: {cycles}, 日期: {start_date}~{end_date}")

        total_records = 0
        success_count = 0
        fail_count = 0

        # 使用 tqdm 进度条
        for i, code in enumerate(tqdm(codes, desc="计算进度")):
            try:
                records = self.calculate_stock(code, cycles, start_date, end_date)
                total_records += records
                success_count += 1
                self.update_task_progress('running', int((i+1) / len(codes) * 100),
                                         f"进度: {i+1}/{len(codes)}, 累计: {total_records} 条")
            except Exception as e:
                logger.error(f"计算失败: {code} - {e}")
                fail_count += 1

        logger.info(f"计算完成: 成功 {success_count}, 失败 {fail_count}, 总记录 {total_records}")
        return {
            'success': success_count,
            'failed': fail_count,
            'total_records': total_records
        }


def main():
    parser = argparse.ArgumentParser(description='分钟线技术指标计算脚本')
    parser.add_argument('--code', type=str, help='股票代码（如 000001）')
    parser.add_argument('--codes', type=str, help='股票代码列表（逗号分隔）')
    parser.add_argument('--all', action='store_true', 
                       help='计算数据库中所有股票（需 stock_basic 表存在）')
    parser.add_argument('--cycle', type=str, 
                       help=f'周期（逗号分隔，默认 {",".join(config.minute_data.default_cycles)}）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--debug', action='store_true', help='开启 DEBUG 日志')

    args = parser.parse_args()
    
    # 设置日志级别
    if args.debug:
        logger.setLevel('DEBUG')
        logger.debug("DEBUG 日志已开启")

    # 参数校验
    if args.start:
        try:
            BaseDataImporter.validate_date(args.start)
        except ValueError as e:
            logger.error(f"参数错误: {e}")
            return
            
    if args.end:
        try:
            BaseDataImporter.validate_date(args.end)
        except ValueError as e:
            logger.error(f"参数错误: {e}")
            return
            
    if args.start and args.end:
        try:
            BaseDataImporter.validate_date_range(args.start, args.end)
        except ValueError as e:
            logger.error(f"参数错误: {e}")
            return

    cycles = args.cycle.split(',') if args.cycle else None
    codes = []
    
    # 优先级: --all > --codes > --code
    if args.all:
        logger.info("📥 从数据库加载所有股票")
        with MinuteIndicatorCalculator() as calculator:
            codes = calculator.get_stock_list()
        logger.info(f"📊 共 {len(codes)} 只股票待计算")
    elif args.codes:
        logger.info(f"📥 从命令行参数加载股票")
        codes = args.codes.split(',')
    elif args.code:
        codes = [args.code]
    else:
        logger.error("❌ 请指定股票代码，使用 --code、--codes 或 --all")
        parser.print_help()
        return

    try:
        with MinuteIndicatorCalculator() as calculator:
            calculator.run(codes=codes, cycles=cycles, start_date=args.start, end_date=args.end)
    except Exception as e:
        logger.error(f"程序异常: {e}")
        raise


if __name__ == '__main__':
    main()

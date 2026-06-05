#!/usr/bin/env python3
"""
周线/月线数据导入脚本
支持从 Tushare 导入周线和月线数据
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import pandas as pd
from datetime import datetime
from typing import List

from collector.datasource.tushare import TushareDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.logger import setup_logger

logger = setup_logger('weekly_monthly_import')


class WeeklyMonthlyImporter:
    """周线/月线数据导入器"""
    
    def __init__(self):
        self.storage = PostgreSQLStorage({})
        self.storage.connect()
        self.tushare = TushareDataSource()
        
    def _ensure_db_connected(self):
        """确保数据库连接"""
        if not self.storage.conn or self.storage.conn.closed:
            self.storage.connect()
    
    def _format_code(self, code: str) -> str:
        """标准化股票代码格式"""
        code = str(code).strip().lower()
        if code.startswith('sh.') or code.startswith('sz.'):
            return code
        if code.startswith('sh'):
            return f'sh.{code[2:]}'
        if code.startswith('sz'):
            return f'sz.{code[2:]}'
        if code.isdigit() and len(code) == 6:
            if code.startswith('6') or code.startswith('9'):
                return f'sh.{code}'
            else:
                return f'sz.{code}'
        return code
    
    def get_stock_list(self) -> List[str]:
        """获取股票列表"""
        self._ensure_db_connected()
        with self.storage.conn.cursor() as cursor:
            cursor.execute("SELECT code FROM stock_basic WHERE code LIKE 'sh.%' OR code LIKE 'sz.%'")
            return [row[0] for row in cursor.fetchall()]
    
    def batch_get_last_trade_date(self, codes: List[str], cycle: str) -> dict:
        """批量获取股票最后交易日"""
        result = {}
        if not codes:
            return result
        
        cycle_map = {'weekly': '1w', 'monthly': '1m'}
        db_cycle = cycle_map[cycle]
        
        placeholders = ','.join(['%s'] * len(codes))
        query = f"SELECT code, MAX(trade_date) FROM stock_quotes WHERE code IN ({placeholders}) AND cycle = %s GROUP BY code"
        
        try:
            self._ensure_db_connected()
            with self.storage.conn.cursor() as cursor:
                cursor.execute(query, codes + [db_cycle])
                for row in cursor.fetchall():
                    result[row[0].replace('sh.', '').replace('sz.', '')] = row[1]
        except Exception as e:
            logger.warning(f"批量查询失败: {e}")
        
        return result
    
    def _process_kline_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理K线数据"""
        if df.empty:
            return df
        
        df = df.copy()
        
        # 确保列存在
        required_cols = ['trade_date', 'open', 'high', 'low', 'close', 'volume', 'amount']
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0
        
        # 转换日期格式
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
        
        # volume 需要转换为整数（股数）
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(int)
        
        # 处理缺失值
        df = df.fillna({
            'open': 0, 'high': 0, 'low': 0, 'close': 0,
            'pre_close': 0, 'amount': 0
        })
        
        return df
    
    def import_cycle_data(self, codes: List[str], cycle: str, start_date: str = None, end_date: str = None):
        """导入指定周期的数据"""
        if cycle not in ['weekly', 'monthly']:
            raise ValueError(f"不支持的周期: {cycle}")
        
        self._ensure_db_connected()
        self.tushare.connect()
        
        success = fail = skip = records = 0
        total = len(codes)
        
        # 预查询已有数据的股票
        last_date_cache = {}
        if not start_date:
            try:
                last_date_cache = self.batch_get_last_trade_date(codes, cycle)
            except Exception as e:
                logger.warning(f"预查询失败: {e}")
        
        cycle_map = {'weekly': '1w', 'monthly': '1m'}
        db_cycle = cycle_map[cycle]
        
        for i, code in enumerate(codes, 1):
            if getattr(self, '_interrupted', False):
                break
            
            if i % 50 == 0:
                self._ensure_db_connected()
            
            formatted = self._format_code(code)
            if not formatted:
                continue
            
            last_date = last_date_cache.get(code)
            if last_date:
                skip += 1
                if skip <= 3:
                    logger.debug(f"[{cycle}] {code} 已有数据({last_date})，跳过")
                continue
            
            current_start = start_date
            if not current_start:
                with self.storage.conn.cursor() as cursor:
                    cursor.execute("SELECT list_date FROM stock_basic WHERE code = %s", (formatted,))
                    r = cursor.fetchone()
                    current_start = r[0] if r else '2000-01-01'
            
            try:
                df = self.tushare.get_kline(code, cycle=cycle, start_date=current_start, end_date=end_date)
                if df is None or df.empty:
                    fail += 1
                    continue
                
                df = self._process_kline_data(df)
                if df is None or df.empty:
                    fail += 1
                    continue
                
                df['code'] = formatted
                df['cycle'] = db_cycle
                df['adjust_type'] = 'qfq'
                df = df[['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close', 'volume', 'amount', 'adjust_type']]
                
                cnt = self.storage.save_quotes(df)
                if cnt > 0:
                    success += 1
                    records += cnt
                else:
                    fail += 1
                
                if i % 100 == 0 or i == total:
                    logger.info(f"[{cycle}] 进度 {i}/{total}, 成功 {success}, 失败 {fail}")
            
            except Exception as e:
                logger.error(f"[{cycle}] {code} 失败: {e}")
                fail += 1
        
        self.tushare.disconnect()
        
        # ===== 任务总结日志 =====
        logger.info("=" * 70)
        logger.info(f"📊 【{cycle}数据导入任务总结】")
        logger.info(f"   • 任务状态: {'全部完成' if fail == 0 else f'部分完成(失败{fail}只)'}")
        logger.info(f"   • 处理股票: {total} 只")
        logger.info(f"   • 成功导入: {success} 只")
        logger.info(f"   • 导入失败: {fail} 只")
        logger.info(f"   • 跳过(已有数据): {skip} 只")
        logger.info(f"   • 总记录数: {records:,} 条")
        if fail > 0:
            logger.warning(f"   ⚠️  警告: 有 {fail} 只股票导入失败，请检查网络或数据源状态")
        logger.info(f"   • 数据覆盖: 从 {start_date if start_date else '上市日'} 到 {end_date if end_date else '最新'}")
        logger.info("=" * 70)
        
        return success, fail, skip, records


def main():
    parser = argparse.ArgumentParser(description='周线/月线数据导入')
    parser.add_argument('--cycle', required=True, choices=['weekly', 'monthly'], help='周期类型')
    parser.add_argument('--code', help='单只股票代码')
    parser.add_argument('--start', help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', help='结束日期 (YYYY-MM-DD)')
    args = parser.parse_args()
    
    importer = WeeklyMonthlyImporter()
    
    if args.code:
        codes = [args.code]
    else:
        codes = importer.get_stock_list()
        logger.info(f"获取股票列表: {len(codes)} 只")
    
    logger.info(f"开始导入{args.cycle}数据...")
    importer.import_cycle_data(codes, args.cycle, args.start, args.end)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
分钟线数据质量验证脚本

功能：
- 跳价检测：检测价格异常跳变
- 零成交过滤：标记成交量为零的记录
- 周期连续性校验：检查分钟线是否连续
- 数据完整性检查：验证数据范围和质量

用法：
    python scripts/validate_minute_data.py --code 000001 --cycle 5m
    python scripts/validate_minute_data.py --code 000001 --all-cycles
    python scripts/validate_minute_data.py --all-stocks --cycle 5m
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('validate_minute')

class MinuteDataValidator:
    def __init__(self):
        self.storage = self._init_storage()
    
    def _init_storage(self) -> PostgreSQLStorage:
        storage_config = config.storage.get('postgresql', {})
        storage = PostgreSQLStorage(storage_config)
        storage.connect()
        return storage
    
    def fetch_minute_data(self, code: str, cycle: str) -> pd.DataFrame:
        """获取指定股票和周期的分钟线数据"""
        cursor = self.storage.conn.cursor()
        cursor.execute("""
            SELECT * FROM stock_quotes_minute
            WHERE code = %s AND cycle = %s
            ORDER BY trade_date, trade_time
        """, (code, cycle))
        
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows, columns=columns)
        df['trade_time'] = pd.to_datetime(df['trade_time'])
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        return df
    
    def detect_price_jump(self, df: pd.DataFrame, threshold: float = 0.1) -> pd.DataFrame:
        """检测价格跳变异常（涨跌幅超过阈值）"""
        if len(df) < 2:
            return pd.DataFrame()
        
        df = df.copy().sort_values('trade_time')
        df['price_change'] = df['close'].pct_change().abs()
        jumps = df[df['price_change'] > threshold]
        
        if not jumps.empty:
            logger.warning(f"⚠️ 检测到 {len(jumps)} 条跳价记录（阈值: {threshold*100}%）")
        
        return jumps[['trade_time', 'close', 'price_change']]
    
    def detect_zero_volume(self, df: pd.DataFrame) -> pd.DataFrame:
        """检测零成交量记录"""
        zero_volume = df[df['volume'] == 0]
        
        if not zero_volume.empty:
            logger.warning(f"⚠️ 检测到 {len(zero_volume)} 条零成交量记录")
        
        return zero_volume[['trade_time', 'volume']]
    
    def check_continuity(self, df: pd.DataFrame, cycle: str) -> List[str]:
        """检查分钟线周期连续性"""
        if len(df) < 2:
            return []
        
        cycle_minutes = {
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '60m': 60
        }
        
        expected_interval = timedelta(minutes=cycle_minutes.get(cycle, 5))
        df = df.copy().sort_values('trade_time')
        
        gaps = []
        times = df['trade_time'].tolist()
        
        for i in range(1, len(times)):
            gap = times[i] - times[i-1]
            if gap > expected_interval:
                gaps.append(f"{times[i-1]} → {times[i]} (间隔: {gap})")
        
        if gaps:
            logger.warning(f"⚠️ 检测到 {len(gaps)} 处周期不连续")
        
        return gaps
    
    def check_data_range(self, df: pd.DataFrame) -> Dict:
        """检查数据时间范围"""
        if df.empty:
            return {'has_data': False}
        
        return {
            'has_data': True,
            'start_date': df['trade_time'].min().strftime('%Y-%m-%d %H:%M:%S'),
            'end_date': df['trade_time'].max().strftime('%Y-%m-%d %H:%M:%S'),
            'total_records': len(df),
            'distinct_days': df['trade_date'].nunique()
        }
    
    def validate_stock_cycle(self, code: str, cycle: str) -> Dict:
        """验证单只股票单个周期的数据质量"""
        logger.info(f"🔍 开始验证: {code} {cycle}")
        
        df = self.fetch_minute_data(code, cycle)
        
        if df.empty:
            logger.warning(f"❌ 无数据: {code} {cycle}")
            return {
                'code': code,
                'cycle': cycle,
                'has_data': False,
                'errors': [],
                'warnings': []
            }
        
        result = {
            'code': code,
            'cycle': cycle,
            'has_data': True,
            'data_range': self.check_data_range(df),
            'errors': [],
            'warnings': []
        }
        
        # 跳价检测
        jumps = self.detect_price_jump(df)
        if not jumps.empty:
            result['warnings'].append(f"跳价异常: {len(jumps)} 条")
            result['jump_details'] = jumps.to_dict('records')
        
        # 零成交检测
        zero_volume = self.detect_zero_volume(df)
        if not zero_volume.empty:
            result['warnings'].append(f"零成交量: {len(zero_volume)} 条")
            result['zero_volume_details'] = zero_volume.to_dict('records')
        
        # 连续性检查
        gaps = self.check_continuity(df, cycle)
        if gaps:
            result['warnings'].append(f"周期不连续: {len(gaps)} 处")
            result['gap_details'] = gaps
        
        if not result['warnings']:
            logger.info(f"✅ 验证通过: {code} {cycle}")
        
        return result
    
    def validate_stock_all_cycles(self, code: str) -> List[Dict]:
        """验证单只股票所有周期"""
        cycles = ['5m', '15m', '30m', '60m']
        results = []
        
        for cycle in cycles:
            result = self.validate_stock_cycle(code, cycle)
            results.append(result)
        
        return results
    
    def validate_all_stocks(self, cycle: str = '5m') -> List[Dict]:
        """验证所有股票指定周期"""
        cursor = self.storage.conn.cursor()
        cursor.execute("SELECT code FROM stock_basic WHERE delist_date IS NULL ORDER BY code")
        codes = [row[0] for row in cursor.fetchall()]
        
        results = []
        for code in codes:
            result = self.validate_stock_cycle(code, cycle)
            results.append(result)
        
        return results
    
    def generate_report(self, results: List[Dict]) -> str:
        """生成验证报告"""
        report = ["\n" + "="*60]
        report.append("          分钟线数据质量验证报告")
        report.append("="*60)
        
        total = len(results)
        passed = sum(1 for r in results if r['has_data'] and not r['warnings'])
        failed = sum(1 for r in results if not r['has_data'])
        warning = sum(1 for r in results if r['has_data'] and r['warnings'])
        
        report.append(f"\n📊 总体统计")
        report.append(f"  验证数量: {total}")
        report.append(f"  ✅ 通过: {passed}")
        report.append(f"  ⚠️ 警告: {warning}")
        report.append(f"  ❌ 无数据: {failed}")
        
        report.append("\n📋 警告详情")
        for r in results:
            if r['warnings']:
                report.append(f"\n  {r['code']} {r['cycle']}:")
                for w in r['warnings']:
                    report.append(f"    - {w}")
        
        report.append("\n" + "="*60)
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description='分钟线数据质量验证脚本')
    parser.add_argument('--code', type=str, help='股票代码（如 000001）')
    parser.add_argument('--cycle', type=str, default='5m',
                       help='周期（5m/15m/30m/60m，默认5m）')
    parser.add_argument('--all-cycles', action='store_true',
                       help='验证该股票所有周期')
    parser.add_argument('--all-stocks', action='store_true',
                       help='验证所有股票指定周期')
    parser.add_argument('--output', type=str, help='输出报告文件路径')
    
    args = parser.parse_args()
    
    validator = MinuteDataValidator()
    results = []
    
    if args.all_stocks:
        logger.info(f"🔍 验证所有股票 {args.cycle} 周期")
        results = validator.validate_all_stocks(args.cycle)
    elif args.all_cycles and args.code:
        logger.info(f"🔍 验证 {args.code} 所有周期")
        results = validator.validate_stock_all_cycles(args.code)
    elif args.code:
        logger.info(f"🔍 验证 {args.code} {args.cycle}")
        results = [validator.validate_stock_cycle(args.code, args.cycle)]
    else:
        parser.print_help()
        return
    
    report = validator.generate_report(results)
    print(report)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        logger.info(f"📝 报告已保存到: {args.output}")


if __name__ == '__main__':
    main()
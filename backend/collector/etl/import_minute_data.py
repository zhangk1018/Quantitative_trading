#!/usr/bin/env python3
"""
分钟线数据导入脚本

功能：
- 从数据源（baostock）拉取 5m/15m/30m/60m K线
- 写入 stock_quotes_minute 表
- 利用 task_progress 记录状态
- 支持全量导入和增量导入
- 集成三重数据校验机制
- 集成智能重试机制

用法：
    python scripts/import_minute_data.py                    # 全量导入（最近30天）
    python scripts/import_minute_data.py --code 000001      # 单股票导入
    python scripts/import_minute_data.py --cycle 5m        # 指定周期导入
    python scripts/import_minute_data.py --date 2026-01-15  # 指定日期导入
    python scripts/import_minute_data.py --incremental      # 增量导入（从上次最新数据开始）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import argparse
import time
import traceback
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from tqdm import tqdm

from collector.datasource.base import DataSourceManager, create_dsm, SwitchStrategy
from base_importer import BaseDataImporter
from clean.processor.data_quality_checker import DataQualityChecker
from utils.error_classifier import ErrorClassifier, ErrorType
from utils.config import config
from utils.logger import setup_logger
from utils.metrics import GlobalMetrics, metrics_context

logger = setup_logger('minute_import')

CYCLE_MAP = {
    '5m': ('min5', '5'),
    '15m': ('min15', '15'),
    '30m': ('min30', '30'),
    '60m': ('min60', '60')
}

VALID_CYCLES = ['5m', '15m', '30m', '60m']


class MinuteDataImporter(BaseDataImporter):
    """分钟线数据导入器 - 继承 BaseDataImporter，集成数据校验和智能重试"""

    def __init__(self):
        super().__init__()
        # 使用数据源管理器，支持多数据源切换
        self.dsm = create_dsm(
            strategy=config.data_source.get('strategy', 'failover'),
            auto_recovery=True,
            health_check_interval=config.data_source.get('health_check_interval', 30)
        )
        self.quality_checker = DataQualityChecker()
        self.failed_stocks = []
        
        # 从配置加载参数
        self.batch_days = config.minute_data.get('batch_days', 10)
        self.max_batch_size = config.minute_data.get('max_batch_size', 5000)
        self.default_cycles = config.minute_data.get('default_cycles', ['5m', '15m', '30m', '60m'])
        self.api_delay = config.minute_data.get('api_delay', 0.3)
        self.max_retries = config.data_source.get('max_retries', 3)
        self.timeout_sec = config.data_source.get('timeout_sec', 30)
        
        # 连接数据源
        self._connect_datasource()

    def _connect_datasource(self):
        """连接数据源"""
        try:
            if self.dsm.connect():
                logger.info(f"✅ 数据源连接成功: {self.dsm.current_source_name}")
            else:
                logger.error("❌ 数据源连接失败")
        except Exception as e:
            logger.error(f"❌ 数据源连接异常: {e}")

    def disconnect(self):
        """断开连接（包括数据源）"""
        if hasattr(self, 'dsm'):
            try:
                self.dsm.disconnect()
                logger.info("✅ 数据源已断开")
            except Exception as e:
                logger.warning(f"断开数据源失败: {e}")
        super().disconnect()

    def import_stock_data(self, code: str, start_date: str, end_date: str) -> int:
        """BaseDataImporter 要求实现的方法 - 导入单股票数据
        
        Returns:
            int: 成功导入的记录条数
        """
        return self.import_stock(code, self.default_cycles, start_date, end_date)

    @staticmethod
    def validate_cycles(cycles: List[str]) -> List[str]:
        """校验周期参数是否合法
        
        Args:
            cycles: 周期列表
            
        Returns:
            过滤后的合法周期列表
            
        Raises:
            ValueError: 如果所有周期都不合法
        """
        valid_cycles = [c for c in cycles if c in VALID_CYCLES]
        if not valid_cycles:
            raise ValueError(f"无效的周期参数: {cycles}，合法周期为: {VALID_CYCLES}")
        return valid_cycles

    def get_last_trade_time(self, code: str, cycle: str) -> Optional[datetime]:
        """获取数据库中该股票该周期最新的 trade_time"""
        with self.storage.conn.cursor() as cursor:
            cursor.execute("""
                SELECT MAX(trade_time) FROM stock_quotes_minute
                WHERE code = %s AND cycle = %s
            """, (code, cycle))
            row = cursor.fetchone()
        return row[0] if row and row[0] else None

    def fetch_minute_data_with_retry(self, code: str, cycle: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """分批拉取分钟线数据（集成智能重试机制和多数据源切换）
        
        Args:
            code: 股票代码
            cycle: 周期
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            合并后的完整 DataFrame
        """
        # 周期映射（统一对外接口）
        cycle_map = {
            '5m': 'min5',
            '15m': 'min15',
            '30m': 'min30',
            '60m': 'min60'
        }
        ds_cycle = cycle_map.get(cycle)
        if not ds_cycle:
            logger.error(f"不支持的周期: {cycle}")
            return None

        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            # 如果日期范围小于等于batch_days，直接拉取
            if (end_dt - start_dt).days <= self.batch_days:
                df = self._fetch_with_retry(code, ds_cycle, start_date, end_date)
                if df is None or len(df) == 0:
                    logger.debug(f"获取数据为空: {code} {cycle} {start_date}~{end_date}")
                    return None
                return df
            
            # 分批拉取，避免内存过高
            dfs = []
            current_dt = start_dt
            while current_dt <= end_dt:
                batch_end_dt = min(current_dt + timedelta(days=self.batch_days), end_dt)
                batch_start = current_dt.strftime('%Y-%m-%d')
                batch_end = batch_end_dt.strftime('%Y-%m-%d')
                
                logger.debug(f"分批拉取: {code} {cycle} {batch_start}~{batch_end}")
                df_batch = self._fetch_with_retry(code, ds_cycle, batch_start, batch_end)
                
                if df_batch is not None and len(df_batch) > 0:
                    dfs.append(df_batch)
                
                current_dt = batch_end_dt + timedelta(days=1)
                time.sleep(0.1)
            
            if not dfs:
                logger.debug(f"获取数据为空: {code} {cycle} {start_date}~{end_date}")
                return None
            
            df = pd.concat(dfs, ignore_index=True)
            logger.debug(f"合并完成: {code} {cycle} 共 {len(df)} 条")
            return df
            
        except Exception as e:
            error_type, _ = ErrorClassifier.classify(e)
            logger.error(f"获取数据失败: {code} {cycle} - [{error_type}] {e}")
            return None

    def _fetch_with_retry(self, code: str, ds_cycle: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """带重试机制的数据拉取（使用数据源管理器）
        
        Args:
            code: 股票代码
            ds_cycle: 数据源周期格式
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            DataFrame 或 None
        """
        retry_count = 0
        base_delay = self.api_delay
        
        while retry_count <= self.max_retries:
            try:
                # 使用数据源管理器获取数据（自动处理故障切换）
                df = self.dsm.get_kline(
                    code=code,
                    cycle=ds_cycle,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # 检查是否发生了数据源切换
                if self.dsm.has_fallback and retry_count == 0:
                    logger.info(f"🔄 数据源已切换到: {self.dsm.current_source_name}")
                
                return df
                
            except Exception as e:
                error_type, error_desc = ErrorClassifier.classify(e)
                
                if ErrorClassifier.should_retry(e, retry_count, self.max_retries):
                    retry_delay = ErrorClassifier.get_retry_delay(retry_count, int(base_delay))
                    logger.warning(f"可重试错误 [{error_type}]: {code} {ds_cycle} {start_date}~{end_date} - {error_desc}, "
                                   f"第 {retry_count + 1}/{self.max_retries} 次重试，延迟 {retry_delay}s")
                    time.sleep(retry_delay)
                    retry_count += 1
                else:
                    logger.error(f"不可重试错误 [{error_type}]: {code} {ds_cycle} {start_date}~{end_date} - {error_desc}")
                    return None
        
        logger.error(f"重试次数耗尽: {code} {ds_cycle} {start_date}~{end_date}")
        return None

    def transform_data(self, df: pd.DataFrame, cycle: str) -> pd.DataFrame:
        """数据转换（集成三重校验）
        
        Args:
            df: 原始数据
            cycle: 周期
            
        Returns:
            转换后的数据
        """
        if df is None or len(df) == 0:
            return df

        # 第一重校验：采集后校验
        result = self.quality_checker.check_data_source_connectivity(df, 'baostock')
        if result['status'] == 'error':
            logger.error(f"第一重校验失败: {result['message']}")
            return pd.DataFrame()
        
        result = pd.DataFrame()
        result['code'] = df['code'].apply(self._format_code)
        result['cycle'] = cycle
        result['adjust_type'] = 'qfq'
        result['created_at'] = datetime.now()

        # 安全解析分钟级时间（防止 astype(str) 将 NaN 转为 "nan"）
        if 'time' in df.columns and 'date' in df.columns:
            date_str = df['date'].astype(str).replace('nan', pd.NaT)
            time_str = df['time'].astype(str).replace('nan', pd.NaT)
            result['trade_time'] = pd.to_datetime(date_str + ' ' + time_str, errors='coerce')
        elif 'datetime' in df.columns:
            result['trade_time'] = pd.to_datetime(df['datetime'], errors='coerce')
        else:
            result['trade_time'] = pd.to_datetime(df.get('trade_date', df.get('date')), errors='coerce')

        # 过滤解析失败的脏数据
        result = result.dropna(subset=['trade_time'])
        if result.empty:
            logger.warning(f"时间解析失败，所有数据被过滤")
            return result

        result['trade_date'] = result['trade_time'].dt.date

        # 数值转换
        price_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        for col in price_cols:
            result[col] = pd.to_numeric(df.get(col), errors='coerce')
        result['volume'] = result['volume'].fillna(0).astype(int)

        # VWAP 防除零
        mask = result['volume'] > 0
        result['vwap'] = np.nan
        result.loc[mask, 'vwap'] = (result.loc[mask, 'amount'] / result.loc[mask, 'volume']).round(4)

        # 第二重校验：入库前校验
        check_result = self.quality_checker.check_format_validity(result)
        if check_result['status'] == 'error':
            logger.error(f"第二重校验失败: {check_result['message']}")
            return pd.DataFrame()
        elif check_result['status'] == 'warning':
            logger.warning(f"第二重校验警告: {check_result['message']}")
        
        check_result = self.quality_checker.check_price_logic(result)
        if check_result['status'] == 'error':
            logger.error(f"价格逻辑校验失败: {check_result['message']}")
            # 过滤掉价格逻辑错误的数据
            if all(col in result.columns for col in ['high', 'low', 'close']):
                valid_mask = (result['high'] >= result['low']) & (result['high'] >= result['close']) & (result['close'] >= result['low'])
                result = result[valid_mask]
                logger.info(f"过滤价格逻辑错误数据后剩余 {len(result)} 条")

        return result

    def import_stock(self, code: str, cycles: List[str], start_date: str, end_date: str, 
                     incremental: bool = False, last_time_cache: Dict[str, Dict[str, datetime]] = None) -> int:
        """导入单只股票的分钟线数据
        
        Args:
            code: 股票代码
            cycles: 周期列表
            start_date: 开始日期
            end_date: 结束日期
            incremental: 是否增量导入
            last_time_cache: 预查询的最后交易时间缓存，格式: {cycle: {code: datetime}}
            
        Returns:
            成功导入的记录总数
        """
        total_records = 0
        
        # 校验股票代码格式
        formatted_code = self._format_code(code)
        if not formatted_code:
            logger.warning(f"跳过格式不合法的股票代码: {code}")
            return 0
        code = formatted_code

        for cycle in cycles:
            self.update_task_progress('running', total_records % 100, f"正在导入 {code} {cycle}")

            # 增量导入：获取上次最新时间戳（优先使用缓存）
            actual_start_date = start_date
            last_time = None
            if incremental:
                # 使用预查询的缓存，避免逐只查询
                if last_time_cache and cycle in last_time_cache:
                    last_time = last_time_cache[cycle].get(code)
                else:
                    # 回退到单只查询
                    last_time = self.get_last_trade_time(code, cycle)
                if last_time:
                    actual_start_datetime = last_time + timedelta(minutes=1)
                    actual_start_date = actual_start_datetime.strftime('%Y-%m-%d')
                    logger.info(f"📈 增量模式: {code} {cycle} 上次最新时间: {last_time}，从 {actual_start_datetime} 开始")
                else:
                    logger.info(f"📊 首次导入: {code} {cycle}")

            # 检查日期范围有效性
            if actual_start_date and end_date:
                if actual_start_date > end_date:
                    logger.info(f"⏭️ {code} {cycle} 无新数据（{actual_start_date} > {end_date}），跳过")
                    continue

            # 分批拉取分钟线数据（集成重试机制）
            df = self.fetch_minute_data_with_retry(code, cycle, actual_start_date, end_date)
            if df is None:
                continue

            df = self.transform_data(df, cycle)
            if df.empty:
                continue
            
            # 如果是增量模式且有上次时间，过滤掉已存在的数据（精确到分钟）
            if incremental and last_time:
                df = df[df['trade_time'] > last_time]
                logger.debug(f"增量过滤后剩余 {len(df)} 条新数据")

            # 使用基类通用批量写入方法
            write_cols = ['code', 'cycle', 'trade_date', 'trade_time',
                          'open', 'high', 'low', 'close', 'volume', 'amount', 'vwap', 'adjust_type', 'created_at']
            update_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'vwap', 'adjust_type']
            inserted = self.batch_write_to_db(df, 'stock_quotes_minute', write_cols, update_cols, self.max_batch_size)
            total_records += inserted

            logger.info(f"导入完成: {code} {cycle} - {inserted} 条")

        self.update_task_progress('completed', 100, f"导入完成: {total_records} 条")
        return total_records

    def run(self, codes: List[str] = None, cycles: List[str] = None,
            start_date: str = None, end_date: str = None, incremental: bool = False,
            delay: float = None) -> Dict[str, Any]:
        """执行分钟线数据导入任务
        
        Args:
            codes: 股票代码列表
            cycles: 周期列表
            start_date: 开始日期
            end_date: 结束日期
            incremental: 是否增量导入
            delay: 每只股票导入间隔（秒）
            
        Returns:
            导入结果统计字典
        """
        if delay is None:
            delay = self.api_delay
            
        self.failed_stocks = []
        
        task_name = f"分钟线数据导入_{('增量' if incremental else '全量')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.create_task(task_name)

        # 校验周期参数
        if not cycles:
            cycles = self.default_cycles
        else:
            try:
                cycles = self.validate_cycles(cycles)
                logger.info(f"校验通过的周期: {cycles}")
            except ValueError as e:
                logger.error(f"周期参数校验失败: {e}")
                self.update_task_progress('failed', 0, str(e))
                return {'success': 0, 'failed': 0, 'total_records': 0, 'failed_stocks': []}

        if not end_date:
            end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        if not start_date and not incremental:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        if not codes:
            codes = self.get_stock_list()
        
        codes = list(set(codes))
        valid_codes = [c for c in codes if self.validate_stock_code(c)]
        invalid_codes = [c for c in codes if not self.validate_stock_code(c)]
        if invalid_codes:
            logger.warning(f"过滤无效股票代码: {invalid_codes}")
        codes = valid_codes

        mode = "增量" if incremental else "全量"
        logger.info(f"开始{mode}导入: {len(codes)} 只股票, 周期: {cycles}, 日期: {start_date if start_date else '自动'}~{end_date}, 间隔: {delay}s")

        total_records = 0
        success_count = 0
        fail_count = 0

        # 增量模式优化：预批量查询所有股票的最后交易时间（避免逐只查询）
        last_time_cache = {}
        if incremental:
            logger.info("⏩ 增量模式：预批量查询所有股票的最后交易时间...")
            for cycle in cycles:
                last_time_cache[cycle] = self.batch_get_last_trade_time(codes, cycle)
            logger.info("✅ 预查询完成")

        # 初始化监控指标
        with metrics_context(f"minute_import_{'incremental' if incremental else 'full'}") as metrics:
            metrics.start_timer('total')
            
            for i, code in enumerate(tqdm(codes, desc="导入进度")):
                try:
                    records = self.import_stock(code, cycles, start_date, end_date, incremental, last_time_cache)
                    total_records += records
                    success_count += 1
                    # 记录指标
                    metrics.add_record(success=True)
                    metrics.add_stock(success=True)
                    metrics.records_processed += records
                    self.update_task_progress('running', int((i+1) / len(codes) * 100),
                                            f"进度: {i+1}/{len(codes)}, 累计: {total_records} 条")
                except Exception as e:
                    error_type, error_desc = ErrorClassifier.classify(e)
                    logger.error(f"导入失败 [{error_type}]: {code} - {error_desc}")
                    fail_count += 1
                    # 记录指标
                    metrics.add_record(success=False)
                    metrics.add_stock(success=False)
                    metrics.add_error(error_desc, {'code': code})
                    self.failed_stocks.append({
                        'code': code,
                        'error': error_desc,
                        'type': error_type,
                        'stack_trace': traceback.format_exc()
                    })
                    continue

                time.sleep(delay)

            metrics.end_timer('total')

        if self.failed_stocks:
            logger.error(f"失败股票列表 ({len(self.failed_stocks)} 只):")
            for fail in self.failed_stocks:
                logger.error(f"  - [{fail['type']}] {fail['code']}: {fail['error']}")
        
        if self.failed_stocks:
            fail_file = f"failed_stocks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            with open(fail_file, 'w') as f:
                for fail in self.failed_stocks:
                    f.write(f"{fail['code']},{fail['type']},{fail['error']}\n")
                    f.write(f"Stack Trace:\n{fail['stack_trace']}\n\n")
            logger.info(f"失败股票列表已保存到: {fail_file}")

        logger.info(f"导入完成: 成功 {success_count}, 失败 {fail_count}, 总记录 {total_records}")
        
        if fail_count > 0:
            self.update_task_progress('completed', 100, 
                                    f"导入完成: 成功 {success_count}, 失败 {fail_count}, 总记录 {total_records}")
        else:
            self.update_task_progress('completed', 100, f"导入完成: {total_records} 条")

        return {
            'success': success_count,
            'failed': fail_count,
            'total_records': total_records,
            'failed_stocks': self.failed_stocks
        }


def load_codes_from_csv(file_path: str) -> List[str]:
    """从CSV文件加载股票代码列表"""
    try:
        df = pd.read_csv(file_path)
        code_columns = ['code', '股票代码', '证券代码', 'symbol']
        for col in code_columns:
            if col in df.columns:
                return df[col].astype(str).str.strip().tolist()
        logger.error(f"CSV文件中未找到代码列: {code_columns}")
        return []
    except Exception as e:
        logger.error(f"读取CSV文件失败: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description='分钟线数据导入脚本')
    parser.add_argument('--code', type=str, help='股票代码（如 000001）')
    parser.add_argument('--codes', type=str, help='股票代码列表（逗号分隔）或CSV文件路径')
    parser.add_argument('--all', action='store_true', 
                       help='导入数据库中所有股票（需 stock_basic 表存在）')
    parser.add_argument('--cycle', type=str, 
                       help=f'周期（逗号分隔，默认 {",".join(config.minute_data.get("default_cycles", ["5m", "15m", "30m", "60m"]))}）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--incremental', action='store_true', 
                       help='增量导入模式（从数据库中最新数据之后开始）')
    parser.add_argument('--delay', type=float, 
                       help='每只股票导入间隔（秒），用于API限频')
    parser.add_argument('--debug', action='store_true', help='开启 DEBUG 日志')

    args = parser.parse_args()
    
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
            
    if args.delay is not None and args.delay < 0:
        logger.error(f"参数错误: delay 不能为负数: {args.delay}")
        return

    cycles = args.cycle.split(',') if args.cycle else None
    codes = []
    
    if args.all:
        logger.info("📥 从数据库加载所有股票")
        with MinuteDataImporter() as importer:
            codes = importer.get_stock_list()
        logger.info(f"📊 共 {len(codes)} 只股票待导入")
    elif args.codes:
        if args.codes.endswith('.csv') and os.path.exists(args.codes):
            logger.info(f"📥 从CSV文件加载股票: {args.codes}")
            codes = load_codes_from_csv(args.codes)
        else:
            logger.info(f"📥 从命令行参数加载股票")
            codes = args.codes.split(',')
    elif args.code:
        codes = [args.code]
    else:
        logger.error("❌ 请指定股票代码，使用 --code、--codes 或 --all")
        parser.print_help()
        return

    try:
        with MinuteDataImporter() as importer:
            importer.run(codes=codes, cycles=cycles, start_date=args.start,
                     end_date=args.end, incremental=args.incremental, delay=args.delay)
    except Exception as e:
        logger.error(f"程序异常: {e}")
        raise


if __name__ == '__main__':
    main()
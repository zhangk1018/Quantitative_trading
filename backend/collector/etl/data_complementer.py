#!/usr/bin/env python3
"""
数据补全工具

功能：
- 检测数据完整性
- 根据缺失类型智能补全数据
- 支持断点续传
- 生成完整性报告

用法：
    python -m collector.etl.data_complementer              # 检测并补全所有缺失数据
    python -m collector.etl.data_complementer --check-only # 仅检测不补全
    python -m collector.etl.data_complementer --date 2026-06-03  # 补全指定日期
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from clean.processor.base_importer import BaseDataImporter
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('data_complementer')


class MissingType(Enum):
    """缺失类型枚举"""
    NONE = "无缺失"                    # 数据完整
    LATEST_ONLY = "仅最新日期缺失"     # 只有今天没数据
    PARTIAL_DATES = "部分日期缺失"     # 某些日期缺失
    PARTIAL_STOCKS = "部分股票缺失"    # 部分股票缺失某些日期
    MASSIVE = "大量数据缺失"           # 超过50%的股票缺失数据


@dataclass
class DataIntegrityReport:
    """数据完整性报告"""
    total_stocks: int
    latest_date: str
    missing_type: MissingType
    missing_dates: List[str]
    missing_stocks_by_date: Dict[str, List[str]]  # {date: [stock_codes]}
    coverage_rate: float
    needs_complement: bool


class DataComplementer(BaseDataImporter):
    """数据补全工具"""

    # 配置
    MAX_RETRY = 3                    # 最大重试次数
    RETRY_DELAY = 5                  # 重试延迟（秒）
    BATCH_SIZE = 100                 # 每批处理股票数
    MIN_COVERAGE_RATE = 0.95         # 最低覆盖率要求（95%）

    def __init__(self):
        super().__init__()
        self.datasource = BaostockDataSource()
        self._interrupted = False

    def close(self):
        """关闭连接"""
        self.disconnect()

    def import_stock_data(self, code: str, start_date: str, end_date: str) -> int:
        """导入单只股票数据（实现抽象方法）"""
        try:
            bs_code = f"sz.{code}" if code.startswith('0') or code.startswith('SZ') else f"sh.{code}"
            df = self.datasource.get_kline(bs_code, cycle='daily', start_date=start_date, end_date=end_date)
            
            if df is None or df.empty:
                return 0
            
            df = self._process_kline_data(df)
            if df is None or df.empty:
                return 0
            
            formatted_code = self._format_code(code)
            if not formatted_code:
                return 0
            
            df['code'] = formatted_code
            df['cycle'] = '1d'
            df['adjust_type'] = 'qfq'
            
            if 'trade_datetime' not in df.columns:
                df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta('15:00:00')
            
            return self.storage.save_quotes(df)
        except Exception as e:
            logger.error(f"导入 {code} 失败: {e}")
            return 0

    def check_data_integrity(self, target_date: Optional[str] = None) -> DataIntegrityReport:
        """检测数据完整性
        
        Args:
            target_date: 目标日期，None表示检测所有数据
            
        Returns:
            DataIntegrityReport: 完整性报告
        """
        logger.info("🔍 开始检测数据完整性...")
        
        cursor = self.storage.conn.cursor()
        
        # 1. 获取股票总数
        cursor.execute("SELECT COUNT(*) FROM stock_basic WHERE delist_date IS NULL")
        total_stocks = cursor.fetchone()[0]
        
        # 2. 获取最新交易日期
        cursor.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
        latest_date = cursor.fetchone()[0]
        
        # 3. 获取最近30天的交易日历和覆盖情况
        start_date = (datetime.strptime(str(latest_date), '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT trade_date, COUNT(DISTINCT code) as stock_count
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date >= %s
            GROUP BY trade_date
            ORDER BY trade_date
        ''', (start_date,))
        
        date_coverage = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 4. 分析缺失类型
        missing_dates = []
        missing_stocks_by_date = {}
        
        if target_date:
            # 检测指定日期
            check_dates = [target_date]
        else:
            # 检测所有日期
            check_dates = list(date_coverage.keys())
        
        for date in check_dates:
            coverage = date_coverage.get(date, 0)
            coverage_rate = coverage / total_stocks if total_stocks > 0 else 0
            
            if coverage_rate < self.MIN_COVERAGE_RATE:
                missing_dates.append(date)
                
                # 找出缺失的股票
                cursor.execute('''
                    SELECT code FROM stock_basic 
                    WHERE delist_date IS NULL 
                    AND code NOT IN (
                        SELECT DISTINCT code FROM stock_quotes 
                        WHERE trade_date = %s AND cycle = '1d'
                    )
                ''', (date,))
                missing_stocks = [row[0] for row in cursor.fetchall()]
                missing_stocks_by_date[date] = missing_stocks
        
        # 5. 判断缺失类型
        if not missing_dates:
            missing_type = MissingType.NONE
            coverage_rate = 1.0
        elif len(missing_dates) == 1 and missing_dates[0] == str(latest_date):
            missing_type = MissingType.LATEST_ONLY
            coverage_rate = date_coverage.get(latest_date, 0) / total_stocks
        elif len(missing_dates) <= 3:
            missing_type = MissingType.PARTIAL_DATES
            coverage_rate = sum(date_coverage.get(d, 0) for d in missing_dates) / (total_stocks * len(missing_dates))
        else:
            missing_type = MissingType.MASSIVE
            coverage_rate = sum(date_coverage.get(d, 0) for d in missing_dates) / (total_stocks * len(missing_dates))
        
        report = DataIntegrityReport(
            total_stocks=total_stocks,
            latest_date=str(latest_date),
            missing_type=missing_type,
            missing_dates=missing_dates,
            missing_stocks_by_date=missing_stocks_by_date,
            coverage_rate=coverage_rate,
            needs_complement=len(missing_dates) > 0
        )
        
        # 打印报告
        self._print_report(report)
        
        return report

    def _print_report(self, report: DataIntegrityReport):
        """打印完整性报告"""
        print("\n" + "=" * 60)
        print("📊 数据完整性报告")
        print("=" * 60)
        print(f"股票总数:     {report.total_stocks}")
        print(f"最新数据日期: {report.latest_date}")
        print(f"缺失类型:     {report.missing_type.value}")
        print(f"覆盖率:       {report.coverage_rate * 100:.2f}%")
        print(f"需要补全:     {'是' if report.needs_complement else '否'}")
        
        if report.missing_dates:
            print(f"\n缺失日期: {len(report.missing_dates)} 个")
            for date in report.missing_dates[:5]:  # 只显示前5个
                count = len(report.missing_stocks_by_date.get(date, []))
                print(f"  - {date}: {count} 只股票缺失")
            if len(report.missing_dates) > 5:
                print(f"  ... 还有 {len(report.missing_dates) - 5} 个日期")
        
        print("=" * 60 + "\n")

    def complement_by_missing_type(self, report: DataIntegrityReport) -> Dict:
        """根据缺失类型调用不同的补全方法
        
        Args:
            report: 完整性报告
            
        Returns:
            补全结果统计
        """
        if not report.needs_complement:
            logger.info("✅ 数据已完整，无需补全")
            return {"status": "no_complement_needed"}
        
        logger.info(f"📦 开始补全数据，缺失类型: {report.missing_type.value}")
        
        # 根据缺失类型选择补全策略
        if report.missing_type == MissingType.LATEST_ONLY:
            # 仅最新日期缺失：快速增量补全
            return self._complement_latest_only(report)
        
        elif report.missing_type == MissingType.PARTIAL_DATES:
            # 部分日期缺失：批量补全
            return self._complement_partial_dates(report)
        
        elif report.missing_type == MissingType.PARTIAL_STOCKS:
            # 部分股票缺失：针对缺失股票补全
            return self._complement_partial_stocks(report)
        
        elif report.missing_type == MissingType.MASSIVE:
            # 大量数据缺失：全量补全
            return self._complement_massive(report)
        
        else:
            return {"status": "unknown_missing_type"}

    def _complement_latest_only(self, report: DataIntegrityReport) -> Dict:
        """补全仅最新日期缺失的数据"""
        logger.info("🚀 使用快速增量补全策略...")
        
        target_date = report.latest_date
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 使用增量导入逻辑
        return self.incremental_import(start_date=target_date, end_date=today)

    def _complement_partial_dates(self, report: DataIntegrityReport) -> Dict:
        """补全部分日期缺失的数据"""
        logger.info("📅 使用批量补全策略...")
        
        results = {
            "dates_completed": 0,
            "stocks_completed": 0,
            "failed": 0,
            "errors": []
        }
        
        for date in report.missing_dates:
            logger.info(f"📦 补全 {date} 的数据...")
            
            missing_stocks = report.missing_stocks_by_date.get(date, [])
            success_count, fail_count, errors = self._complement_stocks_batch(
                missing_stocks, date, date
            )
            
            results["dates_completed"] += 1
            results["stocks_completed"] += success_count
            results["failed"] += fail_count
            results["errors"].extend(errors)
        
        return results

    def _complement_partial_stocks(self, report: DataIntegrityReport) -> Dict:
        """补全部分股票缺失的数据"""
        logger.info("👥 使用股票针对性补全策略...")
        
        # 收集所有缺失的股票
        all_missing_stocks = set()
        for stocks in report.missing_stocks_by_date.values():
            all_missing_stocks.update(stocks)
        
        # 找出最早缺失日期和最晚日期
        all_missing_dates = report.missing_dates
        
        return self._complement_stocks_batch(
            list(all_missing_stocks),
            min(all_missing_dates),
            max(all_missing_dates)
        )

    def _complement_massive(self, report: DataIntegrityReport) -> Dict:
        """补全大量数据缺失"""
        logger.info("🔄 使用全量补全策略...")
        
        # 获取所有缺失的股票和日期范围
        all_missing_stocks = set()
        for stocks in report.missing_stocks_by_date.values():
            all_missing_stocks.update(stocks)
        
        all_missing_dates = report.missing_dates
        
        if not all_missing_stocks or not all_missing_dates:
            logger.info("✅ 没有需要补全的数据")
            return {"status": "no_data_to_complement"}
        
        # 确定日期范围（从最早缺失日期到今天）
        start_date = min(all_missing_dates)
        end_date = max(all_missing_dates)
        
        logger.info(f"📦 补全 {len(all_missing_stocks)} 只股票的数据 ({start_date} ~ {end_date})")
        
        # 批量补全
        success_count, fail_count, errors = self._complement_stocks_batch(
            list(all_missing_stocks),
            start_date,
            end_date
        )
        
        return {
            "status": "completed",
            "missing_dates_count": len(all_missing_dates),
            "stocks_completed": success_count,
            "failed": fail_count,
            "errors": errors
        }

    def _complement_stocks_batch(
        self, 
        stocks: List[str], 
        start_date: str, 
        end_date: str
    ) -> Tuple[int, int, List[Dict]]:
        """批量补全股票数据
        
        Returns:
            (成功数, 失败数, 错误列表)
        """
        success_count = 0
        fail_count = 0
        errors = []
        
        total = len(stocks)
        logger.info(f"📦 补全 {total} 只股票的数据 ({start_date} ~ {end_date})...")
        
        for i, code in enumerate(stocks, 1):
            if self._interrupted:
                logger.info("检测到中断信号，停止补全")
                break
            
            try:
                # 格式化股票代码
                formatted_code = self._format_code(code)
                if not formatted_code:
                    continue
                
                # 构建 Baostock 格式的代码
                bs_code = f"sz.{formatted_code}" if formatted_code.startswith('0') else f"sh.{formatted_code}"
                
                # 获取数据
                df = self.datasource.get_kline(
                    bs_code, 
                    cycle='daily',
                    start_date=start_date,
                    end_date=end_date
                )
                
                if df is not None and not df.empty:
                    df = self._process_kline_data(df)
                    if df is not None and not df.empty:
                        df['code'] = formatted_code
                        df['cycle'] = '1d'
                        df['adjust_type'] = 'qfq'
                        
                        # 添加 trade_datetime
                        if 'trade_datetime' not in df.columns:
                            df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta('15:00:00')
                        
                        # 确保列顺序与 save_quotes 期望一致
                        required_columns = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 
                                          'close', 'pre_close', 'volume', 'amount', 'adjust_type', 
                                          'trade_datetime']
                        
                        # 只保留需要的列，并填充缺失的列
                        for col in required_columns:
                            if col not in df.columns:
                                if col == 'pre_close':
                                    df[col] = df['close'].shift(1)
                                elif col == 'trade_datetime':
                                    df[col] = pd.to_datetime(df['trade_date']) + pd.Timedelta('15:00:00')
                                else:
                                    df[col] = None
                        
                        df_save = df[required_columns].copy()
                        count = self.storage.save_quotes(df_save)
                        success_count += 1
                        
                        if i % 100 == 0:
                            logger.info(f"进度: {i}/{total}, 成功: {success_count}, 失败: {fail_count}")
                else:
                    fail_count += 1
                    
            except Exception as e:
                fail_count += 1
                errors.append({"code": code, "error": str(e)})
                logger.debug(f"补全 {code} 失败: {e}")
            
            time.sleep(0.1)  # 避免请求过快
        
        logger.info(f"✅ 补全完成: 成功 {success_count}, 失败 {fail_count}")
        
        return success_count, fail_count, errors

    def _process_kline_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理K线数据"""
        if df.empty:
            return df
        
        df = df.copy()
        
        # 转换数据类型
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pre_close']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 过滤无效数据
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if col in df.columns:
                df = df[df[col] > 0]
        
        df = df[df['volume'].notna() & (df['volume'] > 0)]
        
        # 确保 trade_date 列存在
        if 'trade_date' not in df.columns and 'date' in df.columns:
            df['trade_date'] = df['date']
        
        return df

    def incremental_import(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict:
        """增量导入（支持指定日期范围）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            导入结果统计
        """
        if not start_date:
            start_date = self._get_last_trade_date()
            if start_date:
                start_date = (datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                start_date = '2000-01-01'
        
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"📦 增量导入: {start_date} ~ {end_date}")
        
        codes = self.get_stock_list()
        total = len(codes)
        
        results = {
            "total": total,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "start_date": start_date,
            "end_date": end_date
        }
        
        for i, code in enumerate(codes, 1):
            if self._interrupted:
                break
            
            try:
                formatted_code = self._format_code(code)
                if not formatted_code:
                    results["skipped"] += 1
                    continue
                
                # 检查是否已有该日期范围的数据
                cursor = self.storage.conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM stock_quotes 
                    WHERE code = %s AND cycle = '1d' 
                    AND trade_date >= %s AND trade_date <= %s
                ''', (formatted_code, start_date, end_date))
                
                count = cursor.fetchone()[0]
                if count > 0:
                    results["skipped"] += 1
                    continue
                
                # 获取数据
                bs_code = f"sz.{formatted_code}" if formatted_code.startswith('0') else f"sh.{formatted_code}"
                df = self.datasource.get_kline(
                    bs_code,
                    cycle='daily',
                    start_date=start_date,
                    end_date=end_date
                )
                
                if df is not None and not df.empty:
                    df = self._process_kline_data(df)
                    if df is not None and not df.empty:
                        df['code'] = formatted_code
                        df['cycle'] = '1d'
                        df['adjust_type'] = 'qfq'
                        
                        if 'trade_datetime' not in df.columns:
                            df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta('15:00:00')
                        
                        saved_count = self.storage.save_quotes(df)
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                else:
                    results["failed"] += 1
                    
            except Exception as e:
                results["failed"] += 1
                logger.debug(f"导入 {code} 失败: {e}")
            
            if i % 500 == 0:
                logger.info(f"进度: {i}/{total}")
            
            time.sleep(0.1)
        
        logger.info(f"✅ 增量导入完成: 成功 {results['success']}, 失败 {results['failed']}, 跳过 {results['skipped']}")
        
        return results

    def _get_last_trade_date(self) -> Optional[str]:
        """获取最后交易日期"""
        cursor = self.storage.conn.cursor()
        cursor.execute("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'")
        result = cursor.fetchone()
        return result[0] if result else None

    def interrupt(self):
        """中断补全任务"""
        self._interrupted = True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='数据补全工具')
    parser.add_argument('--check-only', action='store_true', help='仅检测不补全')
    parser.add_argument('--date', type=str, help='指定补全日期 (YYYY-MM-DD)')
    parser.add_argument('--full', action='store_true', help='全量补全')
    
    args = parser.parse_args()
    
    complementer = DataComplementer()
    
    try:
        if args.check_only:
            # 仅检测
            report = complementer.check_data_integrity(args.date)
            if not report.needs_complement:
                print("✅ 数据已完整，无需补全")
            else:
                print(f"❌ 数据不完整，缺失类型: {report.missing_type.value}")
                print("请运行不带 --check-only 参数的命令进行补全")
        
        elif args.full:
            # 全量补全
            report = complementer.check_data_integrity()
            if report.needs_complement:
                complementer.complement_by_missing_type(report)
            else:
                print("✅ 数据已完整，无需补全")
        
        else:
            # 智能检测并补全
            report = complementer.check_data_integrity(args.date)
            if report.needs_complement:
                result = complementer.complement_by_missing_type(report)
                
                # 验证补全结果
                print("\n📊 补全后验证:")
                new_report = complementer.check_data_integrity(args.date)
                
                if new_report.coverage_rate > report.coverage_rate:
                    print(f"✅ 覆盖率提升: {report.coverage_rate*100:.2f}% → {new_report.coverage_rate*100:.2f}%")
                else:
                    print(f"⚠️ 覆盖率未提升，当前: {new_report.coverage_rate*100:.2f}%")
            else:
                print("✅ 数据已完整，无需补全")
    
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断补全任务")
        complementer.interrupt()
    finally:
        complementer.close()


if __name__ == '__main__':
    main()

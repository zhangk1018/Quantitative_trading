#!/usr/bin/env python3
"""数据质量校验模块 - 实现行业标准的数据质量校验规则"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from utils.logger import setup_logger

logger = setup_logger('data_quality_checker')


class DataQualityChecker:
    """数据质量校验器 - 实现行业标准的三重校验规则"""
    
    # 校验结果状态
    STATUS_PASS = 'pass'
    STATUS_WARNING = 'warning'
    STATUS_ERROR = 'error'
    
    def __init__(self):
        self.check_results = []
    
    def reset(self):
        """重置校验结果"""
        self.check_results = []
    
    def _add_result(self, check_name: str, status: str, message: str, details: Optional[Dict] = None):
        """添加校验结果"""
        self.check_results.append({
            'check_name': check_name,
            'status': status,
            'message': message,
            'details': details or {},
            'timestamp': datetime.now().isoformat()
        })
    
    def _check_required_columns(self, df: pd.DataFrame, required_cols: List[str]) -> Tuple[bool, List[str]]:
        """检查必要列是否存在"""
        missing_cols = [col for col in required_cols if col not in df.columns]
        return len(missing_cols) == 0, missing_cols
    
    # ==================== 采集后校验（第一重校验）====================
    
    def check_data_source_connectivity(self, df: pd.DataFrame, source_name: str = 'unknown') -> dict:
        """
        数据源连通性校验 - 采集后立即执行
        
        检查：
        1. 返回的数据是否为空
        2. 必要字段是否存在
        """
        check_name = 'data_source_connectivity'
        
        if df is None:
            self._add_result(check_name, self.STATUS_ERROR, f"数据源 {source_name} 返回None", {'source': source_name})
            return self._get_last_result()
        
        if df.empty:
            self._add_result(check_name, self.STATUS_WARNING, f"数据源 {source_name} 返回空数据", {'source': source_name})
            return self._get_last_result()
        
        self._add_result(check_name, self.STATUS_PASS, f"数据源 {source_name} 连通性正常", {
            'source': source_name,
            'row_count': len(df),
            'columns': list(df.columns)
        })
        return self._get_last_result()
    
    def check_basic_structure(self, df: pd.DataFrame, expected_cols: List[str]) -> dict:
        """
        基础结构校验 - 检查数据基本结构
        
        Args:
            df: 待校验数据
            expected_cols: 期望的列名列表
        
        Returns:
            校验结果
        """
        check_name = 'basic_structure'
        
        if df is None or df.empty:
            self._add_result(check_name, self.STATUS_ERROR, "数据为空", {})
            return self._get_last_result()
        
        has_required, missing_cols = self._check_required_columns(df, expected_cols)
        
        if not has_required:
            self._add_result(check_name, self.STATUS_ERROR, f"缺少必要列", {
                'expected_cols': expected_cols,
                'missing_cols': missing_cols,
                'actual_cols': list(df.columns)
            })
            return self._get_last_result()
        
        self._add_result(check_name, self.STATUS_PASS, "数据结构校验通过", {
            'row_count': len(df),
            'column_count': len(df.columns),
            'columns': list(df.columns)
        })
        return self._get_last_result()
    
    # ==================== 清洗后校验（第二重校验）====================
    
    def check_format_validity(self, df: pd.DataFrame) -> dict:
        """
        格式逻辑校验 - 清洗后执行
        
        检查：
        1. 数值列是否包含非数值
        2. 日期格式是否正确
        3. 价格是否合理（非负）
        """
        check_name = 'format_validity'
        
        if df is None or df.empty:
            self._add_result(check_name, self.STATUS_ERROR, "数据为空", {})
            return self._get_last_result()
        
        issues = []
        
        # 检查数值列
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        for col in numeric_cols:
            if col in df.columns:
                # 检查是否有非数值（NaN不算）
                non_numeric = df[col].apply(lambda x: pd.notna(x) and not isinstance(x, (int, float, np.number)))
                if non_numeric.any():
                    count = non_numeric.sum()
                    issues.append(f"列 {col} 存在 {count} 个非数值")
        
        # 检查日期格式
        if 'trade_date' in df.columns:
            try:
                pd.to_datetime(df['trade_date'])
            except Exception as e:
                issues.append(f"日期格式错误: {str(e)}")
        
        # 检查价格合理性（非负）
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if col in df.columns:
                negative_count = (df[col] < 0).sum()
                if negative_count > 0:
                    issues.append(f"列 {col} 存在 {negative_count} 个负数")
        
        # 检查成交量合理性
        if 'volume' in df.columns:
            negative_volume = (df['volume'] < 0).sum()
            if negative_volume > 0:
                issues.append(f"成交量存在 {negative_volume} 个负数")
        
        if issues:
            self._add_result(check_name, self.STATUS_WARNING, "格式校验发现问题", {
                'issues': issues,
                'row_count': len(df)
            })
        else:
            self._add_result(check_name, self.STATUS_PASS, "格式校验通过", {
                'row_count': len(df)
            })
        
        return self._get_last_result()
    
    def check_duplicates(self, df: pd.DataFrame, unique_cols: List[str] = None) -> dict:
        """
        重复记录校验
        
        Args:
            df: 待校验数据
            unique_cols: 唯一性约束列，默认 ['code', 'trade_date', 'cycle']
        
        Returns:
            校验结果
        """
        check_name = 'duplicate_check'
        
        if df is None or df.empty:
            self._add_result(check_name, self.STATUS_ERROR, "数据为空", {})
            return self._get_last_result()
        
        if unique_cols is None:
            unique_cols = ['code', 'trade_date', 'cycle']
        
        # 检查唯一键列是否存在
        missing_cols = [col for col in unique_cols if col not in df.columns]
        if missing_cols:
            self._add_result(check_name, self.STATUS_WARNING, f"缺少唯一性约束列", {
                'missing_cols': missing_cols
            })
            return self._get_last_result()
        
        # 检查重复
        duplicates = df.duplicated(subset=unique_cols, keep=False)
        duplicate_count = duplicates.sum()
        
        if duplicate_count > 0:
            duplicate_rows = df[duplicates].head(5).to_dict('records')
            self._add_result(check_name, self.STATUS_WARNING, f"发现 {duplicate_count} 条重复记录", {
                'duplicate_count': duplicate_count,
                'sample_duplicates': duplicate_rows
            })
        else:
            self._add_result(check_name, self.STATUS_PASS, "无重复记录", {
                'row_count': len(df)
            })
        
        return self._get_last_result()
    
    def check_missing_values(self, df: pd.DataFrame, max_missing_ratio: float = 0.05) -> dict:
        """
        缺失值校验
        
        Args:
            df: 待校验数据
            max_missing_ratio: 最大允许缺失比例，默认5%
        
        Returns:
            校验结果
        """
        check_name = 'missing_values'
        
        if df is None or df.empty:
            self._add_result(check_name, self.STATUS_ERROR, "数据为空", {})
            return self._get_last_result()
        
        missing_info = {}
        total_rows = len(df)
        has_excessive_missing = False
        
        for col in df.columns:
            missing_count = df[col].isna().sum()
            if missing_count > 0:
                ratio = missing_count / total_rows
                missing_info[col] = {
                    'count': missing_count,
                    'ratio': f"{ratio * 100:.2f}%"
                }
                if ratio > max_missing_ratio:
                    has_excessive_missing = True
        
        if has_excessive_missing:
            self._add_result(check_name, self.STATUS_ERROR, "存在过多缺失值", {
                'missing_info': missing_info,
                'max_allowed_ratio': f"{max_missing_ratio * 100:.2f}%"
            })
        elif missing_info:
            self._add_result(check_name, self.STATUS_WARNING, "存在少量缺失值", {
                'missing_info': missing_info
            })
        else:
            self._add_result(check_name, self.STATUS_PASS, "无缺失值", {})
        
        return self._get_last_result()
    
    # ==================== 特征工程后校验（第三重校验）====================
    
    def check_price_logic(self, df: pd.DataFrame) -> dict:
        """
        价格逻辑校验 - 检查价格之间的逻辑关系
        
        检查：
        1. high >= close >= low
        2. high >= open >= low
        """
        check_name = 'price_logic'
        
        if df is None or df.empty:
            self._add_result(check_name, self.STATUS_ERROR, "数据为空", {})
            return self._get_last_result()
        
        issues = []
        total_rows = len(df)
        
        # 检查 high >= close >= low
        if all(col in df.columns for col in ['high', 'low', 'close']):
            invalid_high_low = ((df['high'] < df['low']) | (df['high'] < df['close']) | (df['close'] < df['low'])).sum()
            if invalid_high_low > 0:
                issues.append(f"价格逻辑错误: {invalid_high_low} 条记录 (high < low 或 high < close 或 close < low)")
        
        # 检查 high >= open >= low
        if all(col in df.columns for col in ['high', 'low', 'open']):
            invalid_open = ((df['open'] < df['low']) | (df['open'] > df['high'])).sum()
            if invalid_open > 0:
                issues.append(f"开盘价超出范围: {invalid_open} 条记录")
        
        if issues:
            self._add_result(check_name, self.STATUS_ERROR, "价格逻辑校验失败", {
                'issues': issues,
                'total_rows': total_rows
            })
        else:
            self._add_result(check_name, self.STATUS_PASS, "价格逻辑校验通过", {
                'total_rows': total_rows
            })
        
        return self._get_last_result()
    
    def check_extreme_values(self, df: pd.DataFrame, threshold: float = 0.3) -> dict:
        """
        极端值校验 - 检查是否存在异常波动
        
        Args:
            df: 待校验数据
            threshold: 涨跌幅度阈值，默认30%
        
        Returns:
            校验结果
        """
        check_name = 'extreme_values'
        
        if df is None or df.empty:
            self._add_result(check_name, self.STATUS_ERROR, "数据为空", {})
            return self._get_last_result()
        
        issues = []
        
        # 检查涨跌幅
        if 'pct_chg' in df.columns:
            extreme_count = ((df['pct_chg'].abs() > threshold * 100)).sum()
            if extreme_count > 0:
                issues.append(f"极端涨跌幅: {extreme_count} 条记录超过 {threshold * 100}%")
        
        # 检查价格跳变（使用前复权数据）
        if 'close' in df.columns:
            df_sorted = df.sort_values('trade_date')
            price_change = df_sorted['close'].pct_change().abs()
            extreme_jump = (price_change > threshold).sum()
            if extreme_jump > 0:
                issues.append(f"价格跳变: {extreme_jump} 条记录价格变化超过 {threshold * 100}%")
        
        if issues:
            self._add_result(check_name, self.STATUS_WARNING, "发现极端值", {
                'issues': issues,
                'row_count': len(df)
            })
        else:
            self._add_result(check_name, self.STATUS_PASS, "无极端值", {
                'row_count': len(df)
            })
        
        return self._get_last_result()
    
    def check_time_sequence(self, df: pd.DataFrame) -> dict:
        """
        时间序列校验 - 检查时间连续性和顺序
        
        Returns:
            校验结果
        """
        check_name = 'time_sequence'
        
        if df is None or df.empty:
            self._add_result(check_name, self.STATUS_ERROR, "数据为空", {})
            return self._get_last_result()
        
        issues = []
        
        if 'trade_date' in df.columns:
            # 检查日期排序
            df_sorted = df.sort_values('trade_date')
            if not df_sorted['trade_date'].is_monotonic_increasing:
                issues.append("日期序列不单调递增")
            
            # 检查日期唯一性
            duplicate_dates = df['trade_date'].duplicated().sum()
            if duplicate_dates > 0:
                issues.append(f"存在 {duplicate_dates} 个重复日期")
        
        if issues:
            self._add_result(check_name, self.STATUS_WARNING, "时间序列校验发现问题", {
                'issues': issues
            })
        else:
            self._add_result(check_name, self.STATUS_PASS, "时间序列校验通过", {
                'row_count': len(df),
                'date_range': f"{df['trade_date'].min()} ~ {df['trade_date'].max()}" if not df.empty else 'N/A'
            })
        
        return self._get_last_result()
    
    # ==================== 多源交叉验证 ====================
    
    def cross_validate_data(self, primary_df: pd.DataFrame, secondary_df: pd.DataFrame, 
                           key_cols: List[str] = None, compare_cols: List[str] = None) -> dict:
        """
        多源交叉验证 - 将核心数据与权威数据源进行比对
        
        Args:
            primary_df: 主数据源数据
            secondary_df: 备用数据源数据
            key_cols: 用于匹配的键列，默认 ['code', 'trade_date']
            compare_cols: 需要比对的列，默认 ['open', 'high', 'low', 'close', 'volume']
        
        Returns:
            校验结果
        """
        check_name = 'cross_validation'
        
        if primary_df is None or primary_df.empty:
            self._add_result(check_name, self.STATUS_ERROR, "主数据源数据为空", {})
            return self._get_last_result()
        
        if secondary_df is None or secondary_df.empty:
            self._add_result(check_name, self.STATUS_WARNING, "备用数据源数据为空", {})
            return self._get_last_result()
        
        if key_cols is None:
            key_cols = ['code', 'trade_date']
        
        if compare_cols is None:
            compare_cols = ['open', 'high', 'low', 'close', 'volume']
        
        # 检查键列是否存在
        for df, name in [(primary_df, 'primary'), (secondary_df, 'secondary')]:
            missing_cols = [col for col in key_cols if col not in df.columns]
            if missing_cols:
                self._add_result(check_name, self.STATUS_ERROR, f"{name}数据源缺少键列", {
                    'missing_cols': missing_cols
                })
                return self._get_last_result()
        
        # 合并数据进行比对
        merged = primary_df.merge(secondary_df, on=key_cols, suffixes=('_primary', '_secondary'), how='inner')
        
        if merged.empty:
            self._add_result(check_name, self.STATUS_WARNING, "无匹配数据可比对", {
                'primary_rows': len(primary_df),
                'secondary_rows': len(secondary_df)
            })
            return self._get_last_result()
        
        # 比对数值列
        discrepancies = {}
        for col in compare_cols:
            primary_col = f"{col}_primary"
            secondary_col = f"{col}_secondary"
            
            if primary_col in merged.columns and secondary_col in merged.columns:
                # 计算绝对差异
                diff = abs(merged[primary_col] - merged[secondary_col])
                
                # 计算相对差异（避免除以0）
                mask = merged[secondary_col] != 0
                rel_diff = np.where(mask, diff[mask] / abs(merged[secondary_col][mask]), diff)
                
                # 找出差异超过阈值的记录（1%）
                threshold = 0.01
                significant_diff = (rel_diff > threshold).sum()
                
                if significant_diff > 0:
                    discrepancies[col] = {
                        'discrepant_count': int(significant_diff),
                        'total_compared': len(merged),
                        'max_diff': float(diff.max()),
                        'avg_diff': float(diff.mean())
                    }
        
        if discrepancies:
            self._add_result(check_name, self.STATUS_WARNING, "多源比对发现差异", {
                'discrepancies': discrepancies,
                'matched_rows': len(merged)
            })
        else:
            self._add_result(check_name, self.STATUS_PASS, "多源比对一致", {
                'matched_rows': len(merged)
            })
        
        return self._get_last_result()
    
    # ==================== 综合校验 ====================
    
    def run_full_checks(self, df: pd.DataFrame, check_type: str = 'full') -> dict:
        """
        运行完整校验
        
        Args:
            df: 待校验数据
            check_type: 校验类型
                - 'acquisition': 采集后校验
                - 'cleaning': 清洗后校验
                - 'feature': 特征工程后校验
                - 'full': 全部校验
        
        Returns:
            完整校验报告
        """
        self.reset()
        
        if check_type in ['acquisition', 'full']:
            self.check_basic_structure(df, ['code', 'trade_date', 'open', 'high', 'low', 'close', 'volume'])
        
        if check_type in ['cleaning', 'full']:
            self.check_format_validity(df)
            self.check_duplicates(df)
            self.check_missing_values(df)
        
        if check_type in ['feature', 'full']:
            self.check_price_logic(df)
            self.check_extreme_values(df)
            self.check_time_sequence(df)
        
        return self.get_report()
    
    def get_report(self) -> dict:
        """获取完整校验报告"""
        summary = self._calculate_summary()
        
        return {
            'summary': summary,
            'details': self.check_results,
            'generated_at': datetime.now().isoformat()
        }
    
    def _calculate_summary(self) -> dict:
        """计算校验摘要"""
        pass_count = sum(1 for r in self.check_results if r['status'] == self.STATUS_PASS)
        warning_count = sum(1 for r in self.check_results if r['status'] == self.STATUS_WARNING)
        error_count = sum(1 for r in self.check_results if r['status'] == self.STATUS_ERROR)
        
        overall_status = self.STATUS_PASS
        if error_count > 0:
            overall_status = self.STATUS_ERROR
        elif warning_count > 0:
            overall_status = self.STATUS_WARNING
        
        return {
            'overall_status': overall_status,
            'total_checks': len(self.check_results),
            'pass_count': pass_count,
            'warning_count': warning_count,
            'error_count': error_count
        }
    
    def _get_last_result(self) -> dict:
        """获取最后一条校验结果"""
        return self.check_results[-1] if self.check_results else None
    
    def print_report(self):
        """打印校验报告"""
        report = self.get_report()
        
        print("=" * 60)
        print("数据质量校验报告")
        print("=" * 60)
        print(f"生成时间: {report['generated_at']}")
        print(f"总体状态: {report['summary']['overall_status'].upper()}")
        print(f"校验总数: {report['summary']['total_checks']}")
        print(f"通过: {report['summary']['pass_count']}")
        print(f"警告: {report['summary']['warning_count']}")
        print(f"错误: {report['summary']['error_count']}")
        print()
        
        for result in report['details']:
            status_icon = "✅" if result['status'] == self.STATUS_PASS else \
                         "⚠️" if result['status'] == self.STATUS_WARNING else "❌"
            print(f"{status_icon} {result['check_name']}: {result['message']}")
            if result['details']:
                for k, v in result['details'].items():
                    print(f"      {k}: {v}")
        
        print("=" * 60)


# 测试代码
if __name__ == '__main__':
    # 创建测试数据
    test_data = pd.DataFrame({
        'code': ['sh.600000'] * 10,
        'trade_date': pd.date_range('2024-01-01', periods=10),
        'open': [10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9],
        'high': [10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 11.0, 11.1],
        'low': [9.8, 9.9, 10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7],
        'close': [10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 11.0],
        'volume': [1000, 1200, 1100, 1300, 1250, 1400, 1350, 1500, 1450, 1600],
        'amount': [10100, 12240, 11330, 13520, 13125, 14840, 14445, 16200, 15805, 17600]
    })
    
    # 创建校验器
    checker = DataQualityChecker()
    
    # 运行完整校验
    report = checker.run_full_checks(test_data, check_type='full')
    
    # 打印报告
    checker.print_report()
    
    # 测试交叉验证
    print("\n\n测试多源交叉验证:")
    # 创建略有差异的第二数据源
    test_data2 = test_data.copy()
    test_data2['close'] = test_data2['close'] * 1.001  # 模拟微小差异
    
    result = checker.cross_validate_data(test_data, test_data2)
    print(f"交叉验证结果: {result['status']} - {result['message']}")

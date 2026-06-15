"""
数据校验模块 - 数据质量检查和告警
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)

class DataValidator:
    def __init__(self):
        # 校验规则配置
        self.rules = {
            'min_rows': 10,           # 最小数据行数
            'max_missing_rate': 0.1,  # 最大缺失率
            'price_min': 0.01,        # 最小价格
            'price_max': 10000,       # 最大价格
            'max_pct_change': 50,     # 最大单日涨跌幅(%)
        }
    
    def validate(self, df: pd.DataFrame, stock_code: str) -> dict:
        """
        执行数据校验
        
        Args:
            df: 待校验的DataFrame
            stock_code: 股票代码
            
        Returns:
            校验结果字典，包含status和errors列表
        """
        errors = []
        warnings = []
        status = 'success'
        
        if df is None or df.empty:
            errors.append('数据为空')
            status = 'critical'
            return {'status': status, 'errors': errors, 'warnings': warnings}
        
        # 1. 检查数据行数
        if len(df) < self.rules['min_rows']:
            warnings.append(f'数据量较少: {len(df)} 行')
            logger.warning(f'{stock_code} 数据量较少: {len(df)} 行')
        
        # 2. 检查缺失值
        missing_rate = df.isnull().sum().sum() / (df.shape[0] * df.shape[1])
        if missing_rate > self.rules['max_missing_rate']:
            errors.append(f'缺失率过高: {missing_rate:.2%}')
            logger.error(f'{stock_code} 缺失率过高: {missing_rate:.2%}')
        
        # 3. 检查价格异常
        if 'close' in df.columns:
            invalid_prices = df[(df['close'] < self.rules['price_min']) | 
                               (df['close'] > self.rules['price_max'])]
            if not invalid_prices.empty:
                errors.append(f'发现 {len(invalid_prices)} 条价格异常记录')
                logger.error(f'{stock_code} 发现 {len(invalid_prices)} 条价格异常记录')
                # 修复异常价格
                df = self._fix_invalid_prices(df)
        
        # 4. 检查涨跌幅异常
        if 'pct_chg' in df.columns:
            abnormal_chg = df[df['pct_chg'].abs() > self.rules['max_pct_change']]
            if not abnormal_chg.empty:
                warnings.append(f'发现 {len(abnormal_chg)} 条涨跌幅异常记录')
                logger.warning(f'{stock_code} 发现 {len(abnormal_chg)} 条涨跌幅异常记录')
        
        # 5. 检查日期连续性
        date_gaps = self._check_date_continuity(df)
        if date_gaps:
            warnings.append(f'发现 {len(date_gaps)} 个日期缺口')
            logger.warning(f'{stock_code} 发现 {len(date_gaps)} 个日期缺口')
        
        # 6. 检查必要列是否存在
        required_cols = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            errors.append(f'缺少必要列: {", ".join(missing_cols)}')
            logger.error(f'{stock_code} 缺少必要列: {", ".join(missing_cols)}')
        
        # 确定最终状态
        if errors:
            status = 'critical' if len(errors) > 1 else 'warning'
        elif warnings:
            status = 'warning'
        
        # 输出校验摘要
        if status == 'success':
            logger.info(f'{stock_code} 数据校验通过 ✅')
        else:
            logger.warning(f'{stock_code} 数据校验完成，状态: {status}')
            if warnings:
                logger.warning(f'警告: {"; ".join(warnings)}')
            if errors:
                logger.error(f'错误: {"; ".join(errors)}')
        
        return {
            'status': status,
            'errors': errors,
            'warnings': warnings,
            'data': df  # 返回修复后的数据
        }
    
    def _fix_invalid_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """修复无效价格"""
        df = df.copy()
        valid_mask = (df['close'] >= self.rules['price_min']) & (df['close'] <= self.rules['price_max'])
        
        # 使用前后数据插值修复
        df.loc[~valid_mask, 'close'] = df['close'].interpolate()
        df.loc[~valid_mask, 'open'] = df['open'].interpolate()
        df.loc[~valid_mask, 'high'] = df['high'].interpolate()
        df.loc[~valid_mask, 'low'] = df['low'].interpolate()
        
        logger.debug('无效价格已修复')
        return df
    
    def _check_date_continuity(self, df: pd.DataFrame) -> list:
        """检查日期连续性"""
        if 'trade_date' not in df.columns:
            return []
        
        df = df.sort_values('trade_date')
        date_diff = df['trade_date'].diff().dt.days
        gaps = date_diff[date_diff > 1]
        
        return gaps.tolist()

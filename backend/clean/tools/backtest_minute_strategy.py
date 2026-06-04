#!/usr/bin/env python3
"""
分钟线策略回测框架

功能：
- 从 stock_quotes_minute 读取分钟线数据
- 计算技术指标（MA、MACD、RSI、布林带等）
- 定义交易策略和信号生成规则
- 执行回测并生成绩效报告

用法：
    python scripts/backtest_minute_strategy.py --code 000001 --strategy macd_crossover
    python scripts/backtest_minute_strategy.py --code 000001 --strategy rsi_overbought
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Callable

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('backtest')

class MinuteBacktester:
    def __init__(self):
        self.storage = self._init_storage()
    
    def _init_storage(self) -> PostgreSQLStorage:
        storage_config = config.storage.get('postgresql', {})
        storage = PostgreSQLStorage(storage_config)
        storage.connect()
        return storage
    
    def fetch_minute_data(self, code: str, cycle: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取分钟线数据（使用显式字段提升性能）"""
        cursor = self.storage.conn.cursor()
        
        # 使用显式字段而非 SELECT *，减少I/O和内存
        if start_date and end_date:
            cursor.execute("""
                SELECT trade_time, trade_date, open, high, low, close, volume, amount, vwap
                FROM stock_quotes_minute
                WHERE code = %s AND cycle = %s
                  AND trade_date >= %s AND trade_date <= %s
                ORDER BY trade_time
            """, (code, cycle, start_date, end_date))
        else:
            cursor.execute("""
                SELECT trade_time, trade_date, open, high, low, close, volume, amount, vwap
                FROM stock_quotes_minute
                WHERE code = %s AND cycle = %s
                ORDER BY trade_time
            """, (code, cycle))
        
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows, columns=columns)
        df['trade_time'] = pd.to_datetime(df['trade_time'])
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # 将 Decimal 类型转换为 float
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'vwap']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        df.set_index('trade_time', inplace=True)
        
        return df
    
    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 移动平均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma60'] = df['close'].rolling(window=60).mean()
        
        # RSI（处理除零问题）
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        # 处理除零和inf值：loss=0时RSI=100，gain=0时RSI=0
        rs = rs.replace([np.inf, -np.inf], np.nan).fillna(100)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = df['ema12'] - df['ema26']
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['histogram'] = df['macd'] - df['signal']
        
        # 布林带（使用完整窗口避免早期虚假信号）
        df['bb_mid'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20, min_periods=20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
        df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
        
        # 成交量指标
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma5']
        
        return df
    
    @staticmethod
    def generate_signals_macd_crossover(df: pd.DataFrame) -> pd.DataFrame:
        """MACD 交叉策略信号
        
        信号含义：本K线收盘后可以确认的信号
        回测时通过 prev_buy_signal 延迟一根K线执行交易
        """
        df = df.copy()
        
        # 金叉：MACD 上穿信号线（基于本K线收盘后的数据）
        # 使用 shift(1) 确保不使用当前K线的指标值（避免未来函数）
        df['buy_signal'] = (df['macd'].shift(1) < df['signal'].shift(1)) & (df['macd'] > df['signal'])
        
        # 死叉：MACD 下穿信号线
        df['sell_signal'] = (df['macd'].shift(1) > df['signal'].shift(1)) & (df['macd'] < df['signal'])
        
        return df
    
    @staticmethod
    def generate_signals_rsi_overbought(df: pd.DataFrame, overbought=70, oversold=30) -> pd.DataFrame:
        """RSI 超买超卖策略信号"""
        df = df.copy()
        
        # RSI 低于超卖线买入（基于本K线的RSI值）
        df['buy_signal'] = df['rsi'] < oversold
        
        # RSI 高于超买线卖出
        df['sell_signal'] = df['rsi'] > overbought
        
        return df
    
    @staticmethod
    def generate_signals_ma_crossover(df: pd.DataFrame) -> pd.DataFrame:
        """均线交叉策略信号"""
        df = df.copy()
        
        # 金叉：短期均线上穿长期均线
        df['buy_signal'] = (df['ma5'].shift(1) < df['ma20'].shift(1)) & (df['ma5'] > df['ma20'])
        
        # 死叉：短期均线下穿长期均线
        df['sell_signal'] = (df['ma5'].shift(1) > df['ma20'].shift(1)) & (df['ma5'] < df['ma20'])
        
        return df
    
    @staticmethod
    def generate_signals_bollinger(df: pd.DataFrame) -> pd.DataFrame:
        """布林带策略信号"""
        df = df.copy()
        
        # 下轨附近买入
        df['buy_signal'] = df['close'] <= df['bb_lower']
        
        # 上轨附近卖出
        df['sell_signal'] = df['close'] >= df['bb_upper']
        
        return df
    
    def backtest(self, df: pd.DataFrame, strategy_func: Callable, 
                 initial_cash: float = 100000.0,
                 commission_rate: float = 0.0003,
                 slippage_rate: float = 0.001,
                 min_commission: float = 5.0) -> Dict:
        """执行回测
        
        Args:
            df: 分钟线数据
            strategy_func: 策略信号生成函数
            initial_cash: 初始资金
            commission_rate: 佣金费率（默认万分之三）
            slippage_rate: 滑点率（默认千分之一）
            min_commission: 最低佣金（默认5元）
        """
        df = df.copy()
        df = self.calculate_indicators(df)
        df = strategy_func(df)
        
        # 初始化回测状态
        position = 0  # 0: 空仓, 1: 持仓
        cash = initial_cash
        holdings = 0
        buy_price = 0.0  # 记录买入成本价
        buy_date = None  # 记录买入日期（用于T+1规则）
        trades = []
        equity_curve = []
        trade_pairs = []  # 配对的买卖交易，用于计算盈亏
        last_buy_trade = None  # 优化：缓存最后买入交易，O(1)访问
        
        # 延迟执行：使用上一根K线的信号来决定当前K线的交易
        prev_buy_signal = False
        prev_sell_signal = False
        
        # 优化：使用 itertuples 提升性能
        for row in df.itertuples(index=True, name=None):
            idx = row[0]
            open_price = row[df.columns.get_loc('open') + 1]
            close_price = row[df.columns.get_loc('close') + 1]
            
            # 当前日期
            current_date = idx.date()
            
            # 买入信号（延迟执行：用上一根K线的信号）
            if prev_buy_signal and position == 0:
                # 使用当前K线的开盘价 + 滑点买入
                price = open_price * (1 + slippage_rate)
                # A股最小交易单位100股
                shares = int(cash // price // 100) * 100
                if shares > 0:
                    buy_amount = shares * price
                    commission = max(buy_amount * commission_rate, min_commission)
                    cash -= buy_amount + commission
                    holdings += shares
                    position = 1
                    buy_price = price
                    buy_date = current_date
                    last_buy_trade = {
                        'time': idx,
                        'type': 'buy',
                        'price': price,
                        'shares': shares,
                        'cash': cash,
                        'holdings': holdings,
                        'commission': commission
                    }
                    trades.append(last_buy_trade)
            
            # 卖出信号（延迟执行：用上一根K线的信号）
            elif prev_sell_signal and position == 1:
                # A股T+1规则：买入当天不能卖出
                if buy_date is not None and current_date <= buy_date:
                    prev_sell_signal = False  # 跳过当天卖出信号
                else:
                    # 使用当前K线的开盘价 - 滑点卖出
                    price = open_price * (1 - slippage_rate)
                    sell_amount = holdings * price
                    commission = max(sell_amount * commission_rate, min_commission)
                    cash += sell_amount - commission
                    
                    # 计算盈亏（使用缓存的买入交易）
                    if last_buy_trade:
                        profit = (price - last_buy_trade['price']) * holdings - commission
                        trade_pairs.append({
                            'buy_time': last_buy_trade['time'],
                            'sell_time': idx,
                            'buy_price': last_buy_trade['price'],
                            'sell_price': price,
                            'shares': holdings,
                            'profit': profit,
                            'pct_return': profit / (last_buy_trade['price'] * holdings) if last_buy_trade['price'] > 0 else 0
                        })
                    
                    trades.append({
                        'time': idx,
                        'type': 'sell',
                        'price': price,
                        'shares': holdings,
                        'cash': cash,
                        'holdings': 0,
                        'commission': commission
                    })
                    holdings = 0
                    position = 0
                    buy_price = 0.0
                    buy_date = None
                    last_buy_trade = None
            
            # 更新prev信号为当前K线计算出的信号
            signal_col_idx = df.columns.get_loc('buy_signal') + 1
            prev_buy_signal = bool(row[signal_col_idx])
            signal_col_idx = df.columns.get_loc('sell_signal') + 1
            prev_sell_signal = bool(row[signal_col_idx])
            
            # 计算当前权益
            current_equity = cash + holdings * close_price
            equity_curve.append({
                'time': idx,
                'equity': current_equity,
                'position': position
            })
        
        # 收盘时仍有持仓，强制卖出
        if position == 1 and len(df) > 0:
            last_row = df.iloc[-1]
            price = last_row['close'] * (1 - slippage_rate)
            sell_amount = holdings * price
            commission = max(sell_amount * commission_rate, min_commission)
            cash += sell_amount - commission
            
            # 计算盈亏（使用缓存的买入交易）
            if last_buy_trade:
                profit = (price - last_buy_trade['price']) * holdings - commission
                trade_pairs.append({
                    'buy_time': last_buy_trade['time'],
                    'sell_time': df.index[-1],
                    'buy_price': last_buy_trade['price'],
                    'sell_price': price,
                    'shares': holdings,
                    'profit': profit,
                    'pct_return': profit / (last_buy_trade['price'] * holdings) if last_buy_trade['price'] > 0 else 0
                })
            
            trades.append({
                'time': df.index[-1],
                'type': 'sell',
                'price': price,
                'shares': holdings,
                'cash': cash,
                'holdings': 0,
                'commission': commission
            })
        
        # 计算绩效指标
        equity_df = pd.DataFrame(equity_curve).set_index('time')
        final_equity = cash
        
        # 收益率
        total_return = (final_equity - initial_cash) / initial_cash
        
        # 年化收益率（使用交易日数量计算，避免非交易时段干扰）
        annualized_return = 0
        annualized_warning = ""
        if len(equity_df) > 0:
            # 使用交易日数量而非自然日
            # 分钟线：统计不同日期的数量作为交易天数
            trading_days = len(set(equity_df.index.date))
            
            if trading_days >= 7:
                # 至少7个交易日才计算年化
                annualized_return = (1 + total_return) ** (240 / trading_days) - 1
            elif trading_days > 0:
                # 少于7个交易日，直接返回总收益
                annualized_return = total_return
                annualized_warning = "⚠️ 回测周期过短，年化收益率仅供参考"
            else:
                annualized_return = 0
        
        # 最大回撤
        equity_df['max_eq'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['max_eq']) / equity_df['max_eq']
        max_drawdown = equity_df['drawdown'].min()
        
        # 胜率（基于配对交易）
        if len(trade_pairs) > 0:
            win_trades = [t for t in trade_pairs if t['profit'] > 0]
            win_rate = len(win_trades) / len(trade_pairs)
        else:
            win_rate = 0
        
        # 交易次数
        trade_count = len(trade_pairs)
        
        # 平均盈亏比
        if trade_count > 0:
            avg_profit = np.mean([t['profit'] for t in trade_pairs])
            avg_pct_return = np.mean([t['pct_return'] for t in trade_pairs])
        else:
            avg_profit = 0
            avg_pct_return = 0
        
        return {
            'initial_equity': initial_cash,
            'final_equity': final_equity,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'annualized_warning': annualized_warning,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'trade_count': trade_count,
            'avg_profit': avg_profit,
            'avg_pct_return': avg_pct_return,
            'trades': trades,
            'trade_pairs': trade_pairs,
            'equity_curve': equity_curve
        }
    
    def generate_report(self, code: str, cycle: str, result: Dict) -> str:
        """生成回测报告"""
        report = ["\n" + "="*60]
        report.append("          分钟线策略回测报告")
        report.append("="*60)
        report.append(f"\n📊 基本信息")
        report.append(f"  股票代码: {code}")
        report.append(f"  周期: {cycle}")
        report.append(f"  初始资金: ¥{result['initial_equity']:,.2f}")
        report.append(f"  最终资金: ¥{result['final_equity']:,.2f}")
        
        report.append("\n📈 绩效指标")
        report.append(f"  总收益率: {result['total_return']*100:+.2f}%")
        report.append(f"  年化收益率: {result['annualized_return']*100:+.2f}%")
        if result.get('annualized_warning'):
            report.append(f"  {result['annualized_warning']}")
        report.append(f"  最大回撤: {result['max_drawdown']*100:.2f}%")
        report.append(f"  胜率: {result['win_rate']*100:.2f}%")
        report.append(f"  交易次数: {result['trade_count']}")
        report.append(f"  平均盈亏: ¥{result['avg_profit']:.2f}")
        report.append(f"  平均收益率: {result['avg_pct_return']*100:.4f}%")
        
        report.append("\n📋 盈亏明细")
        if result.get('trade_pairs'):
            for i, pair in enumerate(result['trade_pairs'][:10]):  # 只显示前10笔
                profit_icon = "✅" if pair['profit'] > 0 else "❌"
                report.append(f"  {profit_icon} {pair['buy_time'].strftime('%Y-%m-%d %H:%M')} -> {pair['sell_time'].strftime('%Y-%m-%d %H:%M')}")
                report.append(f"     买入: ¥{pair['buy_price']:.2f} | 卖出: ¥{pair['sell_price']:.2f}")
                report.append(f"     盈亏: ¥{pair['profit']:.2f} ({pair['pct_return']*100:.4f}%) | {pair['shares']}股")
            
            if len(result['trade_pairs']) > 10:
                report.append(f"  ... 还有 {len(result['trade_pairs']) - 10} 笔交易")
        else:
            report.append("  无交易记录")
        
        report.append("\n" + "="*60)
        return "\n".join(report)


STRATEGIES = {
    'macd_crossover': MinuteBacktester.generate_signals_macd_crossover,
    'rsi_overbought': MinuteBacktester.generate_signals_rsi_overbought,
    'ma_crossover': MinuteBacktester.generate_signals_ma_crossover,
    'bollinger': MinuteBacktester.generate_signals_bollinger
}


def main():
    parser = argparse.ArgumentParser(description='分钟线策略回测框架')
    parser.add_argument('--code', type=str, required=True, help='股票代码（如 000001）')
    parser.add_argument('--cycle', type=str, default='5m', help='周期（5m/15m/30m/60m）')
    parser.add_argument('--strategy', type=str, required=True, 
                       choices=STRATEGIES.keys(), help='策略类型')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--output', type=str, help='输出报告文件路径')
    parser.add_argument('--cash', type=float, default=100000.0, help='初始资金（默认10万）')
    parser.add_argument('--commission', type=float, default=0.0003, 
                       help='佣金费率（默认万分之三）')
    parser.add_argument('--min-commission', type=float, default=5.0, 
                       help='最低佣金（默认5元）')
    parser.add_argument('--slippage', type=float, default=0.001, 
                       help='滑点率（默认千分之一）')
    
    args = parser.parse_args()
    
    backtester = MinuteBacktester()
    
    # 获取数据
    df = backtester.fetch_minute_data(args.code, args.cycle, args.start, args.end)
    
    if df.empty:
        logger.error(f"❌ 未找到数据: {args.code} {args.cycle}")
        return
    
    logger.info(f"📥 获取数据: {len(df)} 条")
    logger.info(f"⚙️ 回测参数: 资金¥{args.cash:,.0f}, 佣金{args.commission*10000:.0f}%%(最低¥{args.min_commission}), 滑点{args.slippage*1000:.1f}‰")
    
    # 执行回测
    strategy_func = STRATEGIES[args.strategy]
    result = backtester.backtest(df, strategy_func, 
                                 initial_cash=args.cash,
                                 commission_rate=args.commission,
                                 slippage_rate=args.slippage,
                                 min_commission=args.min_commission)
    
    # 生成报告
    report = backtester.generate_report(args.code, args.cycle, result)
    print(report)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        logger.info(f"📝 报告已保存到: {args.output}")


if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""
Akshare 数据源实现

特点：
- 免费、无需Token
- 数据来源广泛（包括东方财富等）
- 作为Baostock的备用数据源，支持自动降级切换
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List
from .base import BaseDataSource


class AkshareDataSource(BaseDataSource):
    """Akshare 数据源实现"""
    
    # Akshare周期映射
    _CYCLE_MAP = {
        'daily': 'daily',
        'min5': '5',
        'min15': '15',
        'min30': '30',
        'min60': '60'
    }
    
    def __init__(self):
        self.connected = False
        self._ak = None
        self._last_request_time = 0
        self._request_interval = 0.5  # 默认请求间隔（秒）
    
    def _import_akshare(self):
        """延迟导入Akshare"""
        if self._ak is None:
            try:
                import akshare as ak
                self._ak = ak
            except ImportError:
                raise RuntimeError("Akshare未安装，请运行: pip install akshare")
        return self._ak
    
    def _rate_limit(self):
        """限流控制"""
        import time
        now = time.time()
        if now - self._last_request_time < self._request_interval:
            time.sleep(self._request_interval - (now - self._last_request_time))
        self._last_request_time = time.time()
    
    def connect(self) -> bool:
        """建立连接（Akshare无需登录）"""
        try:
            self._import_akshare()
            self.connected = True
            return True
        except Exception as e:
            return False
    
    def disconnect(self) -> bool:
        """断开连接（Akshare无需断开）"""
        self.connected = False
        return True
    
    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表"""
        if not self.connected:
            raise RuntimeError("未连接到Akshare")
        
        self._rate_limit()
        
        try:
            ak = self._import_akshare()
            
            # 获取股票列表
            df = ak.stock_info_a_code_name()
            
            if df.empty:
                return pd.DataFrame()
            
            # 获取行业信息
            industry_df = ak.stock_zh_a_classify_sector()
            
            # 处理数据
            result = pd.DataFrame({
                'code': df['code'],
                'name': df['name'],
                'exchange': df['code'].apply(lambda x: 'SH' if x.startswith('6') else 'SZ'),
                'industry': '',
                'list_date': '',
                'delist_date': ''
            })
            
            # 过滤有效股票：只保留沪市主板(60)、深市主板(000)、中小板(002)、创业板(300)
            # 排除：科创板(688)、北交所(8)、B股(9/2)、基金/债券等
            stock_code = result['code'].astype(str)
            valid_pattern = stock_code.str.match(r'^(60|000|002|300)\d{3}$')
            result = result[valid_pattern]
            
            # 填充行业信息
            if not industry_df.empty:
                industry_map = dict(zip(industry_df['code'], industry_df['industry']))
                result['industry'] = result['code'].map(industry_map).fillna('')
            
            return result
            
        except Exception as e:
            raise RuntimeError(f"获取股票列表异常: {str(e)}")
    
    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = 'none'  # none, qfq(前复权), hfq(后复权)
    ) -> pd.DataFrame:
        """获取K线数据"""
        if not self.connected:
            raise RuntimeError("未连接到Akshare")
        
        # 验证周期
        if cycle not in self._CYCLE_MAP:
            raise ValueError(f"不支持的周期: {cycle}")
        
        # 处理日期格式
        start = self._format_date(start_date) if start_date else None
        end = self._format_date(end_date) if end_date else None
        
        # 标准化代码
        code = self._normalize_code(code)
        
        self._rate_limit()
        
        try:
            ak = self._import_akshare()
            
            # 调整类型映射
            adjust_map = {
                'none': '',
                'qfq': 'qfq',
                'hfq': 'hfq'
            }
            
            # 分钟线和日线使用不同的API
            if cycle in ['min5', 'min15', 'min30', 'min60']:
                period_map = {
                    'min5': '5',
                    'min15': '15',
                    'min30': '30',
                    'min60': '60'
                }
                adjust_flag = adjust_map.get(adjust, 'qfq')  # 分钟线默认前复权
                df = ak.stock_zh_a_hist_min(
                    symbol=code,
                    start_date=start,
                    end_date=end,
                    period=period_map.get(cycle, '5'),
                    adjust=adjust_flag
                )
            else:
                # 日线使用 stock_zh_a_hist
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period=self._CYCLE_MAP[cycle],
                    start_date=start,
                    end_date=end,
                    adjust=adjust_map.get(adjust, '')
                )
            
            if df.empty:
                return pd.DataFrame()
            
            # 处理分钟线时间
            if cycle in ['min5', 'min15', 'min30', 'min60']:
                # stock_zh_a_hist_min 返回的时间格式可能是 'YYYY-MM-DD HH:MM:SS' 或包含日期时间
                if '时间' in df.columns:
                    df['trade_date'] = df['时间']
                elif 'datetime' in df.columns:
                    df['trade_date'] = df['datetime']
                else:
                    df['trade_date'] = df['日期'] + ' ' + df['时间']
            else:
                df['trade_date'] = df['日期']
            
            # 构建结果
            result = pd.DataFrame({
                'code': code,
                'trade_date': df['trade_date'],
                'open': pd.to_numeric(df['开盘'], errors='coerce'),
                'high': pd.to_numeric(df['最高'], errors='coerce'),
                'low': pd.to_numeric(df['最低'], errors='coerce'),
                'close': pd.to_numeric(df['收盘'], errors='coerce'),
                'volume': pd.to_numeric(df['成交量'], errors='coerce'),
                'amount': pd.to_numeric(df['成交额'], errors='coerce'),
                'cycle': cycle,
                'adjust': adjust  # 标记复权类型
            })
            
            # 按日期排序
            result = result.sort_values('trade_date').reset_index(drop=True)
            
            return result
            
        except Exception as e:
            raise RuntimeError(f"获取K线数据异常: {str(e)}")
    
    def get_trade_calendar(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exchange: str = 'SH'
    ) -> pd.DataFrame:
        """获取交易日历"""
        if not self.connected:
            raise RuntimeError("未连接到Akshare")
        
        self._rate_limit()
        
        try:
            ak = self._import_akshare()
            
            # 获取交易日历
            df = ak.tool_trade_date_hist_sina()
            
            if df.empty:
                return pd.DataFrame()
            
            # 格式化日期
            df['cal_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
            df['is_open'] = 1  # Akshare返回的都是交易日
            df['exchange'] = exchange
            
            # 过滤日期范围
            if start_date:
                df = df[df['cal_date'] >= start_date]
            if end_date:
                df = df[df['cal_date'] <= end_date]
            
            return df[['cal_date', 'is_open', 'exchange']].reset_index(drop=True)
            
        except Exception as e:
            return pd.DataFrame()
    
    def get_next_trade_date(self, last_date: str, exchange: str = 'SH') -> Optional[str]:
        """获取下一个交易日"""
        if not self.connected:
            raise RuntimeError("未连接到Akshare")
        
        try:
            end_date = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')
            calendar = self.get_trade_calendar(start_date=last_date, end_date=end_date, exchange=exchange)
            
            if calendar.empty:
                return self._simple_next_trade_date(last_date)
            
            mask = calendar['cal_date'] > last_date
            next_dates = calendar[mask]['cal_date'].sort_values()
            
            return next_dates.iloc[0] if not next_dates.empty else None
            
        except Exception:
            return self._simple_next_trade_date(last_date)
    
    def _simple_next_trade_date(self, last_date: str) -> Optional[str]:
        """简单计算下一个交易日（备用方案）"""
        try:
            dt = datetime.strptime(last_date, '%Y-%m-%d')
            for i in range(1, 10):
                next_dt = dt + timedelta(days=i)
                # 排除周末
                if next_dt.weekday() < 5:
                    return next_dt.strftime('%Y-%m-%d')
            return None
        except:
            return None
    
    def _normalize_code(self, code: str) -> str:
        """标准化股票代码（Akshare使用6位数字）"""
        code = str(code).strip()
        
        # 移除前缀
        if code.startswith('sh.'):
            return code[3:]
        if code.startswith('sz.'):
            return code[3:]
        if code.endswith('.SH'):
            return code[:-3]
        if code.endswith('.SZ'):
            return code[:-3]
        
        return code
    
    def _format_date(self, date_str: str) -> str:
        """转换日期格式为Akshare格式（YYYYMMDD）"""
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.strftime('%Y%m%d')
        except:
            return date_str
    
    @property
    def name(self) -> str:
        return "Akshare"
    
    @property
    def requires_token(self) -> bool:
        return False
    
    @property
    def supported_cycles(self) -> List[str]:
        return list(self._CYCLE_MAP.keys())

    def fetch_market_snapshot(self) -> Optional[pd.DataFrame]:
        """
        获取A股市场快照（所有股票实时行情）

        Returns:
            市场快照数据，包含代码、名称、最新价、涨跌幅等
        """
        if not self.connected:
            raise RuntimeError("未连接到Akshare")

        self._rate_limit()

        try:
            ak = self._import_akshare()

            # 获取实时行情数据
            df = ak.stock_zh_a_spot_em()

            if df is None or df.empty:
                return None

            # 重命名列以便统一处理
            column_map = {
                '代码': 'code',
                '名称': 'name',
                '最新价': 'price',
                '涨跌幅': 'pct_chg',
                '涨跌额': 'change',
                '今开': 'open',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'vol',
                '成交额': 'amount',
                '昨收': 'pre_close',
                '换手率': 'turnover_rate',
                '市盈率': 'pe'
            }

            # 重命名列
            df = df.rename(columns=column_map)

            # 确保必要的列存在
            required_cols = ['code', 'name', 'price']
            for col in required_cols:
                if col not in df.columns:
                    return None

            return df

        except Exception as e:
            raise RuntimeError(f"获取市场快照异常: {str(e)}")


# 测试代码
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    ds = AkshareDataSource()
    
    if ds.connect():
        print("✅ 连接成功")
        
        # 测试股票列表
        print("\n📋 获取股票列表...")
        stocks = ds.get_stock_list()
        print(f"获取到 {len(stocks)} 只股票")
        print(stocks.head())
        
        # 测试日线数据
        print("\n📊 获取日线数据...")
        df = ds.get_kline('600000', cycle='daily', start_date='2025-05-01', end_date='2025-05-28')
        print(f"获取到 {len(df)} 条日线数据")
        print(df.head())
        
        # 测试交易日历
        print("\n📅 获取交易日历...")
        calendar = ds.get_trade_calendar(start_date='2025-05-01', end_date='2025-05-31')
        print(f"获取到 {len(calendar)} 天")
        print(calendar.head())
        
        ds.disconnect()
        print("\n✅ 断开连接")
    else:
        print("❌ 连接失败")

import pandas as pd
import requests
from typing import Optional, List
import time
import random
import sys
import os

_current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from utils.logger import setup_logger

logger = setup_logger('sina_datasource')


class SinaDataSource:
    """东方财富实时行情数据源（替代新浪财经）"""
    
    name = 'Sina'
    
    def __init__(self):
        self.connected = False
        self._session = None
        self._request_interval = 0.5
        self._last_request_time = 0
    
    def connect(self) -> bool:
        """连接数据源"""
        try:
            self._session = requests.Session()
            self.connected = True
            logger.info("✅ 东方财富数据源连接成功")
            return True
        except Exception as e:
            logger.error(f"东方财富数据源连接失败: {str(e)}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self._session:
            self._session.close()
        self.connected = False
    
    def _rate_limit(self):
        """限流控制"""
        now = time.time()
        if now - self._last_request_time < self._request_interval:
            time.sleep(self._request_interval - (now - self._last_request_time))
        self._last_request_time = time.time()
    
    def fetch_market_snapshot(self) -> Optional[pd.DataFrame]:
        """
        获取A股市场快照（所有股票实时行情）
        
        Returns:
            市场快照数据
        """
        if not self.connected:
            raise RuntimeError("未连接到东方财富")
        
        self._rate_limit()
        
        try:
            # 东方财富实时行情接口
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'pn': 1,
                'pz': 5000,  # 每页最多5000条
                'po': 1,
                'np': 1,
                'fltt': 2,
                'invt': 2,
                'fid': 'f3',
                'fs': 'm:0 t:6,m:0 t:13,m:0 t:80,m:1 t:2,m:1 t:23',  # A股市场
                'fields': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f24,f25,f26,f27,f28,f30,f31,f32,f33,f34,f35,f36,f37,f38,f39,f40,f41,f42,f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65'
            }
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://quote.eastmoney.com/',
                'Accept': 'application/json, text/plain, */*'
            }
            
            response = self._session.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code != 200:
                return None
            
            result = response.json()
            
            if not result.get('data') or not result['data'].get('diff'):
                return None
            
            data = []
            for item in result['data']['diff']:
                try:
                    # 代码格式转换
                    market = item.get('f13', 0)  # 市场代码: 1=沪市, 0=深市
                    code = item.get('f12', '')
                    
                    if market == 1:
                        code = f"sh.{code}"
                    elif market == 0:
                        code = f"sz.{code}"
                    else:
                        code = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
                    
                    record = {
                        'code': code,
                        'name': item.get('f14', ''),
                        'price': item.get('f2', ''),
                        'change': item.get('f4', ''),
                        'pct_chg': item.get('f3', ''),
                        'open': item.get('f17', ''),
                        'high': item.get('f15', ''),
                        'low': item.get('f16', ''),
                        'vol': item.get('f5', ''),
                        'amount': item.get('f6', ''),
                        'pre_close': item.get('f18', ''),
                        'turnover_rate': item.get('f8', ''),
                        'pe': item.get('f9', '')
                    }
                    
                    # 确保价格字段是数字
                    for key in ['price', 'change', 'pct_chg', 'open', 'high', 'low', 'vol', 'amount', 'pre_close']:
                        if record[key] == '-' or record[key] == '':
                            record[key] = ''
                        elif isinstance(record[key], str):
                            try:
                                record[key] = float(record[key])
                            except:
                                record[key] = ''
                    
                    data.append(record)
                
                except Exception as e:
                    logger.debug(f"解析股票数据失败: {str(e)}")
                    continue
            
            if not data:
                return None
            
            df = pd.DataFrame(data)
            return df
            
        except Exception as e:
            logger.error(f"获取东方财富快照失败: {str(e)}")
            return None
    
    @property
    def supported_cycles(self) -> List[str]:
        return ['daily']


# 测试代码
if __name__ == '__main__':
    ds = SinaDataSource()
    if ds.connect():
        df = ds.fetch_market_snapshot()
        if df is not None and not df.empty:
            print(f"获取到 {len(df)} 条实时行情数据")
            print(df[['code', 'name', 'price', 'pct_chg']].head())
        ds.disconnect()

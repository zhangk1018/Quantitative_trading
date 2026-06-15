import pandas as pd
import requests
from typing import Optional, List
import time
import sys
import os

_current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from utils.logger import setup_logger

logger = setup_logger('tencent_datasource')


class TencentDataSource:
    """腾讯财经实时行情数据源"""
    
    name = 'Tencent'
    
    def __init__(self):
        self.connected = False
        self._session = None
        self._request_interval = 0.3
        self._last_request_time = 0
    
    def connect(self) -> bool:
        """连接数据源"""
        try:
            self._session = requests.Session()
            self.connected = True
            logger.info("✅ 腾讯财经数据源连接成功")
            return True
        except Exception as e:
            logger.error(f"腾讯财经数据源连接失败: {str(e)}")
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
            raise RuntimeError("未连接到腾讯财经")
        
        self._rate_limit()
        
        try:
            # 腾讯财经实时行情接口（批量获取）
            url = "https://qt.gtimg.cn/q="
            
            # 构建股票列表参数（沪深A股主要指数和热门股票）
            # 腾讯接口支持批量查询，一次最多约60只股票
            stock_groups = [
                # 上证A股 - 金融
                ["sh600000", "sh601398", "sh601988", "sh601328", "sh601166",
                 "sh600036", "sh601818", "sh601939", "sh600519", "sh601899"],
                # 上证A股 - 能源
                ["sh601857", "sh600028", "sh600008", "sh601088", "sh600583",
                 "sh601668", "sh600011", "sh600010", "sh600104", "sh600339"],
                # 上证A股 - 制造
                ["sh600030", "sh601318", "sh600518", "sh600031", "sh601601",
                 "sh601117", "sh600489", "sh600027", "sh600026", "sh600585"],
                # 深证A股 - 金融
                ["sz000001", "sz000002", "sz000858", "sz000333", "sz002594",
                 "sz002555", "sz002142", "sz000725", "sz000100", "sz000651"],
                # 深证A股 - 科技
                ["sz000063", "sz000768", "sz002230", "sz002352", "sz002415",
                 "sz002271", "sz002030", "sz000977", "sz000800", "sz002512"],
                # 创业板
                ["sz300001", "sz300059", "sz300104", "sz300033", "sz300251",
                 "sz300124", "sz300070", "sz300347", "sz300433", "sz300601"]
            ]
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://stockhtm.finance.qq.com/'
            }
            
            data = []
            
            # 逐个获取股票数据（避免批量请求的解析问题）
            all_stocks = []
            for group in stock_groups:
                all_stocks.extend(group)
            
            for stock_code in all_stocks:
                try:
                    full_url = f"{url}{stock_code}"
                    response = self._session.get(full_url, headers=headers, timeout=10)
                    response.encoding = 'gbk'
                    
                    if response.status_code != 200:
                        continue
                    
                    content = response.text.strip()
                    if not content:
                        continue
                    
                    # 解析格式：v_sz000001="1~平安银行~000001~10.00~...~";
                    parts = content.split('=')
                    if len(parts) < 2:
                        continue
                    
                    code_raw = parts[0].replace('v_', '')
                    stock_info = parts[1].strip().strip('"')
                    fields = stock_info.split('~')
                    
                    if len(fields) < 11:
                        continue
                    
                    # 代码格式转换
                    if code_raw.startswith('sh'):
                        code = f"sh.{code_raw[2:]}"
                    elif code_raw.startswith('sz'):
                        code = f"sz.{code_raw[2:]}"
                    else:
                        continue
                    
                    # 腾讯接口字段映射：
                    # fields[0]: 市场类型
                    # fields[1]: 股票名称
                    # fields[2]: 股票代码
                    # fields[3]: 当前价格
                    # fields[30]: 时间戳
                    # fields[31]: 涨跌额
                    # fields[32]: 涨跌幅(%)
                    # fields[33]: 最高价
                    # fields[34]: 最低价
                    # fields[35]: 开盘价/成交量/成交额
                    # fields[36]: 成交量(手)
                    # fields[37]: 成交额(万元)
                    # fields[38]: 换手率(%)
                    # fields[39]: 市盈率
                    record = {
                        'code': code,
                        'name': fields[1],
                        'price': float(fields[3]),
                        'change': float(fields[31]) if len(fields) > 31 else 0,
                        'pct_chg': float(fields[32]) if len(fields) > 32 else 0,
                        'open': float(fields[35].split('/')[0]) if len(fields) > 35 else 0,
                        'high': float(fields[33]) if len(fields) > 33 else 0,
                        'low': float(fields[34]) if len(fields) > 34 else 0,
                        'vol': float(fields[36]) * 100,
                        'amount': float(fields[37]) * 10000,
                        'pre_close': float(fields[3]) - float(fields[31]) if len(fields) > 31 else 0,
                        'turnover_rate': fields[38] if len(fields) > 38 else '',
                        'pe': fields[39] if len(fields) > 39 else ''
                    }
                    
                    data.append(record)
                    
                except Exception as e:
                    logger.debug(f"获取股票 {stock_code} 失败: {str(e)}")
                    continue
            
            if not data:
                return None
            
            df = pd.DataFrame(data)
            return df
            
        except Exception as e:
            logger.error(f"获取腾讯财经快照失败: {str(e)}")
            return None
    
    @property
    def supported_cycles(self) -> List[str]:
        return ['daily']


# 测试代码
if __name__ == '__main__':
    ds = TencentDataSource()
    if ds.connect():
        df = ds.fetch_market_snapshot()
        if df is not None and not df.empty:
            print(f"获取到 {len(df)} 条实时行情数据")
            print(df[['code', 'name', 'price', 'pct_chg']].head())
        ds.disconnect()

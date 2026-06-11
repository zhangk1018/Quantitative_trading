"""
api_client.py - 后台 FastAPI 客户端

【设计目标】
- 前台所有数据都通过这个客户端从后台获取
- 不直接连接数据库（保持前后端物理隔离）
- 支持重试、超时、缓存

【使用示例】
```python
from frontend.utils import BackendClient
client = BackendClient(base_url='http://localhost:8000')

# 获取 K线
kline = client.get_kline('000001.SZ', start='2023-01-01', end='2023-12-31', adj='forward')

# 获取股票列表
stocks = client.get_stocks(as_of_date='2026-06-05', sort_by='change_pct', limit=50)
```
"""

import os
import time
import logging
from typing import Optional, Dict, List, Any
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BackendClient:
    """
    后台 API 客户端

    特性：
    1. 自动重试（网络波动）
    2. 超时控制
    3. 错误日志
    """

    DEFAULT_TIMEOUT = 30
    DEFAULT_MAX_RETRIES = 3

    def __init__(
        self,
        base_url: str = 'http://localhost:8000',
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """GET 请求统一处理"""
        url = f'{self.base_url}{path}'
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get('code') != 200:
                raise BackendError(data.get('message', 'Unknown error'), data)
            return data.get('data')
        except requests.exceptions.RequestException as e:
            logger.error(f'❌ API 请求失败: {url} {e}')
            raise

    def get_kline(
        self,
        stock_code: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        cycle: str = '1d',
        adj: str = 'none',
    ) -> List[Dict]:
        """
        获取 K线数据

        Args:
            stock_code: 股票代码
            start: 开始日期 'YYYY-MM-DD'
            end: 结束日期 'YYYY-MM-DD'
            cycle: 周期 (1d/1w/1m/5m/...)
            adj: 复权方式 (none/forward/backward)

        Returns:
            K线数据列表
        """
        params = {
            'cycle': cycle,
            'adj': adj,
        }
        if start:
            params['start_date'] = start
        if end:
            params['end_date'] = end
        data = self._get(f'/api/kline/{stock_code}', params)
        return data.get('data', [])

    def get_stocks(
        self,
        as_of_date: str,
        sort_by: str = 'change_pct',
        sort_asc: bool = False,
        offset: int = 0,
        limit: int = 50,
        industry: Optional[str] = None,
        filters: Optional[str] = None,
    ) -> Dict:
        """
        获取股票列表

        Args:
            as_of_date: 数据截止日期 (YYYY-MM-DD)
            sort_by: 排序字段
            sort_asc: 是否升序
            offset: 分页偏移
            limit: 每页数量
            industry: 行业过滤
            filters: K线形态过滤

        Returns:
            {'total': int, 'data': [...]}
        """
        params = {
            'as_of_date': as_of_date,
            'sort_by': sort_by,
            'sort_asc': str(sort_asc).lower(),
            'offset': offset,
            'limit': limit,
        }
        if industry:
            params['industry'] = industry
        if filters:
            params['filters'] = filters
        return self._get('/api/stocks', params)

    def get_signals(
        self,
        stock_code: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict]:
        """获取买卖信号"""
        params = {}
        if start:
            params['start_date'] = start
        if end:
            params['end_date'] = end
        data = self._get(f'/api/signals/{stock_code}', params)
        return data.get('signals', [])

    def get_meta(self) -> Dict:
        """获取元数据（行业/地区/筛选选项）"""
        return self._get('/api/meta')

    def health_check(self) -> bool:
        """检查后台是否健康"""
        try:
            self._get('/api/meta', params={})  # 任意端点都行
            return True
        except Exception:
            return False


class BackendError(Exception):
    """后台 API 业务错误"""
    def __init__(self, message: str, response: Optional[Dict] = None):
        super().__init__(message)
        self.response = response

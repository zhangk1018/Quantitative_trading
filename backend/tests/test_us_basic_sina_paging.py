"""美股基本面（sync_us_basic）新浪分页抓取容错测试。

背景：2026-10-08 美股基本面 ETL 失败（看板美股链「基本面 ❌」）。根因：
`ak.stock_us_spot()` 内部分页循环对上游偶发异常响应无容错——新浪美股列表某页
返回错误对象（如 `{"__ERROR":"HY000","__ERRORMSG":"SQLSTATE[HY000]: General error:
2006 MySQL server has gone away",...}`，无 `data` 字段）时，官方实现直接取
`data_json["data"]` 抛 KeyError，使整任务失败（当日 3 次重试均因不同分页失败）。

修复：`_fetch_spot_df` 改为自实现分页，逐页重试；重试用尽后跳过该页并累计，
跳过占比超过 `_SINA_MAX_SKIP_RATIO` 时抛错放弃写入（宁缺勿残）。

全部用例注入假分页响应，不访问网络与数据库。

2026-10-08 创建
"""
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import pytest

# 保证 `collector.* / utils.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from collector.etl import sync_us_basic as m  # noqa: E402


def _ok_page(page: int, n: int = 20) -> Dict[str, Any]:
    """构造正常页响应：含 count 与 data。"""
    return {
        'count': '18262',
        'data': [
            {'symbol': f'SYM{page}_{i}', 'mktcap': '1e9', 'pe': '10', 'price': '1'}
            for i in range(n)
        ],
    }


def _err_page() -> Dict[str, Any]:
    """构造上游异常页响应：无 data 字段（复刻 2026-10-08 真实响应）。"""
    return {
        '__ERROR': 'HY000',
        '__ERRORMSG': 'SQLSTATE[HY000]: General error: 2006 MySQL server has gone away',
        '__ERRORFILE': '/data1/www/htdocs/stock7.finance.sina.com.cn/mysql.inc.php',
        '__ERRORLINE': 382,
    }


class _FakeSina:
    """假新浪分页源：按页返回正常/异常响应，支持「前 k 次失败后成功」。"""

    def __init__(self, pages: int, bad: Optional[Dict[int, int]] = None):
        """
        Args:
            pages: 总页数。
            bad: {页码: 需要连续失败次数}（取大值模拟持续异常页）。
        """
        self.pages = pages
        self.calls: List[int] = []
        self._fail_left: Dict[int, int] = dict(bad or {})

    def __call__(self, page: int) -> Dict[str, Any]:
        self.calls.append(page)
        if self._fail_left.get(page, 0) > 0:
            self._fail_left[page] -= 1
            return _err_page()
        return _ok_page(page)


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """缩短重试间隔，避免测试真等待。"""
    monkeypatch.setattr(m, '_SINA_RETRY_SLEEP', 0)


def _bind_pager(monkeypatch: pytest.MonkeyPatch, fake: _FakeSina) -> None:
    """绑定假分页源：总页数固定为该 fake 的 pages，逐页请求走 fake。"""
    monkeypatch.setattr(m, '_sina_page_count', lambda: fake.pages)
    monkeypatch.setattr(m, '_sina_page_payload', fake)


class TestSinaPageCount:
    """总页数计算（复用新浪 count 字段）。"""

    def test_rounds_up_partial_last_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(m, '_sina_page_payload', lambda p: {'count': '18262'})
        assert m._sina_page_count() == 914

    def test_exact_multiple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(m, '_sina_page_payload', lambda p: {'count': '40'})
        assert m._sina_page_count() == 2

    def test_retries_then_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _always_err(page: int) -> Dict[str, Any]:
            return _err_page()

        monkeypatch.setattr(m, '_sina_page_payload', _always_err)
        with pytest.raises(RuntimeError, match='总页数'):
            m._sina_page_count()


class TestFetchSpotDf:
    """分页抓取容错行为。"""

    def test_all_pages_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSina(pages=3)
        _bind_pager(monkeypatch, fake)
        df = m._fetch_spot_df()
        assert len(df) == 60
        assert set(df.columns) >= {'symbol', 'mktcap', 'pe'}

    def test_transient_error_page_retried_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """上游偶发异常页（如 MySQL gone away）重试即恢复，不丢数据。"""
        fake = _FakeSina(pages=3, bad={2: 2})  # 第 2 页连续失败 2 次后成功
        _bind_pager(monkeypatch, fake)
        df = m._fetch_spot_df()
        assert len(df) == 60
        assert fake.calls.count(2) == 3  # 失败 2 次 + 成功 1 次

    def test_persistent_error_page_skipped_when_within_ratio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """持续异常页在允许比例内被跳过，其余页照常返回。"""
        fake = _FakeSina(pages=40, bad={7: 99})
        _bind_pager(monkeypatch, fake)
        df = m._fetch_spot_df()
        assert len(df) == 39 * 20  # 少一页
        assert fake.calls.count(7) == m._SINA_PAGE_RETRIES

    def test_first_page_error_skips_not_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """关键回归：无 data 字段不再抛 KeyError 直接失败，而是按异常页跳过。"""
        fake = _FakeSina(pages=40, bad={1: 99})
        _bind_pager(monkeypatch, fake)
        df = m._fetch_spot_df()  # 不应抛 KeyError
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 39 * 20

    def test_skip_ratio_exceeded_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """跳过页占比超阈值 → 抛错放弃写入（宁缺勿残）。"""
        fake = _FakeSina(pages=4, bad={2: 99})  # 1/4 = 25% > 10%
        _bind_pager(monkeypatch, fake)
        with pytest.raises(RuntimeError, match='快照不完整'):
            m._fetch_spot_df()

    def test_all_pages_fail_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeSina(pages=5, bad={p: 99 for p in range(1, 6)})
        _bind_pager(monkeypatch, fake)
        with pytest.raises(RuntimeError, match='均失败'):
            m._fetch_spot_df()
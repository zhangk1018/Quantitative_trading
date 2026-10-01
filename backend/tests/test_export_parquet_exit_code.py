"""export_parquet 失败必须以非 0 退出码上报。

背景：`export_to_parquet` 原实现在「连接失败 / 宽表为空 / 当日无数据 / 导出异常」时
仅打印 `TASK_RESULT{error}` 便 return，进程退出码仍为 0 → job_runner 记为「成功」，
既不重试也不告警。2026-10-01 美股 Parquet 导出因 `OSError [Errno 18] Cross-device link`
失败即被这样掩盖，靠人工重跑才补齐。修复后函数返回 bool，`__main__` 转成退出码。

全部用例使用假 engine，不访问数据库、不触碰真实 parquet 文件。

2026-10-01 创建
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

# 保证 `clean.* / utils.*` 可解析（backend 为包根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from clean.enrich import export_parquet  # noqa: E402


def _fake_connection(fetchone_result, fetchall_rows=None, columns=('code', 'trade_date')):
    """构造假连接：execute() 兼顾 MAX(trade_date) 查询与明细查询。"""
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_rows if fetchall_rows is not None else []
    cursor.keys.return_value = list(columns)
    conn.execute.return_value = cursor
    return conn


def _fake_engine(conn):
    """构造假 engine（connect() 返回给定连接）。"""
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


class TestExportParquetExitStatus:
    """四个失败分支均须返回 False（由 __main__ 转成退出码 1）。"""

    def test_db_connect_failure_returns_false(self, monkeypatch) -> None:
        """数据库连接失败 → False。"""
        monkeypatch.setattr(export_parquet, 'create_engine',
                            MagicMock(side_effect=RuntimeError('connect refused')))
        assert export_parquet.export_to_parquet('us') is False

    def test_empty_table_returns_false(self, monkeypatch) -> None:
        """stock_daily_snapshot 该市场无任何数据 → False。"""
        monkeypatch.setattr(export_parquet, 'create_engine',
                            MagicMock(return_value=_fake_engine(_fake_connection((None,)))))
        assert export_parquet.export_to_parquet('us') is False

    def test_no_data_for_latest_date_returns_false(self, monkeypatch) -> None:
        """最新交易日无明细行 → False。"""
        conn = _fake_connection((date(2026, 9, 30),), fetchall_rows=[])
        monkeypatch.setattr(export_parquet, 'create_engine',
                            MagicMock(return_value=_fake_engine(conn)))
        assert export_parquet.export_to_parquet('us') is False

    def test_export_exception_returns_false(self, monkeypatch) -> None:
        """保存 parquet 抛异常（模拟本次 Cross-device link）→ False，不再静默成功。"""
        conn = _fake_connection((date(2026, 9, 30),),
                                fetchall_rows=[(1, date(2026, 9, 30))])
        monkeypatch.setattr(export_parquet, 'create_engine',
                            MagicMock(return_value=_fake_engine(conn)))
        # 备份轮转与落盘均不触碰真实文件
        monkeypatch.setattr(export_parquet, '_rotate_backups', lambda *args, **kwargs: None)

        def _boom(self, *args, **kwargs):
            raise OSError(18, 'Cross-device link')

        monkeypatch.setattr(pd.DataFrame, 'to_parquet', _boom)
        assert export_parquet.export_to_parquet('us') is False
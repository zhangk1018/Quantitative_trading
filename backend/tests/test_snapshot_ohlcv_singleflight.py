"""协作单 51.0：OHLCV 延迟加载的「单飞」并发守卫测试。

背景：原 `_ensure_ohlcv_loaded` 在 `_state_lock` 内判空后**立即释放锁**再 unpickle
231MB 的 `ohlcv.pkl`，缓存被刷新清空后并发请求各自解整包（实测 6 路同时），把整个
后端拖到分钟级，前端 20s 超时报「请求超时，请重试」。

本测试用「不使用假连接、不联网」的方式（直接 `__new__` 构造 + 打桩）验证：
N 个线程并发触发加载时，`pd.read_pickle` 只被调用**一次**，且所有线程都能拿到数据。
"""
import threading
from unittest.mock import patch

from core.service import snapshot_service as ss
from core.service.snapshot_service import SnapshotService


def _bare_service():
    """构造不带后台线程/不连库的裸服务实例（仅装配本测试用到的属性）。"""
    svc = SnapshotService.__new__(SnapshotService)
    svc._ohlcv_cache = {}
    svc._state_lock = threading.Lock()
    # 单飞锁：若实现里漏了该属性，本测试会以 AttributeError 直接失败
    svc._ohlcv_load_lock = threading.Lock()
    return svc


def test_concurrent_ensure_ohlcv_loaded_reads_pickle_once():
    svc = _bare_service()
    reads = []

    def fake_read_pickle(_f):
        reads.append(1)
        return {"600519": [[20260101, 1.0, 1.0, 1.0, 1.0, 100.0]]}

    threads = [threading.Thread(target=svc._ensure_ohlcv_loaded) for _ in range(8)]
    with patch.object(ss.os.path, "exists", return_value=True), \
         patch.object(SnapshotService, "_verify_signature", return_value=True), \
         patch.object(ss.pd, "read_pickle", side_effect=fake_read_pickle):
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(reads) == 1, f"并发下应只解包一次，实际 {len(reads)} 次"
    assert svc._ohlcv_cache, "加载后缓存应就绪"


def test_ensure_ohlcv_loaded_returns_immediately_when_warm():
    """已加载时不应再读文件（走无锁快路径）。"""
    svc = _bare_service()
    svc._ohlcv_cache = {"A": [[1, 1.0, 1.0, 1.0, 1.0, 1.0]]}
    with patch.object(ss.pd, "read_pickle", side_effect=AssertionError("不应解包")):
        svc._ensure_ohlcv_loaded()

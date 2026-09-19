"""
snapshot_service.py - 全量快照数据服务（最终优化版）

核心改进：
- 双缓存机制：刷新期间旧数据持续服务，原子切换
- 缓存安全：HMAC 签名校验，防反序列化注入
- 向量化加载：彻底消除逐行 Python 循环
- 增量查询二分查找：O(log n) 过滤
- 数据库重试机制：提升容错
- 精细化状态监控与进度日志
"""

import gc
import hashlib
import hmac
import json
import os
import pickle
import time
import logging
import threading
import bisect
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from shared.schemas import (
    SnapshotAllData,
    SnapshotHistoryData,
    SnapshotHistoryStock,
    SnapshotIncrementalData,
    SnapshotStock,
    SnapshotIndicators,
)
from utils.stock_code_utils import infer_market

logger = logging.getLogger(__name__)

# ================================================================
# 常量配置（集中管理）
# ================================================================
HISTORY_DAYS = 300
RANGE_MAX_DAYS = 1500               # /api/snapshot/all 范围模式（start_date/end_date）自然日上限（协作单 40.0）
FETCH_BATCH_SIZE = 10000
CACHE_CHECK_INTERVAL = 10 * 60          # 缓存检查防抖：10分钟
RELOAD_RETRY_COUNT = 3                  # 数据库重试次数
RELOAD_RETRY_BACKOFF = 2                # 重试退避基数（秒）

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)
CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "cache")
OHLCV_CACHE_FILE = os.path.join(CACHE_DIR, "ohlcv.pkl")
SNAPSHOT_CACHE_FILE = os.path.join(CACHE_DIR, "snapshot.pkl")
CACHE_META_FILE = os.path.join(CACHE_DIR, "cache_meta.json")
CACHE_VERSION = 5                       # v5: _load_from_db + _load_raw_data 新增 pre_close 字段

# HMAC 密钥（生产环境应通过环境变量注入）
HMAC_KEY = os.environ.get("CACHE_HMAC_KEY", "change_me_in_production").encode()

OHLCV_TIME = 0
OHLCV_OPEN = 1
OHLCV_HIGH = 2
OHLCV_LOW = 3
OHLCV_CLOSE = 4
OHLCV_VOLUME = 5

# 板块枚举（统一管理）
BOARD_VALUES = ("main_board", "gem", "beijing")

# ================================================================
# 历史逐日快照（/api/snapshot/history，协作单 35.0 回测口径对齐）
# ================================================================
# 字段白名单：与 stock_daily_snapshot 表实际列 / 选股 parquet 列完全一致，
# 保证回测逐日判定与选股视图（/api/stocks/）同一口径。
HISTORY_SNAPSHOT_FIELDS: Tuple[str, ...] = (
    # 行情/价格
    "open", "high", "low", "close", "pre_close", "volume", "amount",
    "change", "change_pct", "turnover_rate", "volume_ratio", "vol_ratio_5",
    # 技术指标
    "ma5", "ma10", "ma20", "ma60", "v_ma5",
    "rsi_6", "rsi_12", "rsi_24", "dif", "dea", "macd",
    "boll_upper", "boll_mid", "boll_lower",
    "kdj_k", "kdj_d", "kdj_j",
    # 估值/基本面（含 stock_daily_basic 同步字段，宽表已合并）
    "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_ratio", "dv_ttm",
    "market_cap", "circ_mv", "float_share", "net_mf_amount",
    # K 线形态（TA-Lib，宽表 boolean 化）
    "pattern_hammer", "pattern_morning_star", "pattern_evening_star",
    "pattern_bullish_engulfing", "pattern_bearish_engulfing",
    # 技术指标 pattern（14）
    "ma_long_align", "ma_short_align",
    "macd_low_golden_cross", "macd_bottom_divergence",
    "macd_high_death_cross", "macd_top_divergence",
    "boll_break_upper", "boll_break_middle_up", "boll_break_middle_down",
    "boll_break_lower",
    "rsi_low_golden_cross", "rsi_high_death_cross",
    "rsi_top_divergence", "rsi_bottom_divergence",
    # 突破/连续/状态
    "break_high_20", "break_high_60", "consec_up_days",
    "is_st", "is_new", "limit_up", "limit_down",
)
HISTORY_DEFAULT_DAYS = 300          # start_date 缺省时的回看自然天
HISTORY_MAX_DAYS = 500              # 区间自然天上限
HISTORY_MAX_CODES = 2000            # codes 数量上限
HISTORY_MAX_ROWS = 60000            # 返回行数上限（内存保护，超出提示缩小范围）
HISTORY_FETCH_BATCH = 5000          # 流式读取批大小

# ETL 窗口避让（工作日 15:00-20:00 为 ETL 管道执行时段）
# 在此期间避免触发后台刷新，减少内存争抢
ETL_AVOID_START_HOUR = 15
ETL_AVOID_END_HOUR = 20


class ServiceNotReadyError(RuntimeError):
    """服务数据未就绪异常（继承 RuntimeError，使全局处理器映射为 503）"""
    pass


class SnapshotService:
    """全量快照数据服务（双缓存 + 安全序列化 + 高性能加载）"""

    def __init__(self, pg_pool: psycopg2.pool.ThreadedConnectionPool) -> None:
        self._pool = pg_pool
        # 双缓存：当前提供服务的缓存
        self._ohlcv_cache: Dict[str, List[List[float]]] = {}
        self._snapshot_cache: Dict[str, dict] = {}
        self._latest_trade_date: Optional[str] = None
        self._cached_row_hash: Optional[str] = None
        self._ready = False
        self._loading = False
        self._load_error: Optional[Exception] = None
        # 状态锁（保护所有共享状态）
        self._state_lock = threading.Lock()
        # 后台刷新互斥锁（防止并发刷新）
        self._reload_mutex = threading.Lock()
        # 防抖时间戳
        self._last_check_time = 0
        # 加载进度统计
        self._load_progress = 0.0
        self._load_total = 0
        self._load_time = 0

        # 初始化元数据（不阻塞）
        try:
            latest, row_hash, _ = self._query_meta()
            with self._state_lock:
                self._latest_trade_date = latest
                self._cached_row_hash = row_hash
        except Exception as e:
            logger.error("初始元数据查询失败: %s", e)

        # 启动后台加载
        threading.Thread(target=self._load_all_async, daemon=True).start()
        # 启动独立定时刷新线程：请求路径不再触发刷新判断（协作单 39.0）
        threading.Thread(target=self._periodic_refresh_loop, daemon=True).start()
        logger.info("SnapshotService 初始化完成，数据后台加载中...")

    # ================================================================
    # 元数据查询（轻量级，仅查询最新交易日和行数哈希）
    # ================================================================
    def _query_meta(self) -> Tuple[str, str, int]:
        """返回 (latest_trade_date, row_hash, count)"""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(trade_date) FROM stock_daily_snapshot")
                row = cur.fetchone()
                if not row or not row[0]:
                    raise RuntimeError("stock_daily_snapshot 表无数据")
                latest = str(row[0])

                cur.execute("""
                    SELECT COUNT(*) FROM stock_quotes
                    WHERE cycle = '1d'
                      AND trade_date >= CAST(%s AS DATE) - CAST(%s AS INTERVAL)
                      AND trade_date <= %s
                """, (latest, f'{HISTORY_DAYS} days', latest))
                count = cur.fetchone()[0]
                row_hash = hashlib.md5(str(count).encode()).hexdigest()
                return latest, row_hash, count
        finally:
            self._pool.putconn(conn)

    # ================================================================
    # 缓存安全读写（HMAC 签名校验）
    # ================================================================
    def _compute_signature(self, data: bytes) -> str:
        return hmac.new(HMAC_KEY, data, hashlib.sha256).hexdigest()

    def _verify_signature(self, filepath: str) -> bool:
        sig_path = filepath + ".sig"
        if not os.path.exists(sig_path):
            return False
        with open(filepath, "rb") as f:
            content = f.read()
        with open(sig_path, "r") as f:
            sig = f.read().strip()
        return hmac.compare_digest(self._compute_signature(content), sig)

    def _write_with_signature(self, filepath: str, data: bytes) -> None:
        with open(filepath, "wb") as f:
            f.write(data)
        sig = self._compute_signature(data)
        with open(filepath + ".sig", "w") as f:
            f.write(sig)

    def _is_cache_valid(self, latest: str, row_hash: str) -> bool:
        if not os.path.exists(CACHE_META_FILE):
            return False
        if not os.path.exists(OHLCV_CACHE_FILE) or not os.path.exists(OHLCV_CACHE_FILE + ".sig"):
            return False
        if not os.path.exists(SNAPSHOT_CACHE_FILE) or not os.path.exists(SNAPSHOT_CACHE_FILE + ".sig"):
            return False
        # 验证文件完整性
        if not self._verify_signature(OHLCV_CACHE_FILE):
            logger.warning("OHLCV 缓存文件签名无效")
            return False
        if not self._verify_signature(SNAPSHOT_CACHE_FILE):
            logger.warning("Snapshot 缓存文件签名无效")
            return False
        try:
            with open(CACHE_META_FILE) as f:
                meta = json.load(f)
            return (
                meta.get("version") == CACHE_VERSION
                and meta.get("latest_trade_date") == latest
                and meta.get("row_count_hash") == row_hash
            )
        except Exception:
            return False

    def _load_from_cache(self) -> None:
        t0 = time.time()
        logger.info("📦 从安全缓存加载...")
        # 先加载快照（轻量级，2MB，启动必需）
        with open(SNAPSHOT_CACHE_FILE, "rb") as f:
            snapshot = pd.read_pickle(f)
        # 延迟加载 OHLCV：仅加载快照，OHLCV 在首次 API 请求时按需加载
        # 启动时跳过 OHLCV 加载，可降低峰值内存 ~700MB，避免被 Jetsam 杀死
        logger.info("  OHLCV 数据将在首次 API 请求时延迟加载")
        with open(CACHE_META_FILE) as f:
            meta = json.load(f)

        with self._state_lock:
            self._snapshot_cache = snapshot
            self._latest_trade_date = meta["latest_trade_date"]
            self._cached_row_hash = meta["row_count_hash"]
            self._load_time = time.time()
            self._ready = True
            self._load_error = None
        elapsed = time.time() - t0
        logger.info("✅ 缓存加载完成：%d 条快照，耗时 %.2fs",
                    len(snapshot), elapsed)

    # ================================================================
    # OHLCV 延迟加载（首次 API 请求时按需加载，避免启动内存峰值）
    # ================================================================
    def _ensure_ohlcv_loaded(self) -> None:
        """确保 OHLCV 数据已加载，未加载时从缓存文件按需加载"""
        with self._state_lock:
            if self._ohlcv_cache:
                return  # 已加载
        # 检查缓存文件是否存在
        if not os.path.exists(OHLCV_CACHE_FILE):
            logger.warning("OHLCV 缓存文件不存在，跳过延迟加载")
            return
        if not self._verify_signature(OHLCV_CACHE_FILE):
            logger.warning("OHLCV 缓存文件签名无效，跳过延迟加载")
            return
        t0 = time.time()
        logger.info("📊 延迟加载 OHLCV 数据...")
        with open(OHLCV_CACHE_FILE, "rb") as f:
            ohlcv = pd.read_pickle(f)
        with self._state_lock:
            self._ohlcv_cache = ohlcv
        elapsed = time.time() - t0
        logger.info("✅ OHLCV 延迟加载完成：%d 只股票，耗时 %.2fs",
                    len(ohlcv), elapsed)

    def _save_cache(self, count: int) -> None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with self._state_lock:
            ohlcv = self._ohlcv_cache
            snapshot = self._snapshot_cache
            latest = self._latest_trade_date
        # 序列化并签名
        ohlcv_bytes = pickle.dumps(ohlcv)
        snap_bytes = pickle.dumps(snapshot)
        self._write_with_signature(OHLCV_CACHE_FILE, ohlcv_bytes)
        self._write_with_signature(SNAPSHOT_CACHE_FILE, snap_bytes)

        row_hash = hashlib.md5(str(count).encode()).hexdigest()
        meta = {
            "version": CACHE_VERSION,
            "latest_trade_date": latest,
            "row_count_hash": row_hash,
            "created_at": time.time(),
        }
        with open(CACHE_META_FILE, "w") as f:
            json.dump(meta, f)
        with self._state_lock:
            self._cached_row_hash = row_hash
        logger.info("💾 缓存保存完成（OHLCV: %d 只，快照: %d 条）",
                    len(ohlcv), len(snapshot))

    # ================================================================
    # 数据库加载（彻底向量化 + 重试）
    # ================================================================
    def _load_from_db(self) -> None:
        """使用服务端游标 + pandas 向量化分组，完全避免逐行 Python 循环"""
        def _execute_load():
            conn = self._pool.getconn()
            try:
                # 使用服务端游标流式读取（需要事务上下文）
                with conn.cursor(name="ohlcv_cursor") as cur:
                    query = """
                        SELECT code,
                               EXTRACT(EPOCH FROM trade_date) AS ts,
                               open, high, low, close, volume, pre_close
                        FROM stock_quotes
                        WHERE cycle = '1d'
                          AND trade_date >= CAST(%s AS DATE) - CAST(%s AS INTERVAL)
                          AND trade_date <= %s
                        ORDER BY code, trade_date
                    """
                    params = (self._latest_trade_date, f'{HISTORY_DAYS} days', self._latest_trade_date)
                    # 使用服务端游标 + chunksize 分批读取，直接建 dict 避免中间列表
                    cur.execute(query, params)
                    ohlcv_dict: Dict[str, List[List[float]]] = {}
                    total_bars = 0
                    while True:
                        batch = cur.fetchmany(FETCH_BATCH_SIZE)
                        if not batch:
                            break
                        # 将 batch 转为 DataFrame 进行向量化处理
                        batch_df = pd.DataFrame(
                            batch,
                            columns=["code", "ts", "open", "high", "low", "close", "volume", "pre_close"],
                        )
                        # 直接合并到 ohlcv_dict，避免 all_chunks 中间列表
                        for code, group in batch_df.groupby("code"):
                            bars = group[["ts", "open", "high", "low", "close", "volume", "pre_close"]].fillna(0).values.tolist()
                            if code in ohlcv_dict:
                                ohlcv_dict[code].extend(bars)
                            else:
                                ohlcv_dict[code] = bars
                            total_bars += len(bars)
                        # 每批后主动释放中间 DataFrame 内存
                        del batch_df
                        gc.collect()
                    # 由于查询已按 code, trade_date 排序，每个 code 的列表已有序
                    self._ohlcv_cache = ohlcv_dict
                    logger.info("📊 OHLCV 加载完成：%d 只股票，%d 条K线", len(ohlcv_dict), total_bars)
                    self._load_total = total_bars
                    self._load_progress = 1.0

                # 加载快照
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            code, stock_name, listed_board, industry, trade_date,
                            close, change_pct, market_cap, turnover_rate, pe_ttm, pb,
                            ma5, ma10, ma20, ma60,
                            rsi_6, rsi_12, rsi_24,
                            dif, dea, macd,
                            boll_upper, boll_mid, boll_lower,
                            is_macd_golden_cross, is_macd_dead_cross
                        FROM stock_daily_snapshot
                        WHERE trade_date = %s
                    """, (self._latest_trade_date,))
                    rows = cur.fetchall()
                    self._snapshot_cache = {r["code"]: dict(r) for r in rows}
                    logger.info("📋 快照加载完成：%d 只股票", len(self._snapshot_cache))

                # 数据一致性校验
                missing_ohlcv = set(self._snapshot_cache.keys()) - set(self._ohlcv_cache.keys())
                if missing_ohlcv:
                    logger.warning("⚠️ %d 只股票有快照但无 OHLCV 数据", len(missing_ohlcv))
                missing_snap = set(self._ohlcv_cache.keys()) - set(self._snapshot_cache.keys())
                if missing_snap:
                    logger.warning("⚠️ %d 只股票有 OHLCV 但无快照数据", len(missing_snap))

                # 保存缓存（使用当前最新数据）
                count = sum(len(v) for v in self._ohlcv_cache.values())
                self._save_cache(count)

            finally:
                self._pool.putconn(conn)

        # 带重试的执行
        last_exception = None
        for attempt in range(1, RELOAD_RETRY_COUNT + 1):
            try:
                _execute_load()
                return
            except Exception as e:
                last_exception = e
                logger.warning("数据库加载失败 (尝试 %d/%d): %s", attempt, RELOAD_RETRY_COUNT, e)
                if attempt < RELOAD_RETRY_COUNT:
                    wait = RELOAD_RETRY_BACKOFF ** attempt
                    time.sleep(wait)
        raise RuntimeError(f"数据库加载失败，重试 {RELOAD_RETRY_COUNT} 次后仍失败") from last_exception

    # ================================================================
    # 统一加载入口（异步 + 双缓存）
    # ================================================================
    def _load_all_async(self) -> None:
        try:
            self._load_all()
        except Exception as e:
            with self._state_lock:
                self._load_error = e
                self._loading = False
                self._ready = False
            logger.error("后台加载异常: %s", e, exc_info=True)

    def _load_all(self) -> None:
        """主加载流程：尝试缓存，否则数据库加载，并原子切换双缓存"""
        # 先读取元数据（可能已存在）
        if self._latest_trade_date is None or self._cached_row_hash is None:
            latest, row_hash, _ = self._query_meta()
            with self._state_lock:
                self._latest_trade_date = latest
                self._cached_row_hash = row_hash

        # 尝试从缓存加载（缓存加载直接修改当前缓存，因为此时尚未对外服务）
        if self._is_cache_valid(self._latest_trade_date, self._cached_row_hash):
            self._load_from_cache()
            with self._state_lock:
                self._loading = False
                self._ready = True
                self._load_error = None
            return

        # 缓存无效，从数据库加载（此时可能还没有任何缓存，所以直接修改当前缓存）
        logger.info("🔄 缓存无效，从数据库加载...")
        with self._state_lock:
            self._loading = True
            self._ready = False
            self._load_error = None
            self._load_progress = 0.0
        try:
            self._load_from_db()
            with self._state_lock:
                self._ready = True
                self._load_error = None
                self._load_time = time.time()
                self._loading = False
            # 主动 GC 释放数据库加载中间数据
            gc.collect()
            logger.info("✅ 快照数据就绪 (加载耗时 %.2fs)", time.time() - self._load_time)
        except Exception as e:
            with self._state_lock:
                self._load_error = e
                self._ready = False
                self._loading = False
            raise

    # ================================================================
    # 智能刷新检查（防抖 + 锁定 + ETL 窗口避让）
    # ================================================================
    @staticmethod
    def _is_etl_window() -> bool:
        """检查是否处于 ETL 管道执行窗口（工作日 15:00-20:00）

        ETL 期间避免触发后台刷新，减少内存争抢，降低被 Jetsam 杀死的风险。
        """
        now = datetime.now()
        # 周一=0, 周日=6 → 0-4 为工作日
        if now.weekday() >= 5:
            return False  # 周末无 ETL
        return ETL_AVOID_START_HOUR <= now.hour < ETL_AVOID_END_HOUR

    def _refresh_if_needed(self) -> None:
        """检查是否需要刷新，使用防抖和互斥锁防止并发刷新"""
        # ETL 窗口避让：不检查也不刷新，防止内存争抢
        if self._is_etl_window():
            return

        now = time.time()
        # 防抖：检查间隔内不重复检查
        with self._state_lock:
            if now - self._last_check_time < CACHE_CHECK_INTERVAL:
                return
            self._last_check_time = now

        # 检查元数据是否变化
        try:
            latest, row_hash, _ = self._query_meta()
        except Exception as e:
            logger.warning("刷新检查查询元数据失败: %s", e)
            return

        with self._state_lock:
            current_latest = self._latest_trade_date
            current_hash = self._cached_row_hash
            is_loading = self._loading

        if (latest != current_latest) or (row_hash != current_hash):
            if is_loading:
                logger.debug("刷新已在后台进行，跳过本次触发")
                return
            # 尝试获取刷新锁
            if self._reload_mutex.acquire(blocking=False):
                try:
                    logger.info("🔄 检测到数据变更，触发后台刷新...")
                    # 更新元数据（原子）；刷新期间保持 _ready=True，旧缓存继续对外服务
                    # （双缓存热切换：新数据就绪后由 _reload_async 原子替换）
                    with self._state_lock:
                        self._latest_trade_date = latest
                        self._cached_row_hash = row_hash
                        self._loading = True
                        self._load_error = None
                    # 启动异步刷新线程
                    threading.Thread(target=self._reload_async, daemon=True).start()
                finally:
                    self._reload_mutex.release()
            else:
                logger.debug("刷新锁已被占用，跳过")

    def _periodic_refresh_loop(self) -> None:
        """后台独立线程：按固定周期检查数据变更并刷新（协作单 39.0）

        与请求量解耦：请求路径只读缓存、不触发刷新判断；
        数据变更检测与全量重建仅在此线程内发生，高峰期不再反复触发。
        """
        logger.info("🔁 后台定时刷新线程启动（周期 %d 秒）", CACHE_CHECK_INTERVAL)
        while True:
            time.sleep(CACHE_CHECK_INTERVAL)
            try:
                self._refresh_if_needed()
            except Exception as e:
                logger.warning("定时刷新检查异常: %s", e)

    def _reload_async(self) -> None:
        """异步刷新：使用双缓存加载新数据，完成后原子替换"""
        try:
            # 创建临时缓存对象（复制当前服务中的元数据）
            with self._state_lock:
                latest = self._latest_trade_date
                row_hash = self._cached_row_hash

            # 临时存储新数据
            new_ohlcv: Dict[str, List[List[float]]] = {}
            new_snapshot: Dict[str, dict] = {}

            # 使用单独连接加载（避免影响当前连接）
            conn = self._pool.getconn()
            try:
                # 加载 OHLCV（同 _load_from_db 但将结果存入临时变量）
                # 此处复用加载逻辑，但为了代码简洁，我们直接调用一个内部加载函数，返回数据
                # 但为了清晰，我们重新实现一段加载代码（略重复，但保持独立）
                # 实际可抽取公共加载函数，但这里为了简洁，直接内联
                # 为避免重复，我们调用一个私有方法 _load_raw_data()
                new_ohlcv, new_snapshot = self._load_raw_data(latest)
            finally:
                self._pool.putconn(conn)

            # 保存缓存（使用新数据）
            count = sum(len(v) for v in new_ohlcv.values())
            os.makedirs(CACHE_DIR, exist_ok=True)
            ohlcv_bytes = pickle.dumps(new_ohlcv)
            snap_bytes = pickle.dumps(new_snapshot)
            self._write_with_signature(OHLCV_CACHE_FILE, ohlcv_bytes)
            self._write_with_signature(SNAPSHOT_CACHE_FILE, snap_bytes)
            row_hash_new = hashlib.md5(str(count).encode()).hexdigest()
            meta = {
                "version": CACHE_VERSION,
                "latest_trade_date": latest,
                "row_count_hash": row_hash_new,
                "created_at": time.time(),
            }
            with open(CACHE_META_FILE, "w") as f:
                json.dump(meta, f)

            # 原子替换缓存（双缓存切换）
            with self._state_lock:
                self._ohlcv_cache = new_ohlcv
                self._snapshot_cache = new_snapshot
                self._latest_trade_date = latest
                self._cached_row_hash = row_hash_new
                self._load_time = time.time()
                self._ready = True
                self._load_error = None
                self._loading = False
            logger.info("✅ 刷新完成，新缓存已生效 (耗时 %.2fs)", time.time() - self._load_time)

        except Exception as e:
            with self._state_lock:
                self._load_error = e
                self._loading = False
                # 保持旧缓存继续服务（_ready 保持不变）
            logger.error("刷新失败: %s", e, exc_info=True)

    def _load_raw_data(self, latest_trade_date: str) -> Tuple[Dict[str, List[List[float]]], Dict[str, dict]]:
        """加载原始数据，返回 (ohlcv_dict, snapshot_dict)"""
        conn = self._pool.getconn()
        try:
            # 使用服务端游标流式读取（需要事务上下文）
            with conn.cursor(name="ohlcv_cursor") as cur:
                query = """
                    SELECT code,
                           EXTRACT(EPOCH FROM trade_date) AS ts,
                           open, high, low, close, volume
                    FROM stock_quotes
                    WHERE cycle = '1d'
                      AND trade_date >= CAST(%s AS DATE) - CAST(%s AS INTERVAL)
                      AND trade_date <= %s
                    ORDER BY code, trade_date
                """
                params = (latest_trade_date, f'{HISTORY_DAYS} days', latest_trade_date)
                cur.execute(query, params)
                ohlcv_dict = {}
                while True:
                    batch = cur.fetchmany(FETCH_BATCH_SIZE)
                    if not batch:
                        break
                    batch_df = pd.DataFrame(
                        batch,
                        columns=["code", "ts", "open", "high", "low", "close", "volume"],
                    )
                    for code, group in batch_df.groupby("code"):
                        bars = group[["ts", "open", "high", "low", "close", "volume"]].fillna(0).values.tolist()
                        if code in ohlcv_dict:
                            ohlcv_dict[code].extend(bars)
                        else:
                            ohlcv_dict[code] = bars
                    # 每批后释放中间 DataFrame 内存
                    del batch_df
                    gc.collect()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        code, stock_name, listed_board, industry, trade_date,
                        close, change_pct, market_cap, turnover_rate, pe_ttm, pb,
                        ma5, ma10, ma20, ma60,
                        rsi_6, rsi_12, rsi_24,
                        dif, dea, macd,
                        boll_upper, boll_mid, boll_lower,
                        is_macd_golden_cross, is_macd_dead_cross
                    FROM stock_daily_snapshot
                    WHERE trade_date = %s
                """, (latest_trade_date,))
                rows = cur.fetchall()
                snapshot_dict = {r["code"]: dict(r) for r in rows}
            return ohlcv_dict, snapshot_dict
        finally:
            self._pool.putconn(conn)

    # ================================================================
    # 范围模式 OHLCV 加载（协作单 40.0：/api/snapshot/all 按回测区间直查，绕过 300 天缓存）
    # ================================================================
    def _load_ohlcv_range(
        self,
        codes: List[str],
        start_date: date,
        end_date: date,
    ) -> Dict[str, List[List[float]]]:
        """按 codes + [start_date, end_date] 从 stock_quotes 直查 OHLCV（仅范围模式使用）。

        与 `_load_raw_data` 的 bar 格式保持一致：[ts, open, high, low, close, volume]（6 列，
        前端 fillPreClose 自行补第 7 列 pre_close）。服务端游标 + 向量化分组，无逐行循环。
        """
        conn = self._pool.getconn()
        try:
            ohlcv_dict: Dict[str, List[List[float]]] = {}
            total_bars = 0
            with conn.cursor(name="ohlcv_range_cursor") as cur:
                cur.execute(
                    """
                    SELECT code,
                           EXTRACT(EPOCH FROM trade_date) AS ts,
                           open, high, low, close, volume
                    FROM stock_quotes
                    WHERE cycle = '1d'
                      AND code = ANY(%s)
                      AND trade_date BETWEEN %s AND %s
                    ORDER BY code, trade_date
                    """,
                    (codes, start_date, end_date),
                )
                while True:
                    batch = cur.fetchmany(FETCH_BATCH_SIZE)
                    if not batch:
                        break
                    batch_df = pd.DataFrame(
                        batch,
                        columns=["code", "ts", "open", "high", "low", "close", "volume"],
                    )
                    for code, group in batch_df.groupby("code"):
                        bars = group[["ts", "open", "high", "low", "close", "volume"]].fillna(0).values.tolist()
                        if code in ohlcv_dict:
                            ohlcv_dict[code].extend(bars)
                        else:
                            ohlcv_dict[code] = bars
                        total_bars += len(bars)
                    del batch_df
                    gc.collect()
            logger.info("📊 范围 OHLCV 加载完成：%d 只股票，%d 条K线", len(ohlcv_dict), total_bars)
            return ohlcv_dict
        finally:
            self._pool.putconn(conn)

    # ================================================================
    # 状态与辅助方法
    # ================================================================
    def _ensure_ready(self) -> None:
        with self._state_lock:
            if not self._ready:
                if self._load_error:
                    raise ServiceNotReadyError(f"数据加载失败: {self._load_error}")
                raise ServiceNotReadyError("数据正在加载中，请稍后重试")

    def _build_indicators(self, row: dict) -> SnapshotIndicators:
        return SnapshotIndicators(
            ma5=float(row['ma5']) if row['ma5'] is not None else None,
            ma10=float(row['ma10']) if row['ma10'] is not None else None,
            ma20=float(row['ma20']) if row['ma20'] is not None else None,
            ma60=float(row['ma60']) if row['ma60'] is not None else None,
            rsi_6=float(row['rsi_6']) if row['rsi_6'] is not None else None,
            rsi_12=float(row['rsi_12']) if row['rsi_12'] is not None else None,
            rsi_24=float(row['rsi_24']) if row['rsi_24'] is not None else None,
            macd_dif=float(row['dif']) if row['dif'] is not None else None,
            macd_dea=float(row['dea']) if row['dea'] is not None else None,
            macd=float(row['macd']) if row['macd'] is not None else None,
            boll_upper=float(row['boll_upper']) if row['boll_upper'] is not None else None,
            boll_mid=float(row['boll_mid']) if row['boll_mid'] is not None else None,
            boll_lower=float(row['boll_lower']) if row['boll_lower'] is not None else None,
            is_macd_golden_cross=bool(row['is_macd_golden_cross']) if row['is_macd_golden_cross'] is not None else False,
            is_macd_dead_cross=bool(row['is_macd_dead_cross']) if row['is_macd_dead_cross'] is not None else False,
        )

    def _build_stock_snapshot(self, code: str, row: dict, ohlcv: List[List[float]]) -> SnapshotStock:
        return SnapshotStock(
            code=code,
            name=row.get('stock_name') or '',
            listed_board=row.get('listed_board') or '',
            industry=row.get('industry') or '',
            trade_date=row['trade_date'],
            close=float(row['close']) if row['close'] is not None else 0.0,
            change_pct=float(row['change_pct']) if row['change_pct'] is not None else None,
            market_cap=float(row['market_cap']) if row['market_cap'] is not None else None,
            turnover_rate=float(row['turnover_rate']) if row['turnover_rate'] is not None else None,
            pe_ttm=float(row['pe_ttm']) if row['pe_ttm'] is not None else None,
            pb=float(row['pb']) if row['pb'] is not None else None,
            indicators=self._build_indicators(row),
            ohlcv=ohlcv,
        )

    # ================================================================
    # 公开 API（入参校验完整）
    # ================================================================
    def get_all_snapshot(self, market: Optional[str] = None, board: Optional[str] = None, industry: Optional[str] = None,
                         codes: Optional[List[str]] = None,
                         start_date: Optional[str] = None, end_date: Optional[str] = None) -> SnapshotAllData:
        if board is not None and board not in BOARD_VALUES:
            raise ValueError(f"board 参数无效，允许值: {BOARD_VALUES}")
        if industry is not None:
            if not isinstance(industry, str) or len(industry) > 100:
                raise ValueError("industry 必须为字符串且长度不超过100")
            if not industry.isalnum() and not all(c in "_- " for c in industry):
                raise ValueError("industry 包含非法字符")

        # 范围模式（协作单 40.0）：start_date/end_date 任一传入时，按 [start_date, end_date]
        # 对 codes 候选池直查 stock_quotes，返回区间内 OHLCV 与 trade_dates（回测早期区间不再被
        # 300 天缓存窗口截断）。缺省（均未传）保持现状：使用 300 天缓存，选股等现有调用无回归。
        if start_date is not None or end_date is not None:
            return self._get_all_snapshot_range(
                market=market, board=board, industry=industry, codes=codes,
                start_date=start_date, end_date=end_date,
            )

        self._ensure_ready()
        # 延迟加载 OHLCV（首次 API 请求时按需加载，避免启动内存峰值）
        self._ensure_ohlcv_loaded()

        with self._state_lock:
            snapshot_cache = self._snapshot_cache
            ohlcv_cache = self._ohlcv_cache
            latest = self._latest_trade_date

        code_set = set(codes) if codes else None
        stocks = []
        date_set = set()
        # 按 codes 哈希索引直接读取（O(K)），未传 codes 时全量遍历（O(N)）（协作单 39.0）
        iterable = (
            ((c, snapshot_cache.get(c)) for c in code_set)
            if code_set is not None else snapshot_cache.items()
        )
        for code, row in iterable:
            if row is None:
                continue
            # 按市场过滤（A股6位→cn / 港股带.HK→hk / 美股字母→us）
            if market and infer_market(code) != market:
                continue
            if board and row.get('listed_board', '') != board:
                continue
            if industry and row.get('industry', '') != industry:
                continue
            ohlcv = ohlcv_cache.get(code, [])
            for bar in ohlcv:
                ts = float(bar[OHLCV_TIME])
                date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                date_set.add(date_str)
            stocks.append(self._build_stock_snapshot(code, row, ohlcv))

        trade_dates = sorted(date_set)
        return SnapshotAllData(
            latest_trade_date=latest or '',
            total=len(stocks),
            trade_dates=trade_dates,
            stocks=stocks,
        )

    def _get_all_snapshot_range(self, market: Optional[str], board: Optional[str], industry: Optional[str],
                                codes: Optional[List[str]], start_date: Optional[str], end_date: Optional[str]) -> SnapshotAllData:
        """范围模式实现（协作单 40.0）：codes 候选池 + [start_date, end_date] 直查 stock_quotes。

        仅对传入 codes 拉取区间 OHLCV（O(K)，避免全市场全量加载），快照元数据仍复用
        `_snapshot_cache`（最新交易日行，与缺省路径同口径）；trade_dates 由区间 K 线推导。
        """
        if not codes:
            raise ValueError("start_date/end_date 模式必须同时传入 codes（候选池），避免全市场全量拉取")
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
            end = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
        except ValueError:
            raise ValueError("start_date/end_date 格式必须为 YYYY-MM-DD")

        self._ensure_ready()
        with self._state_lock:
            snapshot_cache = self._snapshot_cache
            latest = self._latest_trade_date
        if end is None:
            end = datetime.strptime(latest[:10], '%Y-%m-%d').date() if latest else datetime.now().date()
        if start is None:
            start = end - timedelta(days=HISTORY_DAYS)
        if start > end:
            raise ValueError("start_date 不能晚于 end_date")
        if (end - start).days > RANGE_MAX_DAYS:
            raise ValueError(f"日期区间超过上限 {RANGE_MAX_DAYS} 天，请缩小范围")

        ohlcv_range = self._load_ohlcv_range(list(dict.fromkeys(codes)), start, end)
        stocks = []
        date_set = set()
        for code in dict.fromkeys(codes):
            ohlcv = ohlcv_range.get(code)
            if not ohlcv:
                continue
            if market and infer_market(code) != market:
                continue
            row = snapshot_cache.get(code)
            if row is None:
                continue  # 与缺省路径口径一致：无最新快照行则跳过
            if board and row.get('listed_board', '') != board:
                continue
            if industry and row.get('industry', '') != industry:
                continue
            for bar in ohlcv:
                ts = float(bar[OHLCV_TIME])
                date_set.add(datetime.fromtimestamp(ts).strftime('%Y-%m-%d'))
            stocks.append(self._build_stock_snapshot(code, row, ohlcv))

        trade_dates = sorted(date_set)
        return SnapshotAllData(
            latest_trade_date=latest or '',
            total=len(stocks),
            trade_dates=trade_dates,
            stocks=stocks,
        )

    def get_incremental_snapshot(self, since: str, market: Optional[str] = None, board: Optional[str] = None, industry: Optional[str] = None,
                                codes: Optional[List[str]] = None) -> SnapshotIncrementalData:
        try:
            since_ts = int(datetime.strptime(since, '%Y-%m-%d').timestamp())
        except ValueError:
            raise ValueError("since 格式必须为 YYYY-MM-DD")
        if board is not None and board not in BOARD_VALUES:
            raise ValueError(f"board 参数无效，允许值: {BOARD_VALUES}")
        if industry is not None:
            if not isinstance(industry, str) or len(industry) > 100:
                raise ValueError("industry 必须为字符串且长度不超过100")
            if not industry.isalnum() and not all(c in "_- " for c in industry):
                raise ValueError("industry 包含非法字符")

        self._ensure_ready()
        # 延迟加载 OHLCV（首次 API 请求时按需加载，避免启动内存峰值）
        self._ensure_ohlcv_loaded()

        with self._state_lock:
            snapshot_cache = self._snapshot_cache
            ohlcv_cache = self._ohlcv_cache
            latest = self._latest_trade_date

        code_set = set(codes) if codes else None
        stocks = []
        days_set = set()
        # 按 codes 哈希索引直接读取（O(K)），未传 codes 时全量遍历（O(N)）（协作单 39.0）
        iterable = (
            ((c, snapshot_cache.get(c)) for c in code_set)
            if code_set is not None else snapshot_cache.items()
        )
        for code, row in iterable:
            if row is None:
                continue
            # 按市场过滤（A股6位→cn / 港股带.HK→hk / 美股字母→us）
            if market and infer_market(code) != market:
                continue
            if board and row.get('listed_board', '') != board:
                continue
            if industry and row.get('industry', '') != industry:
                continue
            ohlcv = ohlcv_cache.get(code, [])
            if not ohlcv:
                continue
            # 二分查找定位起始位置（假设 ohlcv 按时间升序排列）
            times = [bar[OHLCV_TIME] for bar in ohlcv]
            idx = bisect.bisect_left(times, since_ts)
            inc_ohlcv = ohlcv[idx:]
            if not inc_ohlcv:
                continue
            for bar in inc_ohlcv:
                days_set.add(bar[OHLCV_TIME])
            stocks.append(self._build_stock_snapshot(code, row, inc_ohlcv))

        return SnapshotIncrementalData(
            since=since,
            latest_trade_date=latest or '',
            days=len(days_set),
            stocks=stocks,
        )

    @property
    def latest_trade_date(self) -> Optional[str]:
        self._ensure_ready()
        with self._state_lock:
            return self._latest_trade_date

    # ================================================================
    # 历史逐日快照（回测逐日判定，与选股视图同口径）
    # ================================================================
    @staticmethod
    def _coerce_history_value(value: Any) -> Any:
        """将 DB 原生类型转换为 JSON 友好类型（Decimal→float / date→str）"""
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, date):
            return value.strftime('%Y-%m-%d')
        return value

    def get_history_snapshots(
        self,
        codes: List[str],
        market: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        fields: Optional[List[str]] = None,
    ) -> SnapshotHistoryData:
        """按股票列表 + 日期区间返回 stock_daily_snapshot 全历史预计算字段（只读）。

        数据直接读取宽表（含 stock_daily_basic 合并的基本面列），不做前端重算，
        与选股视图 /api/stocks/（parquet 源 = 同一宽表）口径逐字段一致。

        Args:
            codes: 股票代码列表（去重前可带空格），上限 HISTORY_MAX_CODES。
            market: 市场过滤 cn/hk/us；传入时剔除推断市场不符的代码。
            start_date: 起始日期 YYYY-MM-DD（含），缺省 = end_date - HISTORY_DEFAULT_DAYS。
            end_date: 结束日期 YYYY-MM-DD（含），缺省 = 最新交易日。
            fields: 字段白名单裁剪（交集），缺省返回 HISTORY_SNAPSHOT_FIELDS 全量。

        Returns:
            SnapshotHistoryData：按股票分组的逐日快照行（trade_date 升序）。

        Raises:
            ValueError: 参数无效（codes 为空/超限、日期格式错误、区间超限、行数超限等）。
        """
        # --- codes 校验与去重 ---
        if not codes:
            raise ValueError("codes 不能为空")
        code_list = [c.strip().upper() for c in codes if c and c.strip()]
        code_list = list(dict.fromkeys(code_list))
        if not code_list:
            raise ValueError("codes 不能为空")
        if len(code_list) > HISTORY_MAX_CODES:
            raise ValueError(f"codes 数量超过上限 {HISTORY_MAX_CODES}，请分批请求")

        # --- market 校验与代码过滤 ---
        mkt: Optional[str] = None
        if market:
            mkt = market.strip().lower()
            if mkt not in ('cn', 'hk', 'us'):
                raise ValueError("market 参数无效，可选：cn,hk,us")
            code_list = [c for c in code_list if infer_market(c) == mkt]
            if not code_list:
                raise ValueError(f"codes 中无 {mkt} 市场股票")

        # --- fields 白名单裁剪 ---
        if fields:
            req_set = {f.strip() for f in fields if f and f.strip()}
            field_list = [f for f in HISTORY_SNAPSHOT_FIELDS if f in req_set]
            if not field_list:
                field_list = list(HISTORY_SNAPSHOT_FIELDS)
        else:
            field_list = list(HISTORY_SNAPSHOT_FIELDS)

        # --- 日期缺省与校验 ---
        self._ensure_ready()
        with self._state_lock:
            latest = self._latest_trade_date
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else (
                datetime.strptime(latest[:10], '%Y-%m-%d').date() if latest else datetime.now().date()
            )
        except ValueError as e:
            raise ValueError("end_date 格式必须为 YYYY-MM-DD") from e
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else (
                end - timedelta(days=HISTORY_DEFAULT_DAYS)
            )
        except ValueError as e:
            raise ValueError("start_date 格式必须为 YYYY-MM-DD") from e
        if start > end:
            raise ValueError("start_date 不能晚于 end_date")
        if (end - start).days > HISTORY_MAX_DAYS:
            raise ValueError(f"日期区间超过上限 {HISTORY_MAX_DAYS} 天，请缩小范围")

        # --- 流式查询（行数上限内存保护） ---
        sql = f"""
            SELECT code, stock_name, trade_date, {', '.join(field_list)}
            FROM stock_daily_snapshot
            WHERE code = ANY(%(codes)s)
              AND trade_date BETWEEN %(start)s AND %(end)s
              {"AND market = %(market)s" if mkt else ""}
            ORDER BY code, trade_date
        """
        params: Dict[str, Any] = {
            'codes': code_list,
            'start': start,
            'end': end,
        }
        if mkt:
            params['market'] = mkt

        stocks_by_code: Dict[str, SnapshotHistoryStock] = {}
        trade_dates_set = set()
        total_rows = 0

        conn = self._pool.getconn()
        try:
            with conn.cursor(name="snapshot_history_cursor") as cur:
                cur.execute(sql, params)
                while True:
                    batch = cur.fetchmany(HISTORY_FETCH_BATCH)
                    if not batch:
                        break
                    for row in batch:
                        total_rows += 1
                        if total_rows > HISTORY_MAX_ROWS:
                            raise ValueError(
                                f"返回行数超过上限 {HISTORY_MAX_ROWS}，"
                                "请缩小日期区间、减少股票数量或用 fields 裁剪后分批请求"
                            )
                        code = row[0]
                        stock = stocks_by_code.get(code)
                        if stock is None:
                            stock = SnapshotHistoryStock(code=code, name=row[1] or '')
                            stocks_by_code[code] = stock
                        row_dict = {'trade_date': row[2].strftime('%Y-%m-%d')}
                        trade_dates_set.add(row_dict['trade_date'])
                        row_dict.update(
                            (f, self._coerce_history_value(v)) for f, v in zip(field_list, row[3:])
                        )
                        stock.rows.append(row_dict)
                    gc.collect()
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"历史快照查询失败: {e}") from e
        finally:
            self._pool.putconn(conn)

        return SnapshotHistoryData(
            market=mkt,
            start_date=start.strftime('%Y-%m-%d'),
            end_date=end.strftime('%Y-%m-%d'),
            fields=field_list,
            total_codes=len(stocks_by_code),
            trade_dates=sorted(trade_dates_set),
            stocks=list(stocks_by_code.values()),
        )

    def wait_ready(self, timeout: float = 600) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            with self._state_lock:
                if self._ready:
                    return True
            time.sleep(1)
        return False

    def get_status(self) -> dict:
        """获取详细状态（供运维监控）"""
        with self._state_lock:
            return {
                "ready": self._ready,
                "loading": self._loading,
                "load_error": str(self._load_error) if self._load_error else None,
                "latest_trade_date": self._latest_trade_date,
                "stocks_count": len(self._snapshot_cache),
                "ohlcv_stocks_count": len(self._ohlcv_cache),
                "load_time": self._load_time,
                "progress": self._load_progress,
                "total_bars": self._load_total,
            }
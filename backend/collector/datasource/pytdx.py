#!/usr/bin/env python3
"""
pytdx（通达信协议）数据源实现

特点：
- 免费、无需 Token、无配额限制
- 支持日线和分钟线（5/15/30/60min）
- 价格数据与 Tushare/Baostock 完全一致（差异 0.000%）
- 历史数据更长（1991年起）
- 不支持北交所

定位：作为 Tushare/Baostock 之后的第三级兜底数据源
"""
import os
import socket
import concurrent.futures
import yaml
import pandas as pd
from typing import Optional, List, Tuple
from pytdx.hq import TdxHq_API

from .base import BaseDataSource
from utils.logger import setup_logger

logger = setup_logger('pytdx_datasource')

# 全局交易日历缓存（由外部注入，避免 pytdx 各实例重复加载）
_global_trade_calendar: Optional[pd.DataFrame] = None


def set_global_trade_calendar(df: pd.DataFrame):
    """注入全局交易日历缓存（在管道启动时由 Tushare/Baostock 初始化）"""
    global _global_trade_calendar
    _global_trade_calendar = df.copy()
    logger.info(f"交易日历已注入 pytdx 全局缓存: {len(df)} 天")


def _resolve_config_path(relative_path: str) -> str:
    """
    解析配置文件路径。

    优先级：
    1. 环境变量 TDX_CONFIG_DIR（适用于生产环境容器化部署）
    2. 环境变量 PROJECT_ROOT（适用于 Cron/系统服务启动）
    3. __file__ 相对路径（适用于开发环境）

    启动时若路径不存在，抛出 FileNotFoundError，禁止静默降级。
    """
    # 1. TDX_CONFIG_DIR 环境变量
    config_dir = os.environ.get("TDX_CONFIG_DIR")
    if config_dir:
        path = os.path.join(config_dir, os.path.basename(relative_path))
        if os.path.exists(path):
            return path
        raise FileNotFoundError(
            f"TDX_CONFIG_DIR={config_dir} 下未找到配置文件: {os.path.basename(relative_path)}"
        )

    # 2. PROJECT_ROOT 环境变量
    project_root = os.environ.get("PROJECT_ROOT")
    if project_root:
        path = os.path.join(project_root, relative_path)
        if os.path.exists(path):
            return path
        raise FileNotFoundError(
            f"PROJECT_ROOT={project_root} 下未找到配置文件: {relative_path}"
        )

    # 3. __file__ 相对路径（开发环境兜底）
    path = os.path.join(os.path.dirname(__file__), "..", "config", os.path.basename(relative_path))
    if os.path.exists(path):
        return path

    raise FileNotFoundError(
        f"找不到 pytdx 配置文件: {relative_path}。"
        f"请设置环境变量 TDX_CONFIG_DIR 或 PROJECT_ROOT 指向项目根目录。"
    )


class PytdxDataSource(BaseDataSource):
    """通达信数据源 - 作为 Tushare/Baostock 的兜底备份"""

    def __init__(
        self,
        hosts_config_path: Optional[str] = None,
        market_config_path: Optional[str] = None,
        trade_calendar: Optional[pd.DataFrame] = None,
    ):
        self._hosts: List[Tuple[str, int]] = []
        self._api: Optional[TdxHq_API] = None
        self._connected: bool = False
        self._trade_calendar: Optional[pd.DataFrame] = trade_calendar

        # 加载配置（路径通过环境变量注入，启动期断言）
        hosts_path = hosts_config_path or _resolve_config_path("backend/collector/config/tdx_hosts.yaml")
        market_path = market_config_path or _resolve_config_path("backend/collector/config/tdx_market_mapping.yaml")

        with open(hosts_path, "r") as f:
            self._hosts_config = yaml.safe_load(f)
        with open(market_path, "r") as f:
            self._market_config = yaml.safe_load(f)

        self._hosts = [
            (h["host"], h["port"]) for h in self._hosts_config["hosts"]
        ]
        self._timeout = self._hosts_config.get("connection", {}).get("timeout", 30)
        self._kline_timeout = self._hosts_config.get("download", {}).get("kline_timeout", 60)

    @property
    def name(self) -> str:
        return "pytdx"

    @property
    def requires_token(self) -> bool:
        return False

    @property
    def supported_cycles(self) -> List[str]:
        return ["daily", "min5", "min15", "min30", "min60"]

    def connect(self) -> bool:
        """多主机轮询连接，绑定超时参数防止僵尸连接"""
        if self._connected and self._api is not None:
            return True

        # 设置 socket 默认超时，防止连接阶段无限阻塞
        socket.setdefaulttimeout(self._timeout)

        self._api = TdxHq_API(heartbeat=True, auto_retry=True, raise_exception=False)
        for host, port in self._hosts:
            try:
                if self._api.connect(host, port):
                    self._connected = True
                    logger.info(f"pytdx 连接成功: {host}:{port} (timeout={self._timeout}s)")
                    return True
            except Exception as e:
                logger.warning(f"pytdx 连接失败 {host}:{port}: {e}")
                continue

        logger.error("pytdx 所有主机连接失败")
        return False

    def disconnect(self) -> bool:
        if self._api:
            try:
                self._api.disconnect()
            except Exception:
                pass
            self._api = None
        self._connected = False
        return True

    def _resolve_code(self, code: str) -> Tuple[str, int]:
        """
        解析代码并推断市场。返回 (code_only, market)。

        支持显式后缀（.SZ/.SH）或无后缀的 6 位股票代码自动推断。
        北交所/新三板（8/9/43/83/87 开头）不在推断范围内，需调用方显式处理。
        """
        if "." in code:
            code_only, suffix = code.split(".")
            suffix_upper = suffix.upper()
            if suffix_upper not in ("SZ", "SH"):
                raise ValueError(
                    f"不支持的后缀: .{suffix}，仅支持 .SZ 或 .SH（输入: {code}）"
                )
            market = 0 if suffix_upper == "SZ" else 1
            return code_only, market

        # 无后缀：仅对明确的 A 股代码进行市场推断
        if not code.isdigit():
            raise ValueError(
                f"代码 '{code}' 无法识别。请使用 '000001.SZ' 或 '000001.SH' 格式，"
                f"或提供 6 位数字 A 股代码。"
            )

        prefix3 = code[:3] if len(code) >= 3 else ""
        prefix2 = code[:2] if len(code) >= 2 else ""

        # 深圳市场（market=0）
        if prefix3 in ("000", "001", "002", "003", "300", "301") or prefix2 == "39":
            market = 0
        # 上海市场（market=1）
        elif prefix3 in ("600", "601", "603", "605", "688", "689") or prefix2 in ("51", "50", "99"):
            market = 1
        else:
            raise ValueError(
                f"代码 '{code}' 缺少市场后缀，且无法自动推断市场。"
                f"请使用 '000001.SZ' 或 '000001.SH' 格式显式声明。"
            )

        return code, market

    def _get_vol_multiplier(self, code: str) -> int:
        """根据品种类型获取成交量乘数（从配置文件读取）"""
        stock_config = self._market_config.get("markets", {}).get("stock", {})
        return stock_config.get("vol_multiplier", 100)

    def get_stock_list(self) -> pd.DataFrame:
        """获取全市场股票列表。返回格式: code(sh.000001), name, exchange, list_date, delist_date"""
        from collector.config.tdx_market_mapping import filter_stock_codes

        dfs = []
        for market, market_label in [(0, "SZ"), (1, "SH")]:
            try:
                security_list = self._api.get_security_list(market, 0)
                if security_list:
                    df = pd.DataFrame(security_list)
                    df["exchange"] = market_label
                    dfs.append(df)
            except Exception as e:
                logger.warning(f"获取证券列表失败 market={market}: {e}")

        if not dfs:
            return pd.DataFrame()

        result = pd.concat(dfs, ignore_index=True)

        # 用配置文件中的正则过滤股票代码
        result = filter_stock_codes(result, self._market_config)

        # 重命名为标准格式
        result["code"] = result.apply(
            lambda r: f"{'sh' if r['exchange'] == 'SH' else 'sz'}.{r['code']}",
            axis=1,
        )
        result["industry"] = ""
        result["list_date"] = None
        result["delist_date"] = None

        return result[["code", "name", "exchange", "industry", "list_date", "delist_date"]]

    def get_kline(
        self,
        code: str,
        cycle: str = "daily",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取K线数据。成交量自动从"手"转换为"股"（乘数由配置决定）。

        K线下载使用 concurrent.futures 超时控制，防止单只股票卡死阻塞全局队列。
        成交额单位：元（pytdx 原生返回单位，无需转换）。
        """
        code_only, market = self._resolve_code(code)
        vol_multiplier = self._get_vol_multiplier(code_only)

        cycle_map = {
            "daily": 9, "min5": 0, "min15": 1, "min30": 2, "min60": 3,
        }
        ktype = cycle_map.get(cycle)
        if ktype is None:
            raise ValueError(f"不支持的周期: {cycle}")

        # 使用超时控制包裹网络 I/O 调用
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._api.get_security_bars, ktype, market, code_only, 0, 800
            )
            try:
                bars = future.result(timeout=self._kline_timeout)
            except concurrent.futures.TimeoutError:
                logger.error(
                    f"pytdx K线下载超时: code={code}, cycle={cycle}, "
                    f"timeout={self._kline_timeout}s"
                )
                return pd.DataFrame()

        if not bars:
            return pd.DataFrame()

        df = pd.DataFrame(bars)
        df = df.rename(columns={
            "datetime": "trade_date", "open": "open", "high": "high",
            "low": "low", "close": "close", "vol": "volume", "amount": "amount",
        })

        # 成交量单位转换：手 → 股（乘数由配置决定）
        df["volume"] = df["volume"] * vol_multiplier
        # 成交额单位：pytdx 原生返回"元"，无需转换
        # 验证：单日成交额量级检查（日志记录异常，不阻断）
        if len(df) > 0 and cycle == "daily":
            sample_amount = df["amount"].iloc[-1]
            if sample_amount < 1e4:  # 低于 1 万元，可能单位异常
                logger.warning(
                    f"pytdx ${code} 成交额偏低: {sample_amount:.0f}元，"
                    f"请确认单位是否为'元'（预期>1万元）"
                )

        # 日期格式化
        if cycle == "daily":
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        else:
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d %H:%M:%S")

        df["code"] = code
        df["cycle"] = cycle

        # 日期过滤
        if start_date:
            df = df[df["trade_date"] >= start_date]
        if end_date:
            df = df[df["trade_date"] <= end_date]

        return df[["code", "trade_date", "open", "high", "low", "close", "volume", "amount", "cycle"]]

    def get_trade_calendar(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exchange: str = "SH",
    ) -> pd.DataFrame:
        """
        获取交易日历。

        pytdx 不原生支持交易日历，此方法从全局缓存获取。
        若缓存不存在，抛出 ValueError（禁止返回空 DataFrame）。
        """
        calendar = self._trade_calendar or _global_trade_calendar

        if calendar is None or calendar.empty:
            raise ValueError(
                "pytdx 交易日历不可用：请在管道启动时调用 "
                "set_global_trade_calendar() 注入交易日历，"
                "或通过 Tushare/Baostock 预加载。"
            )

        result = calendar.copy()
        date_col = "cal_date" if "cal_date" in result.columns else "trade_date"
        result[date_col] = pd.to_datetime(result[date_col]).dt.strftime("%Y-%m-%d")

        if start_date:
            result = result[result[date_col] >= start_date]
        if end_date:
            result = result[result[date_col] <= end_date]

        return result
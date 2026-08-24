"""
集中式错误码表 - 全后端统一错误码规范

错误码格式: 5 位数字
- 400xx: 业务/参数校验错误（HTTP 400）
- 404xx: 资源不存在（HTTP 404）
- 500xx: 系统/数据库/数据源错误（HTTP 500）

每个错误码包含: code / message / category / source
- category: 错误分类（业务/校验/不存在/数据源/数据库/网络/内部）
- source:   数据来源标识（local/postgresql/baostock/tushare/akshare/pytdx），
            日志中写清楚数据源，便于定位"用了哪个数据源"。

使用示例:
    from shared.error_codes import PDCAError
    raise HTTPException(status_code=404, detail=PDCAError.RECORD_NOT_FOUND.detail())
    logger.error(PDCAError.RECORD_NOT_FOUND.log_msg(detail="id=123"))
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorCategory(str, Enum):
    """错误分类"""
    VALIDATION = "validation"        # 参数/数据校验
    BUSINESS = "business"            # 业务规则
    NOT_FOUND = "not_found"          # 资源不存在
    DATA_SOURCE = "data_source"      # 数据源错误
    DATABASE = "database"            # 数据库错误
    NETWORK = "network"              # 网络错误
    INTERNAL = "internal"            # 内部错误


class DataSource(str, Enum):
    """数据源标识"""
    LOCAL = "local"
    POSTGRESQL = "postgresql"
    BAOSTOCK = "baostock"
    TUSHARE = "tushare"
    AKSHARE = "akshare"
    PYTDX = "pytdx"


@dataclass(frozen=True)
class ErrorCode:
    """错误码定义"""
    code: str
    message: str
    category: ErrorCategory = ErrorCategory.INTERNAL
    source: DataSource = DataSource.LOCAL

    def detail(self, detail: str = "") -> str:
        """生成 API 响应 detail（保持 'CODE: message' 兼容前端展示）"""
        msg = f"{self.code}: {self.message}"
        if detail:
            msg += f" | {detail}"
        return msg

    def log_msg(self, detail: str = "", source: Optional[DataSource] = None) -> str:
        """生成日志消息（含分类与数据源标识，便于排查）"""
        src = (source or self.source).value
        msg = f"[{self.category.value}/{src}] {self.code}: {self.message}"
        if detail:
            msg += f" | {detail}"
        return msg


# ============================================================
# 通用系统错误 (500xx)
# ============================================================
class CommonError:
    INTERNAL = ErrorCode("50000", "服务器内部错误", ErrorCategory.INTERNAL)
    DB_CONNECTION = ErrorCode("50001", "数据库连接失败", ErrorCategory.DATABASE, DataSource.POSTGRESQL)
    DB_QUERY = ErrorCode("50002", "数据库查询失败", ErrorCategory.DATABASE, DataSource.POSTGRESQL)
    SOURCE_UNAVAILABLE = ErrorCode("50010", "数据源不可用", ErrorCategory.DATA_SOURCE)
    SOURCE_TIMEOUT = ErrorCode("50011", "数据源请求超时", ErrorCategory.NETWORK)
    NETWORK_ERROR = ErrorCode("50012", "网络请求失败", ErrorCategory.NETWORK)


# ============================================================
# PDCA 业务错误 (400xx / 404xx)
# 说明: 部分码沿用历史（如 40011 覆盖记录/日记/配置等不存在场景），
#       message 区分具体含义，前端仅展示 message 不解析码值，保持兼容。
# ============================================================
class PDCAError:
    IMPORT_EMPTY = ErrorCode("40003", "导入数据为空", ErrorCategory.VALIDATION)
    ENTRY_PRICE_POSITIVE = ErrorCode("40004", "入场价必须大于0", ErrorCategory.VALIDATION)
    ENTRY_EXIT_DATE = ErrorCode("40008", "出场日期不能早于进场日期", ErrorCategory.VALIDATION)
    BROKER_NOT_SUPPORTED = ErrorCode("40009", "不支持的券商格式，请先配置适配器", ErrorCategory.BUSINESS)
    EXCEL_PARSE_FAILED = ErrorCode("40009", "无法解析 Excel 文件", ErrorCategory.VALIDATION)
    EXCEL_EMPTY = ErrorCode("40009", "Excel 文件为空", ErrorCategory.VALIDATION)
    FILE_FORMAT_UNSUPPORTED = ErrorCode("40010", "仅支持 jpg/png/gif 格式", ErrorCategory.VALIDATION)
    FILE_TOO_LARGE = ErrorCode("40010", "文件大小不能超过 10MB", ErrorCategory.VALIDATION)
    RECORD_NOT_FOUND = ErrorCode("40011", "交易记录不存在", ErrorCategory.NOT_FOUND)
    RECORD_DELETED = ErrorCode("40011", "交易记录已被删除", ErrorCategory.BUSINESS)
    DIARY_NOT_FOUND = ErrorCode("40011", "交易日记不存在", ErrorCategory.NOT_FOUND)
    DIARY_DELETED = ErrorCode("40011", "交易日记已被删除", ErrorCategory.BUSINESS)
    CONFIG_NOT_FOUND = ErrorCode("40011", "配置项不存在", ErrorCategory.NOT_FOUND)
    SLIP_NOT_FOUND = ErrorCode("40011", "卖出子单不存在", ErrorCategory.NOT_FOUND)
    REPORT_NOT_FOUND = ErrorCode("40011", "复盘报告不存在", ErrorCategory.NOT_FOUND)
    NO_ACTIVE_CYCLE = ErrorCode("40012", "没有活跃的 PDCA 周期，请先创建周期", ErrorCategory.BUSINESS)
    SNAPSHOT_EXISTS = ErrorCode("40012", "该日期已存在资金快照", ErrorCategory.BUSINESS)
    RECORD_EXISTS = ErrorCode("40012", "该日期已存在资金记录", ErrorCategory.BUSINESS)
    NO_UPDATE_FIELDS = ErrorCode("40013", "无更新字段", ErrorCategory.VALIDATION)
    SELL_QTY_EXCEEDED = ErrorCode("40014", "卖出数量超过剩余持仓", ErrorCategory.VALIDATION)
    CYCLE_NOT_FOUND = ErrorCode("40015", "周期不存在", ErrorCategory.NOT_FOUND)
    ACT_RECORD_NOT_FOUND = ErrorCode("40016", "迭代处理记录不存在", ErrorCategory.NOT_FOUND)
    FUND_RECORD_NOT_FOUND = ErrorCode("40401", "资金记录不存在", ErrorCategory.NOT_FOUND)

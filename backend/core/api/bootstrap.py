"""
bootstrap.py - 应用首启多用户账号 bootstrap

职责：
1. 依据 .env 的 API_ADMIN_USERNAME/PASSWORD 幂等创建初始管理员（无则跳过）。
2. 将老自选股 `user_id='default'` 迁移归入首个 admin（唯一执行点，用
   migration_flags 标记仅执行一次；目标 admin 不存在时跳过，防误迁移）。

约束（方案 §6）：
- 在应用启动 lifespan 中调用；迁移不在 V014 SQL 里做（admin 用户名来自运行时配置）。
- 幂等：二次启动无 default 数据则 UPDATE 0 rows 无害；执行一次由 migration_flags 守护。
"""

import logging

from sqlalchemy import text as sa_text
from sqlalchemy.exc import SQLAlchemyError

from core.api.config import settings
from core.api.passwords import hash_password
from collector.db.database import get_db_session

logger = logging.getLogger(__name__)

_MIGRATION_FLAG = "watchlist_default_to_admin"


def bootstrap_auth() -> None:
    """应用首启执行：建初始 admin + 迁移老自选股归属。失败仅记日志，不阻塞启动。"""
    try:
        _create_initial_admin()
        _migrate_default_watchlist()
    except SQLAlchemyError as exc:
        logger.error("[bootstrap] 账号初始化失败（不影响服务继续启动）：%s", exc)


def _create_initial_admin() -> None:
    """依据配置幂等创建初始管理员。"""
    username = settings.admin_username.strip()
    password = settings.admin_password.strip()
    if not username or not password:
        logger.warning("[bootstrap] API_ADMIN_USERNAME/PASSWORD 未配置，跳过初始管理员创建")
        return
    with get_db_session() as db:
        db.execute(
            sa_text(
                "INSERT INTO users (username, password_hash, display_name, role, is_active) "
                "VALUES (:username, :password_hash, :display_name, 'admin', TRUE) "
                "ON CONFLICT (username) DO NOTHING"
            ),
            {
                "username": username,
                "password_hash": hash_password(password),
                "display_name": username,
            },
        )
        db.commit()
    logger.info("[bootstrap] 初始管理员已就绪（存在则不重复创建）：%s", username)


def _migrate_default_watchlist() -> None:
    """将老自选股 user_id='default' 迁入首个 admin（带迁移标记，仅执行一次）。"""
    username = settings.admin_username.strip()
    if not username:
        logger.warning("[bootstrap] 未配置 admin 用户名，跳过老自选股迁移")
        return
    with get_db_session() as db:
        flag = db.execute(
            sa_text("SELECT 1 FROM migration_flags WHERE flag_name = :flag"),
            {"flag": _MIGRATION_FLAG},
        ).fetchone()
        if flag:
            return
        db.execute(
            sa_text(
                "UPDATE user_watchlist SET user_id = :admin "
                "WHERE user_id = 'default' "
                "AND NOT EXISTS (SELECT 1 FROM migration_flags WHERE flag_name = :flag) "
                "AND EXISTS (SELECT 1 FROM users WHERE username = :admin)"
            ),
            {"admin": username, "flag": _MIGRATION_FLAG},
        )
        db.execute(
            sa_text("INSERT INTO migration_flags (flag_name) VALUES (:flag) ON CONFLICT DO NOTHING"),
            {"flag": _MIGRATION_FLAG},
        )
        db.commit()
    logger.info("[bootstrap] 老自选股 user_id='default' 已归入 admin，迁移标记已写：%s", _MIGRATION_FLAG)
"""
database.py - PostgreSQL 数据库连接管理模块

提供数据库连接池和会话管理，支持从环境变量读取配置。
"""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 数据库配置（从环境变量读取）
DB_HOST = os.getenv("PG_HOST", "localhost")
DB_PORT = os.getenv("PG_PORT", "5432")
DB_NAME = os.getenv("PG_DATABASE", "quant_trading")
DB_USER = os.getenv("PG_USER", "quant_user")
DB_PASSWORD = os.getenv("PG_PASSWORD", "")

# 构建数据库连接 URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 创建引擎（带连接池）
engine = create_engine(
    DATABASE_URL,
    pool_size=10,           # 连接池大小
    max_overflow=20,        # 最大溢出连接数
    pool_pre_ping=True,     # 连接前检查有效性
    echo=False              # 是否打印 SQL 日志（调试时可设为 True）
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    获取数据库会话的上下文管理器
    
    使用示例:
        with get_db_session() as db:
            result = db.execute(text("SELECT * FROM stock_basic LIMIT 10"))
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_connection() -> bool:
    """
    测试数据库连接是否正常
    
    Returns:
        bool: 连接成功返回 True，失败返回 False
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False


def get_table_names() -> list:
    """
    获取数据库中所有表名
    
    Returns:
        list: 表名列表
    """
    try:
        with get_db_session() as db:
            result = db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            return [row[0] for row in result.fetchall()]
    except Exception as e:
        print(f"❌ 获取表名失败: {e}")
        return []


if __name__ == "__main__":
    # 测试连接
    print("🔍 测试数据库连接...")
    if test_connection():
        print("✅ 数据库连接成功！")
        print(f"📊 数据库: {DB_NAME}")
        print(f"🏠 主机: {DB_HOST}:{DB_PORT}")
        
        # 显示所有表
        tables = get_table_names()
        print(f"\n📋 数据库中的表 ({len(tables)} 个):")
        for table in tables:
            print(f"   - {table}")
    else:
        print("❌ 无法连接到数据库，请检查配置")

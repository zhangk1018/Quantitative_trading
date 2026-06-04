"""
存储工厂
根据配置创建对应的存储实例
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class StorageFactory:
    """存储工厂类"""

    @staticmethod
    def create_storage(config: Dict[str, Any]) -> 'BaseStorage':
        """根据配置创建存储实例"""
        db_type = config.get('type', 'sqlite').lower()
        
        if db_type == 'postgresql':
            return StorageFactory._create_postgresql_storage(config)
        elif db_type == 'sqlite':
            return StorageFactory._create_sqlite_storage(config)
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

    @staticmethod
    def _create_postgresql_storage(config: Dict[str, Any]) -> 'PostgreSQLStorage':
        """创建 PostgreSQL 存储实例"""
        from collector.storage.postgresql_storage import PostgreSQLStorage
        
        pg_config = config.get('postgresql', {})
        logger.info("📦 创建 PostgreSQL 存储实例")
        
        return PostgreSQLStorage({
            'host': pg_config.get('host', 'localhost'),
            'port': pg_config.get('port', 5432),
            'database': pg_config.get('database', 'quant_trading'),
            'username': pg_config.get('username', 'quant_user'),
            'password': pg_config.get('password', 'quant_password')
        })

    @staticmethod
    def _create_sqlite_storage(config: Dict[str, Any]) -> 'SQLiteStorage':
        """创建 SQLite 存储实例"""
        from collector.storage.sqlite_storage import SQLiteStorage
        
        sqlite_config = config.get('sqlite', {})
        logger.info("📦 创建 SQLite 存储实例")
        
        return SQLiteStorage({
            'path': sqlite_config.get('path', 'data/quantitative_trading.db')
        })
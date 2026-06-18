"""调用完整函数看返回 0 的原因"""
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

from collector.storage.postgresql_storage import PostgreSQLStorage
from clean.etl.compute_indicators_daily import compute_indicators_for_stock
from utils.config import config
from utils.logger import setup_logger
import logging

# 强制输出所有 DEBUG 日志
logger = setup_logger('test')
logging.getLogger().setLevel(logging.DEBUG)

db_config = config.get('database', {})
storage = PostgreSQLStorage({
    'host': db_config.get('host', 'localhost'),
    'port': db_config.get('port', 5432),
    'database': db_config.get('database', 'quant_trading'),
    'username': db_config.get('username', 'quant_user'),
    'password': db_config.get('password', ''),
})
storage.connect()

count = compute_indicators_for_stock(storage, '000011')
print(f"\n返回: {count}")

storage.disconnect()

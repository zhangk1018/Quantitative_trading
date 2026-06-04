#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

storage_config = config.storage.get('postgresql', {})
storage = PostgreSQLStorage(storage_config)
storage.connect()

cursor = storage.conn.cursor()

partitions = [
    ('stock_quotes_2000', '2000-01-01', '2001-01-01'),
    ('stock_quotes_2001', '2001-01-01', '2002-01-01'),
    ('stock_quotes_2002', '2002-01-01', '2003-01-01'),
    ('stock_quotes_2003', '2003-01-01', '2004-01-01'),
    ('stock_quotes_2004', '2004-01-01', '2005-01-01'),
    ('stock_quotes_2005', '2005-01-01', '2006-01-01'),
    ('stock_quotes_2006', '2006-01-01', '2007-01-01'),
    ('stock_quotes_2007', '2007-01-01', '2008-01-01'),
    ('stock_quotes_2008', '2008-01-01', '2009-01-01'),
    ('stock_quotes_2009', '2009-01-01', '2010-01-01'),
    ('stock_quotes_2010', '2010-01-01', '2011-01-01'),
    ('stock_quotes_2011', '2011-01-01', '2012-01-01'),
    ('stock_quotes_2012', '2012-01-01', '2013-01-01'),
    ('stock_quotes_2013', '2013-01-01', '2014-01-01'),
    ('stock_quotes_2014', '2014-01-01', '2015-01-01'),
]

for table_name, start_date, end_date in partitions:
    try:
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} PARTITION OF stock_quotes FOR VALUES FROM ('{start_date}') TO ('{end_date}')"
        cursor.execute(sql)
        print(f'✅ 创建分区 {table_name}')
    except Exception as e:
        print(f'❌ 创建分区 {table_name} 失败: {e}')

storage.conn.commit()
print('\n分区创建完成！')
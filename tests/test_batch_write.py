#!/usr/bin/env python3
"""数据库批量写入单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


class TestBatchWriteToDb:
    """批量写入数据库测试类"""
    
    def test_empty_dataframe(self):
        """测试空DataFrame写入"""
        from base_importer import BaseDataImporter
        
        class TestImporter(BaseDataImporter):
            def import_stock_data(self, code, start_date, end_date):
                pass
        
        importer = TestImporter()
        importer._storage = MagicMock()
        
        df = pd.DataFrame()
        result = importer.batch_write_to_db(df, 'test_table', ['col1'], ['col1'])
        
        assert result == 0, "空DataFrame应返回0"
    
    def test_single_row_write(self):
        """测试单行数据写入 - 使用patch模拟execute_values"""
        from base_importer import BaseDataImporter
        
        class TestImporter(BaseDataImporter):
            def import_stock_data(self, code, start_date, end_date):
                pass
        
        importer = TestImporter()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        importer._storage = MagicMock()
        importer._storage.conn = mock_conn
        
        df = pd.DataFrame({
            'code': ['000001'],
            'cycle': ['1d'],
            'trade_date': [datetime.now().date()],
            'trade_time': [datetime.now()],
            'close': [100.0]
        })
        
        with patch('base_importer.execute_values') as mock_execute_values:
            result = importer.batch_write_to_db(
                df,
                'test_table',
                ['code', 'cycle', 'trade_date', 'trade_time', 'close'],
                ['close']
            )
        
        assert result == 1, "应写入1条记录"
        mock_execute_values.assert_called_once()
    
    def test_large_batch_write(self):
        """测试大批量数据写入（超过max_batch_size）"""
        from base_importer import BaseDataImporter
        
        class TestImporter(BaseDataImporter):
            def import_stock_data(self, code, start_date, end_date):
                pass
        
        importer = TestImporter()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        importer._storage = MagicMock()
        importer._storage.conn = mock_conn
        
        dates = [datetime.now() - timedelta(days=i) for i in range(6000)]
        df = pd.DataFrame({
            'code': ['000001'] * 6000,
            'cycle': ['1d'] * 6000,
            'trade_date': [d.date() for d in dates],
            'trade_time': dates,
            'close': np.random.rand(6000) * 100
        })
        
        with patch('base_importer.execute_values') as mock_execute_values:
            result = importer.batch_write_to_db(
                df,
                'test_table',
                ['code', 'cycle', 'trade_date', 'trade_time', 'close'],
                ['close'],
                max_batch_size=5000
            )
        
        assert result == 6000, "应写入6000条记录"
        assert mock_execute_values.call_count == 2, "应分两批写入"
    
    def test_data_cleaning(self):
        """测试数据清洗（NaN/Inf处理）"""
        from base_importer import BaseDataImporter
        
        class TestImporter(BaseDataImporter):
            def import_stock_data(self, code, start_date, end_date):
                pass
        
        importer = TestImporter()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        importer._storage = MagicMock()
        importer._storage.conn = mock_conn
        
        df = pd.DataFrame({
            'code': ['000001', '000002', '000003'],
            'cycle': ['1d', '1d', '1d'],
            'trade_date': [datetime.now().date()] * 3,
            'trade_time': [datetime.now()] * 3,
            'close': [100.0, np.nan, np.inf]
        })
        
        with patch('base_importer.execute_values') as mock_execute_values:
            result = importer.batch_write_to_db(
                df,
                'test_table',
                ['code', 'cycle', 'trade_date', 'trade_time', 'close'],
                ['close']
            )
        
        assert result == 3, "应写入3条记录"
        
        # 验证参数中NaN和Inf被转换为None
        call_args = mock_execute_values.call_args
        values = call_args[0][2]  # 获取第三个参数（values）
        assert values[0][4] == 100.0, "正常值应保持不变"
        assert values[1][4] is None, "NaN应转换为None"
        assert values[2][4] is None, "Inf应转换为None"
    
    def test_insert_conflict_update(self):
        """测试INSERT ON CONFLICT UPDATE逻辑"""
        from base_importer import BaseDataImporter
        
        class TestImporter(BaseDataImporter):
            def import_stock_data(self, code, start_date, end_date):
                pass
        
        importer = TestImporter()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        importer._storage = MagicMock()
        importer._storage.conn = mock_conn
        
        df = pd.DataFrame({
            'code': ['000001'],
            'cycle': ['1d'],
            'trade_date': [datetime.now().date()],
            'trade_time': [datetime.now()],
            'close': [100.0],
            'volume': [1000]
        })
        
        with patch('base_importer.execute_values') as mock_execute_values:
            importer.batch_write_to_db(
                df,
                'test_table',
                ['code', 'cycle', 'trade_date', 'trade_time', 'close', 'volume'],
                ['close', 'volume']
            )
        
        # 获取执行的SQL
        call_args = mock_execute_values.call_args
        sql = call_args[0][1]  # 获取第二个参数（sql）
        
        assert 'ON CONFLICT' in sql, "SQL应包含ON CONFLICT"
        assert 'DO UPDATE SET' in sql, "SQL应包含DO UPDATE SET"
        assert 'close = EXCLUDED.close' in sql, "应更新close列"
        assert 'volume = EXCLUDED.volume' in sql, "应更新volume列"
    
    def test_error_handling(self):
        """测试错误处理和回滚"""
        from base_importer import BaseDataImporter
        
        class TestImporter(BaseDataImporter):
            def import_stock_data(self, code, start_date, end_date):
                pass
        
        importer = TestImporter()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        importer._storage = MagicMock()
        importer._storage.conn = mock_conn
        
        df = pd.DataFrame({
            'code': ['000001'],
            'cycle': ['1d'],
            'trade_date': [datetime.now().date()],
            'trade_time': [datetime.now()],
            'close': [100.0]
        })
        
        with patch('base_importer.execute_values') as mock_execute_values:
            mock_execute_values.side_effect = Exception("数据库错误")
            result = importer.batch_write_to_db(
                df,
                'test_table',
                ['code', 'cycle', 'trade_date', 'trade_time', 'close'],
                ['close']
            )
        
        assert result == 0, "写入失败应返回0"
        mock_conn.rollback.assert_called_once(), "应调用回滚"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
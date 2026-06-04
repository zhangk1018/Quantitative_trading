#!/usr/bin/env python3
"""SQLite存储模块 - 支持断点续传和冷热数据分离"""
import os
import sqlite3
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, List
from utils.logger import setup_logger
from utils.config import config

from .base_storage import BaseStorage

logger = setup_logger('sqlite_storage')


class SQLiteStorage(BaseStorage):
    """SQLite数据存储类 - 支持冷热数据分离"""
    
    # 热数据年限（年），超过此年限的数据视为冷数据
    HOT_DATA_YEARS = config.storage.get('hot_data_years', 3)
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.storage.get('db_path', 'data/stock_data.db')
        self.conn = None
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def connect(self):
        """连接数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self._create_tables()
            logger.info(f"✅ 数据库连接成功: {self.db_path}")
            return True
        except Exception as e:
            logger.error(f"❌ 数据库连接失败: {str(e)}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.conn:
            self.conn.close()
            logger.info("✅ 数据库已断开")
    
    def _create_tables(self):
        """创建表结构"""
        cursor = self.conn.cursor()
        
        # 股票基本信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_basic (
                code TEXT PRIMARY KEY,
                name TEXT,
                exchange TEXT,
                industry TEXT,
                list_date TEXT,
                delist_date TEXT
            )
        ''')
        
        # 行情数据主表（热数据）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_quotes (
                code TEXT,
                trade_date TEXT,
                cycle TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                amount REAL,
                adjust_type TEXT,       -- qfq(前复权), hfq(后复权), None(不复权)
                adjust_factor REAL,     -- 复权因子
                adjust_version INTEGER, -- 复权版本号（防止前视偏差）
                effective_date TEXT,    -- 数据生效日期（防止前视偏差）
                PRIMARY KEY (code, trade_date, cycle, adjust_type)
            )
        ''')
        
        # 交易日历表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_calendar (
                cal_date TEXT PRIMARY KEY,
                is_open INTEGER,
                exchange TEXT
            )
        ''')
        
        # 任务状态表（用于断点续传）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_progress (
                task_id TEXT PRIMARY KEY,
                task_type TEXT,
                status TEXT,           -- pending, running, completed, failed
                total_count INTEGER,
                success_count INTEGER,
                fail_count INTEGER,
                current_index INTEGER,
                current_code TEXT,
                current_cycle TEXT,
                start_time TEXT,
                last_update_time TEXT,
                error_message TEXT,
                extra_data TEXT        -- JSON格式的额外数据
            )
        ''')
        
        # 标的生命周期映射表（管理代码变更、更名、ST、退市等）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS symbol_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                old_code TEXT,          -- 旧代码
                new_code TEXT,          -- 新代码
                event_type TEXT,        -- 事件类型: rename(更名), st(ST标记), delist(退市), merge(合并), split(分拆)
                event_date TEXT,        -- 事件发生日期
                effective_date TEXT,    -- 生效日期
                old_name TEXT,          -- 旧名称
                new_name TEXT,          -- 新名称
                is_active INTEGER,      -- 当前是否有效
                extra_info TEXT         -- 额外信息（JSON格式）
            )
        ''')
        
        # 历史股票池快照表（按日维护，解决幸存者偏差）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_universe_snapshot (
                snapshot_date TEXT,     -- 快照日期
                code TEXT,              -- 股票代码
                name TEXT,              -- 股票名称
                exchange TEXT,          -- 交易所
                industry TEXT,          -- 行业
                list_date TEXT,         -- 上市日期
                delist_date TEXT,       -- 退市日期（如果有）
                is_st INTEGER,          -- 是否ST（1=是，0=否）
                st_start_date TEXT,     -- ST起始日期
                is_active INTEGER,      -- 是否活跃（1=活跃，0=已退市）
                PRIMARY KEY (snapshot_date, code)
            )
        ''')
        
        # 技术指标表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_indicators (
                code TEXT,
                trade_date TEXT,
                cycle TEXT,
                MA5 REAL,
                MA10 REAL,
                MA20 REAL,
                MA60 REAL,
                MA120 REAL,
                MA250 REAL,
                MACD REAL,
                MACD_SIGNAL REAL,
                MACD_HIST REAL,
                KDJ_K REAL,
                KDJ_D REAL,
                KDJ_J REAL,
                BOLL_MID REAL,
                BOLL_UPPER REAL,
                BOLL_LOWER REAL,
                RSI REAL,
                ATR REAL,
                VOL_MA5 REAL,
                VOL_MA10 REAL,
                VOL_MA20 REAL,
                PRIMARY KEY (code, trade_date, cycle)
            )
        ''')
        
        # 财务报表原始数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_report (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,              -- 股票代码
                report_type TEXT,       -- 报表类型: annual(年报), semi(半年报), quarterly(季报)
                report_period TEXT,     -- 报告期（如2024Q4, 2024A）
                announcement_date TEXT, -- 公告日期（关键：PIT处理的核心字段）
                publish_time TEXT,      -- 发布时间（精确到时分）
                end_date TEXT,          -- 报告截止日期
                fiscal_year INTEGER,    -- 会计年度
                fiscal_quarter INTEGER, -- 会计季度
                total_assets REAL,      -- 总资产
                total_liabilities REAL, -- 总负债
                total_equity REAL,      -- 股东权益合计
                revenue REAL,           -- 营业收入
                operating_profit REAL,  -- 营业利润
                net_profit REAL,        -- 净利润
                eps REAL,               -- 每股收益
                bps REAL,               -- 每股净资产
                roe REAL,               -- 净资产收益率
                roa REAL,               -- 总资产收益率
                gross_margin REAL,      -- 毛利率
                operating_margin REAL,  -- 营业利润率
                cash_flow REAL,         -- 经营活动现金流
                extra_info TEXT         -- 额外信息（JSON格式）
            )
        ''')
        
        # Point-in-Time财务数据表（解决未来函数问题）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_pit (
                code TEXT,              -- 股票代码
                as_of_date TEXT,        -- 数据可用日期（交易日期）
                report_type TEXT,       -- 报表类型
                report_period TEXT,     -- 报告期
                announcement_date TEXT, -- 公告日期
                end_date TEXT,          -- 报告截止日期
                total_assets REAL,      -- 总资产（最新可用值）
                total_liabilities REAL, -- 总负债（最新可用值）
                total_equity REAL,      -- 股东权益合计（最新可用值）
                revenue REAL,           -- 营业收入（最新可用值）
                operating_profit REAL,  -- 营业利润（最新可用值）
                net_profit REAL,        -- 净利润（最新可用值）
                eps REAL,               -- 每股收益（最新可用值）
                bps REAL,               -- 每股净资产（最新可用值）
                roe REAL,               -- 净资产收益率（最新可用值）
                roa REAL,               -- 总资产收益率（最新可用值）
                gross_margin REAL,      -- 毛利率（最新可用值）
                operating_margin REAL,  -- 营业利润率（最新可用值）
                cash_flow REAL,         -- 经营活动现金流（最新可用值）
                PRIMARY KEY (code, as_of_date, report_type)
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotes_code_cycle ON stock_quotes (code, cycle)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotes_code_date ON stock_quotes (code, trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotes_cycle_date ON stock_quotes (cycle, trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_quotes_adjust_type ON stock_quotes (adjust_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_calendar_date ON trade_calendar (cal_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_status ON task_progress (status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_type ON task_progress (task_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_indicators_code_cycle ON stock_indicators (code, cycle)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_indicators_code_date ON stock_indicators (code, trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_old_code ON symbol_mapping (old_code)')
        
        # 财务数据索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_financial_code ON financial_report (code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_financial_period ON financial_report (report_period)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_financial_announcement ON financial_report (announcement_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_financial_pit_code_date ON financial_pit (code, as_of_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_financial_pit_report_type ON financial_pit (report_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_new_code ON symbol_mapping (new_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_event_date ON symbol_mapping (event_date)')
        
        # 股票池快照索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_universe_date ON stock_universe_snapshot (snapshot_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_universe_code ON stock_universe_snapshot (code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_universe_is_active ON stock_universe_snapshot (is_active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_universe_is_st ON stock_universe_snapshot (is_st)')
        
        self.conn.commit()
    
    def _get_table_name_by_year(self, year: int) -> str:
        """根据年份获取表名"""
        return f"stock_quotes_{year}"
    
    def _create_year_table(self, year: int):
        """创建年度行情数据表（冷数据存储）"""
        table_name = self._get_table_name_by_year(year)
        cursor = self.conn.cursor()
        
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                code TEXT,
                trade_date TEXT,
                cycle TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                amount REAL,
                adjust_type TEXT,       -- qfq(前复权), hfq(后复权), None(不复权)
                adjust_factor REAL,     -- 复权因子
                adjust_version INTEGER, -- 复权版本号（防止前视偏差）
                effective_date TEXT,    -- 数据生效日期（防止前视偏差）
                PRIMARY KEY (code, trade_date, cycle, adjust_type)
            )
        ''')
        
        # 创建索引
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{year}_code_cycle ON {table_name} (code, cycle)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{year}_code_date ON {table_name} (code, trade_date)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{year}_cycle_date ON {table_name} (cycle, trade_date)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{year}_adjust_type ON {table_name} (adjust_type)')
        
        self.conn.commit()
    
    def _is_hot_data(self, trade_date: str) -> bool:
        """判断是否为热数据"""
        try:
            date = datetime.strptime(trade_date.split(' ')[0], '%Y-%m-%d')
            current_year = datetime.now().year
            return (current_year - date.year) < self.HOT_DATA_YEARS
        except:
            return True  # 日期解析失败，默认视为热数据
    
    def _get_year_from_date(self, trade_date: str) -> int:
        """从日期中提取年份"""
        try:
            return int(trade_date.split('-')[0])
        except:
            return datetime.now().year
    
    def _get_tables_for_date_range(self, start_date: Optional[str], end_date: Optional[str]) -> List[str]:
        """获取日期范围内需要查询的表名列表"""
        tables = ['stock_quotes']  # 始终包含主表
        
        if start_date:
            start_year = self._get_year_from_date(start_date)
        else:
            start_year = 2000  # 默认从2000年开始
        
        if end_date:
            end_year = self._get_year_from_date(end_date)
        else:
            end_year = datetime.now().year
        
        # 添加冷数据表
        current_year = datetime.now().year
        cold_start_year = current_year - self.HOT_DATA_YEARS
        
        for year in range(start_year, end_year + 1):
            if year < cold_start_year:
                table_name = self._get_table_name_by_year(year)
                # 检查表是否存在
                cursor = self.conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if cursor.fetchone():
                    tables.append(table_name)
        
        return tables
    
    def save_stock_basic(self, df: pd.DataFrame):
        """保存股票基本信息（带事务）"""
        if df.empty:
            return
        
        df = df.fillna('')
        insert_data = []
        
        for _, row in df.iterrows():
            insert_data.append((
                row['code'],
                row['name'],
                row['exchange'],
                row['industry'],
                row['list_date'],
                row.get('delist_date', '')
            ))
        
        try:
            with self.conn:  # 自动 BEGIN / COMMIT / ROLLBACK
                self.conn.executemany('''
                    INSERT OR REPLACE INTO stock_basic
                    (code, name, exchange, industry, list_date, delist_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', insert_data)
            logger.info(f"✅ 保存股票基本信息: {len(insert_data)} 条")
        except Exception as e:
            logger.error(f"❌ 保存股票基本信息失败: {str(e)}")
    
    def save_quotes(self, df: pd.DataFrame):
        """保存行情数据（批量插入，带事务，支持冷热分离）"""
        if df.empty:
            return
        
        df = df.dropna(subset=['code', 'trade_date', 'cycle'])
        df = df[df['volume'] > 0]
        
        if df.empty:
            return
        
        # 按年份分组数据
        year_groups = {}
        for _, row in df.iterrows():
            trade_date = row['trade_date']
            year = self._get_year_from_date(trade_date)
            
            if year not in year_groups:
                year_groups[year] = []
            
            year_groups[year].append((
                row['code'],
                row['trade_date'],
                row['cycle'],
                row['open'],
                row['high'],
                row['low'],
                row['close'],
                row['volume'],
                row['amount'],
                row.get('adjust_type'),
                row.get('adjust_factor'),
                row.get('adjust_version', 1),
                row.get('effective_date', trade_date)
            ))
        
        # 获取热数据起始年份
        current_year = datetime.now().year
        hot_start_year = current_year - self.HOT_DATA_YEARS
        
        # 写入数据
        try:
            with self.conn:  # 自动 BEGIN / COMMIT / ROLLBACK
                for year, data_list in year_groups.items():
                    if year >= hot_start_year:
                        # 热数据写入主表
                        self.conn.executemany('''
                            INSERT OR REPLACE INTO stock_quotes
                            (code, trade_date, cycle, open, high, low, close, volume, amount,
                             adjust_type, adjust_factor, adjust_version, effective_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', data_list)
                        logger.debug(f"✅ 写入热数据: {len(data_list)} 条")
                    else:
                        # 冷数据写入年度表
                        table_name = self._get_table_name_by_year(year)
                        self._create_year_table(year)
                        self.conn.executemany(f'''
                            INSERT OR REPLACE INTO {table_name}
                            (code, trade_date, cycle, open, high, low, close, volume, amount,
                             adjust_type, adjust_factor, adjust_version, effective_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', data_list)
                        logger.debug(f"✅ 写入冷数据 {year}: {len(data_list)} 条")
            
            logger.debug(f"✅ 保存行情数据: {len(df)} 条（冷热分离存储）")
        except Exception as e:
            logger.error(f"❌ 批量写入行情数据失败: {str(e)}")
    
    def batch_upsert_quotes(self, data_list: list, table: str = "stock_quotes"):
        """批量写入行情数据（带事务，通用方法）"""
        sql = f"""
            INSERT OR REPLACE INTO {table}
            (code, trade_date, cycle, open, high, low, close, volume, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self.conn:  # 自动 BEGIN / COMMIT / ROLLBACK
                self.conn.executemany(sql, data_list)
            logger.debug(f"✅ 批量写入 {table} 成功: {len(data_list)} 条")
            return True
        except Exception as e:
            logger.error(f"❌ 批量写入 {table} 失败: {str(e)}")
            return False
    
    def save_trade_calendar(self, df: pd.DataFrame):
        """保存交易日历"""
        if df.empty:
            return
        
        insert_data = []
        for _, row in df.iterrows():
            insert_data.append((
                row['cal_date'],
                row['is_open'],
                row.get('exchange', '')
            ))
        
        try:
            with self.conn:
                self.conn.executemany('''
                    INSERT OR REPLACE INTO trade_calendar
                    (cal_date, is_open, exchange)
                    VALUES (?, ?, ?)
                ''', insert_data)
            logger.info(f"✅ 保存交易日历: {len(insert_data)} 条")
        except Exception as e:
            logger.error(f"❌ 保存交易日历失败: {str(e)}")
    
    def get_next_trade_date(self, last_date: str) -> Optional[str]:
        """获取下一个交易日"""
        cursor = self.conn.execute("""
            SELECT cal_date FROM trade_calendar
            WHERE cal_date > ? AND is_open = 1
            ORDER BY cal_date ASC LIMIT 1
        """, (last_date,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        next_date = row[0]
        
        # 检查是否超过今天
        today = datetime.now().strftime("%Y-%m-%d")
        if next_date > today:
            return None
        
        return next_date
    
    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表"""
        query = 'SELECT code, name, exchange, industry, list_date, delist_date FROM stock_basic ORDER BY exchange, code'
        return pd.read_sql_query(query, self.conn)
    
    def get_last_date(self, code: str, cycle: str) -> Optional[str]:
        """获取最后日期（从所有表中查找）"""
        # 先从主表查找
        cursor = self.conn.cursor()
        cursor.execute('SELECT MAX(trade_date) FROM stock_quotes WHERE code = ? AND cycle = ?', (code, cycle))
        result = cursor.fetchone()
        main_last_date = result[0] if result and result[0] else None
        
        # 检查是否有冷数据表需要查询
        current_year = datetime.now().year
        cold_start_year = current_year - self.HOT_DATA_YEARS
        
        max_date = main_last_date
        
        for year in range(2000, cold_start_year):
            table_name = self._get_table_name_by_year(year)
            try:
                cursor.execute(f'SELECT MAX(trade_date) FROM {table_name} WHERE code = ? AND cycle = ?', (code, cycle))
                result = cursor.fetchone()
                if result and result[0]:
                    if max_date is None or result[0] > max_date:
                        max_date = result[0]
            except:
                continue
        
        return max_date
    
    def get_quotes(
        self,
        code: str,
        cycle: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """获取行情数据（自动查询冷热数据表）"""
        tables = self._get_tables_for_date_range(start_date, end_date)
        
        dfs = []
        for table in tables:
            query = f'SELECT * FROM {table} WHERE code = ? AND cycle = ?'
            params = [code, cycle]
            
            if start_date:
                query += ' AND trade_date >= ?'
                params.append(start_date)
            if end_date:
                query += ' AND trade_date <= ?'
                params.append(end_date)
            
            query += ' ORDER BY trade_date'
            
            try:
                df = pd.read_sql_query(query, self.conn, params=params)
                if not df.empty:
                    dfs.append(df)
            except Exception as e:
                logger.debug(f"查询表 {table} 失败: {str(e)}")
        
        if dfs:
            return pd.concat(dfs).sort_values('trade_date').reset_index(drop=True)
        
        return pd.DataFrame()
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        cursor = self.conn.cursor()
        
        # 股票数量
        cursor.execute('SELECT COUNT(*) FROM stock_basic')
        stock_count = cursor.fetchone()[0]
        
        # 行情数据数量（主表）
        cursor.execute('SELECT COUNT(*) FROM stock_quotes')
        hot_quotes_count = cursor.fetchone()[0]
        
        # 冷数据数量
        cold_quotes_count = 0
        current_year = datetime.now().year
        cold_start_year = current_year - self.HOT_DATA_YEARS
        
        for year in range(2000, cold_start_year):
            table_name = self._get_table_name_by_year(year)
            try:
                cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
                cold_quotes_count += cursor.fetchone()[0]
            except:
                continue
        
        # 已存储周期
        cursor.execute('SELECT DISTINCT cycle FROM stock_quotes')
        cycles = [row[0] for row in cursor.fetchall()]
        
        # 日历数据数量
        cursor.execute('SELECT COUNT(*) FROM trade_calendar')
        calendar_count = cursor.fetchone()[0]
        
        # 进行中的任务数
        cursor.execute('SELECT COUNT(*) FROM task_progress WHERE status = ?', ('running',))
        running_tasks = cursor.fetchone()[0]
        
        # 获取冷数据年份列表
        cold_years = []
        for year in range(2000, cold_start_year):
            table_name = self._get_table_name_by_year(year)
            try:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if cursor.fetchone():
                    cold_years.append(year)
            except:
                continue
        
        return {
            'stock_count': stock_count,
            'hot_quotes_count': hot_quotes_count,
            'cold_quotes_count': cold_quotes_count,
            'total_quotes_count': hot_quotes_count + cold_quotes_count,
            'cycles': cycles,
            'calendar_count': calendar_count,
            'running_tasks': running_tasks,
            'cold_data_years': cold_years,
            'hot_data_years_threshold': cold_start_year
        }
    
    def migrate_cold_data(self):
        """将过期的热数据迁移到冷数据表"""
        logger.info("=" * 60)
        logger.info("开始迁移冷数据")
        logger.info("=" * 60)
        
        try:
            current_year = datetime.now().year
            cold_start_year = current_year - self.HOT_DATA_YEARS
            migrate_year = cold_start_year - 1  # 需要迁移的年份
            
            table_name = self._get_table_name_by_year(migrate_year)
            
            # 检查目标表是否已存在
            cursor = self.conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if not cursor.fetchone():
                self._create_year_table(migrate_year)
            
            # 查询需要迁移的数据
            cursor.execute('''
                SELECT code, trade_date, cycle, open, high, low, close, volume, amount
                FROM stock_quotes
                WHERE trade_date LIKE ?
            ''', (f'{migrate_year}-%',))
            
            rows = cursor.fetchall()
            
            if not rows:
                logger.info(f"✅ 没有需要迁移的冷数据（{migrate_year}年）")
                return True
            
            # 迁移数据
            with self.conn:
                self.conn.executemany(f'''
                    INSERT OR REPLACE INTO {table_name}
                    (code, trade_date, cycle, open, high, low, close, volume, amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', rows)
                
                # 删除原表数据
                self.conn.execute('DELETE FROM stock_quotes WHERE trade_date LIKE ?', (f'{migrate_year}-%',))
            
            logger.info(f"✅ 迁移冷数据完成: {len(rows)} 条数据从主表迁移到 {table_name}")
            return True
        
        except Exception as e:
            logger.error(f"❌ 迁移冷数据失败: {str(e)}")
            return False
    
    def get_cold_data_stats(self) -> dict:
        """获取冷数据统计信息"""
        stats = {}
        current_year = datetime.now().year
        cold_start_year = current_year - self.HOT_DATA_YEARS
        
        for year in range(2000, cold_start_year):
            table_name = self._get_table_name_by_year(year)
            try:
                cursor = self.conn.execute(f'SELECT COUNT(*) FROM {table_name}')
                count = cursor.fetchone()[0]
                stats[year] = count
            except:
                stats[year] = 0
        
        return stats
    
    # ==================== 断点续传相关方法 ====================
    
    def create_task(self, task_id: str, task_type: str, total_count: int, **kwargs) -> bool:
        """创建新任务"""
        try:
            with self.conn:
                self.conn.execute('''
                    INSERT OR REPLACE INTO task_progress
                    (task_id, task_type, status, total_count, success_count, fail_count, 
                     current_index, current_code, current_cycle, start_time, last_update_time,
                     error_message, extra_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id,
                    task_type,
                    'pending',
                    total_count,
                    0,
                    0,
                    0,
                    '',
                    '',
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    '',
                    ''
                ))
            logger.info(f"✅ 创建任务: {task_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 创建任务失败: {str(e)}")
            return False
    
    def update_task_progress(
        self,
        task_id: str,
        current_index: int,
        current_code: str = '',
        current_cycle: str = '',
        success_count: int = None,
        fail_count: int = None
    ) -> bool:
        """更新任务进度"""
        try:
            update_fields = ['current_index = ?', 'current_code = ?', 'current_cycle = ?', 'last_update_time = ?']
            update_values = [current_index, current_code, current_cycle, datetime.now().isoformat()]
            
            if success_count is not None:
                update_fields.append('success_count = ?')
                update_values.append(success_count)
            
            if fail_count is not None:
                update_fields.append('fail_count = ?')
                update_values.append(fail_count)
            
            update_values.append(task_id)
            
            sql = f'UPDATE task_progress SET {", ".join(update_fields)} WHERE task_id = ?'
            
            with self.conn:
                self.conn.execute(sql, update_values)
            return True
        except Exception as e:
            logger.error(f"❌ 更新任务进度失败: {str(e)}")
            return False
    
    def set_task_status(self, task_id: str, status: str, error_message: str = '') -> bool:
        """设置任务状态"""
        try:
            with self.conn:
                self.conn.execute('''
                    UPDATE task_progress
                    SET status = ?, error_message = ?, last_update_time = ?
                    WHERE task_id = ?
                ''', (status, error_message, datetime.now().isoformat(), task_id))
            logger.info(f"✅ 任务状态更新: {task_id} -> {status}")
            return True
        except Exception as e:
            logger.error(f"❌ 设置任务状态失败: {str(e)}")
            return False
    
    def get_task_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务进度"""
        cursor = self.conn.execute('''
            SELECT task_id, task_type, status, total_count, success_count, fail_count,
                   current_index, current_code, current_cycle, start_time, last_update_time, error_message
            FROM task_progress WHERE task_id = ?
        ''', (task_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return {
            'task_id': row[0],
            'task_type': row[1],
            'status': row[2],
            'total_count': row[3],
            'success_count': row[4],
            'fail_count': row[5],
            'current_index': row[6],
            'current_code': row[7],
            'current_cycle': row[8],
            'start_time': row[9],
            'last_update_time': row[10],
            'error_message': row[11]
        }
    
    def get_running_tasks(self) -> pd.DataFrame:
        """获取所有进行中的任务"""
        query = '''
            SELECT task_id, task_type, status, total_count, success_count, fail_count,
                   current_index, start_time, last_update_time
            FROM task_progress WHERE status = ?
        '''
        return pd.read_sql_query(query, self.conn, params=['running'])
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务记录"""
        try:
            with self.conn:
                self.conn.execute('DELETE FROM task_progress WHERE task_id = ?', (task_id,))
            logger.info(f"✅ 删除任务: {task_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 删除任务失败: {str(e)}")
            return False
    
    def cleanup_stale_tasks(self, hours: int = 24) -> int:
        """清理超时任务（超过指定小时数未更新的任务）"""
        try:
            cutoff_time = (datetime.now() - pd.Timedelta(hours=hours)).isoformat()
            cursor = self.conn.execute('''
                DELETE FROM task_progress 
                WHERE status = ? AND last_update_time < ?
            ''', ('running', cutoff_time))
            deleted = cursor.rowcount
            self.conn.commit()
            if deleted > 0:
                logger.info(f"✅ 清理超时任务: {deleted} 个")
            return deleted
        except Exception as e:
            logger.error(f"❌ 清理超时任务失败: {str(e)}")
            return 0
    
    # ==================== 技术指标相关方法 ====================
    
    def save_indicators(self, df: pd.DataFrame):
        """保存技术指标数据（批量插入，带事务）"""
        if df.empty:
            return
        
        df = df.dropna(subset=['code', 'trade_date', 'cycle'])
        
        if df.empty:
            return
        
        insert_data = []
        
        for _, row in df.iterrows():
            insert_data.append((
                row['code'],
                row['trade_date'],
                row['cycle'],
                row.get('MA5'),
                row.get('MA10'),
                row.get('MA20'),
                row.get('MA60'),
                row.get('MA120'),
                row.get('MA250'),
                row.get('MACD'),
                row.get('MACD_SIGNAL'),
                row.get('MACD_HIST'),
                row.get('KDJ_K'),
                row.get('KDJ_D'),
                row.get('KDJ_J'),
                row.get('BOLL_MID'),
                row.get('BOLL_UPPER'),
                row.get('BOLL_LOWER'),
                row.get('RSI'),
                row.get('ATR'),
                row.get('VOL_MA5'),
                row.get('VOL_MA10'),
                row.get('VOL_MA20')
            ))
        
        try:
            with self.conn:
                self.conn.executemany('''
                    INSERT OR REPLACE INTO stock_indicators
                    (code, trade_date, cycle, MA5, MA10, MA20, MA60, MA120, MA250,
                     MACD, MACD_SIGNAL, MACD_HIST, KDJ_K, KDJ_D, KDJ_J,
                     BOLL_MID, BOLL_UPPER, BOLL_LOWER, RSI, ATR,
                     VOL_MA5, VOL_MA10, VOL_MA20)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', insert_data)
            logger.info(f"✅ 保存技术指标: {len(insert_data)} 条")
        except Exception as e:
            logger.error(f"❌ 保存技术指标失败: {str(e)}")
    
    def get_indicators(
        self,
        code: str,
        cycle: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """获取技术指标数据"""
        query = 'SELECT * FROM stock_indicators WHERE code = ? AND cycle = ?'
        params = [code, cycle]
        
        if start_date:
            query += ' AND trade_date >= ?'
            params.append(start_date)
        if end_date:
            query += ' AND trade_date <= ?'
            params.append(end_date)
        
        query += ' ORDER BY trade_date'
        
        return pd.read_sql_query(query, self.conn, params=params)
    
    def get_indicators_last_date(self, code: str, cycle: str) -> Optional[str]:
        """获取技术指标最后日期"""
        cursor = self.conn.execute(
            'SELECT MAX(trade_date) FROM stock_indicators WHERE code = ? AND cycle = ?',
            (code, cycle)
        )
        result = cursor.fetchone()
        return result[0] if result and result[0] else None
    
    def delete_indicators(self, code: str, cycle: str = None) -> int:
        """删除指定股票的技术指标数据"""
        try:
            if cycle:
                cursor = self.conn.execute(
                    'DELETE FROM stock_indicators WHERE code = ? AND cycle = ?',
                    (code, cycle)
                )
            else:
                cursor = self.conn.execute(
                    'DELETE FROM stock_indicators WHERE code = ?',
                    (code,)
                )
            deleted = cursor.rowcount
            self.conn.commit()
            if deleted > 0:
                logger.info(f"✅ 删除技术指标: {deleted} 条")
            return deleted
        except Exception as e:
            logger.error(f"❌ 删除技术指标失败: {str(e)}")
            return 0
    
    # ==================== 标的生命周期映射相关方法 ====================
    
    def save_symbol_event(self, old_code: str, new_code: str, event_type: str, 
                         event_date: str, effective_date: str, 
                         old_name: str = '', new_name: str = '', extra_info: dict = None):
        """
        保存标的事件（代码变更、更名、ST、退市等）
        
        Args:
            old_code: 旧代码
            new_code: 新代码
            event_type: 事件类型: rename(更名), st(ST标记), delist(退市), merge(合并), split(分拆)
            event_date: 事件发生日期
            effective_date: 生效日期
            old_name: 旧名称
            new_name: 新名称
            extra_info: 额外信息（字典）
        
        Returns:
            是否成功
        """
        try:
            extra_info_json = json.dumps(extra_info) if extra_info else None
            
            cursor = self.conn.execute('''
                INSERT INTO symbol_mapping
                (old_code, new_code, event_type, event_date, effective_date, 
                 old_name, new_name, is_active, extra_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (old_code, new_code, event_type, event_date, effective_date, 
                  old_name, new_name, 1, extra_info_json))
            
            self.conn.commit()
            logger.info(f"✅ 保存标的事件: {event_type} {old_code} -> {new_code}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存标的事件失败: {str(e)}")
            return False
    
    def get_symbol_events(self, code: str = None, event_type: str = None, 
                         start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        获取标的事件记录
        
        Args:
            code: 股票代码（可匹配旧代码或新代码）
            event_type: 事件类型过滤
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            事件记录 DataFrame
        """
        query = 'SELECT * FROM symbol_mapping WHERE 1=1'
        params = []
        
        if code:
            query += ' AND (old_code = ? OR new_code = ?)'
            params.extend([code, code])
        
        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)
        
        if start_date:
            query += ' AND event_date >= ?'
            params.append(start_date)
        
        if end_date:
            query += ' AND event_date <= ?'
            params.append(end_date)
        
        query += ' ORDER BY event_date DESC'
        
        return pd.read_sql_query(query, self.conn, params=params)
    
    def get_symbol_history(self, code: str, as_of_date: str = None) -> list:
        """
        获取标的历史代码变更记录
        
        Args:
            code: 当前代码
            as_of_date: 截止日期
        
        Returns:
            历史代码列表（按时间倒序）
        """
        query = '''
            SELECT old_code, new_code, event_date, effective_date, event_type
            FROM symbol_mapping
            WHERE new_code = ? OR old_code = ?
        '''
        params = [code, code]
        
        if as_of_date:
            query += ' AND effective_date <= ?'
            params.append(as_of_date)
        
        query += ' ORDER BY event_date DESC'
        
        df = pd.read_sql_query(query, self.conn, params=params)
        
        history = []
        current_code = code
        
        for _, row in df.iterrows():
            if row['new_code'] == current_code:
                history.append({
                    'code': row['old_code'],
                    'event_type': row['event_type'],
                    'event_date': row['event_date'],
                    'effective_date': row['effective_date']
                })
                current_code = row['old_code']
        
        return history
    
    def is_stock_active(self, code: str, as_of_date: str) -> bool:
        """
        判断股票在指定日期是否处于活跃状态（未退市）
        
        Args:
            code: 股票代码
            as_of_date: 查询日期
        
        Returns:
            是否活跃
        """
        # 检查是否有退市事件在指定日期之前生效
        cursor = self.conn.execute('''
            SELECT COUNT(*) FROM symbol_mapping
            WHERE (old_code = ? OR new_code = ?)
              AND event_type = 'delist'
              AND effective_date <= ?
        ''', (code, code, as_of_date))
        
        count = cursor.fetchone()[0]
        return count == 0
    
    def resolve_symbol(self, code: str, as_of_date: str) -> str:
        """
        根据日期解析股票代码（处理更名等情况）
        
        Args:
            code: 当前代码
            as_of_date: 查询日期
        
        Returns:
            该日期有效的代码
        """
        # 查询该日期之前发生的更名事件
        cursor = self.conn.execute('''
            SELECT old_code, new_code, effective_date
            FROM symbol_mapping
            WHERE new_code = ?
              AND event_type = 'rename'
              AND effective_date > ?
            ORDER BY effective_date ASC
            LIMIT 1
        ''', (code, as_of_date))
        
        result = cursor.fetchone()
        
        if result:
            # 在 as_of_date 时，该代码还未变更，返回旧代码
            return result[0]
        
        return code
    
    # ==================== 历史股票池快照相关方法（解决幸存者偏差） ====================
    
    def save_stock_universe_snapshot(self, snapshot_date: str, df: pd.DataFrame):
        """
        保存指定日期的股票池快照
        
        Args:
            snapshot_date: 快照日期
            df: 包含股票信息的DataFrame，需包含以下字段:
                - code: 股票代码
                - name: 股票名称
                - exchange: 交易所
                - industry: 行业
                - list_date: 上市日期
                - delist_date: 退市日期（可选）
                - is_st: 是否ST（1=是，0=否，可选）
                - st_start_date: ST起始日期（可选）
                - is_active: 是否活跃（1=活跃，0=已退市）
        
        Returns:
            是否成功
        """
        if df.empty:
            logger.warning("股票池快照数据为空")
            return False
        
        df = df.fillna('')
        
        insert_data = []
        for _, row in df.iterrows():
            insert_data.append((
                snapshot_date,
                row['code'],
                row['name'],
                row.get('exchange', ''),
                row.get('industry', ''),
                row.get('list_date', ''),
                row.get('delist_date', ''),
                row.get('is_st', 0),
                row.get('st_start_date', ''),
                row.get('is_active', 1)
            ))
        
        try:
            with self.conn:
                self.conn.executemany('''
                    INSERT OR REPLACE INTO stock_universe_snapshot
                    (snapshot_date, code, name, exchange, industry, list_date,
                     delist_date, is_st, st_start_date, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', insert_data)
            logger.info(f"✅ 保存股票池快照: {snapshot_date} - {len(insert_data)} 只股票")
            return True
        except Exception as e:
            logger.error(f"❌ 保存股票池快照失败: {str(e)}")
            return False
    
    def get_stock_universe_at_date(self, as_of_date: str) -> pd.DataFrame:
        """
        获取指定日期的股票池（解决幸存者偏差）
        
        Args:
            as_of_date: 查询日期
            
        Returns:
            该日期存在的股票列表DataFrame
        """
        query = '''
            SELECT code, name, exchange, industry, list_date, delist_date,
                   is_st, st_start_date, is_active
            FROM stock_universe_snapshot
            WHERE snapshot_date = ? AND is_active = 1
            ORDER BY exchange, code
        '''
        return pd.read_sql_query(query, self.conn, params=[as_of_date])
    
    def get_stock_universe_range(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取日期范围内的股票池快照
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            日期范围内的股票池快照DataFrame
        """
        query = '''
            SELECT snapshot_date, code, name, exchange, industry, list_date,
                   delist_date, is_st, st_start_date, is_active
            FROM stock_universe_snapshot
            WHERE snapshot_date >= ? AND snapshot_date <= ?
            ORDER BY snapshot_date, exchange, code
        '''
        return pd.read_sql_query(query, self.conn, params=[start_date, end_date])
    
    def get_all_snapshot_dates(self) -> list:
        """获取所有已保存的快照日期"""
        cursor = self.conn.execute('SELECT DISTINCT snapshot_date FROM stock_universe_snapshot ORDER BY snapshot_date')
        return [row[0] for row in cursor.fetchall()]
    
    def get_stock_count_at_date(self, as_of_date: str) -> int:
        """获取指定日期的股票数量"""
        cursor = self.conn.execute(
            'SELECT COUNT(*) FROM stock_universe_snapshot WHERE snapshot_date = ? AND is_active = 1',
            (as_of_date,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0
    
    def is_stock_in_universe(self, code: str, as_of_date: str) -> bool:
        """
        判断股票在指定日期是否在股票池中（已上市且未退市）
        
        Args:
            code: 股票代码
            as_of_date: 查询日期
            
        Returns:
            是否在股票池中
        """
        cursor = self.conn.execute('''
            SELECT COUNT(*) FROM stock_universe_snapshot
            WHERE snapshot_date = ? AND code = ? AND is_active = 1
        ''', (as_of_date, code))
        
        count = cursor.fetchone()[0]
        return count > 0
    
    def build_historical_universe(self, start_date: str, end_date: str) -> bool:
        """
        构建历史股票池快照（补全日期范围内的快照）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            是否成功
        """
        logger.info(f"📊 开始构建历史股票池快照: {start_date} 至 {end_date}")
        
        try:
            # 获取交易日历
            calendar_df = self.get_trade_calendar(start_date, end_date, is_open=1)
            
            if calendar_df.empty:
                logger.warning("未获取到交易日历")
                return False
            
            # 获取股票基本信息
            stock_df = self.get_stock_list()
            if stock_df.empty:
                logger.warning("未获取到股票列表")
                return False
            
            # 获取已有快照日期
            existing_dates = set(self.get_all_snapshot_dates())
            
            # 获取ST和退市事件
            events_df = self.get_symbol_events()
            
            success_count = 0
            fail_count = 0
            
            for _, cal_row in calendar_df.iterrows():
                trade_date = cal_row['cal_date']
                
                if trade_date in existing_dates:
                    logger.debug(f"📅 跳过已存在的快照: {trade_date}")
                    continue
                
                # 构建当天的股票池
                daily_universe = []
                
                for _, stock_row in stock_df.iterrows():
                    code = stock_row['code']
                    list_date = stock_row.get('list_date', '')
                    delist_date = stock_row.get('delist_date', '')
                    
                    # 检查是否在当天已上市且未退市
                    if list_date and trade_date < list_date:
                        continue  # 还未上市
                    
                    if delist_date and trade_date >= delist_date:
                        continue  # 已退市
                    
                    # 检查ST状态
                    is_st = 0
                    st_start_date = ''
                    
                    if not events_df.empty:
                        st_events = events_df[
                            (events_df['event_type'] == 'st') &
                            ((events_df['old_code'] == code) | (events_df['new_code'] == code)) &
                            (events_df['effective_date'] <= trade_date)
                        ]
                        
                        if not st_events.empty:
                            st_event = st_events.sort_values('effective_date').iloc[-1]
                            is_st = 1
                            st_start_date = st_event['effective_date']
                    
                    daily_universe.append({
                        'code': code,
                        'name': stock_row['name'],
                        'exchange': stock_row.get('exchange', ''),
                        'industry': stock_row.get('industry', ''),
                        'list_date': list_date,
                        'delist_date': delist_date,
                        'is_st': is_st,
                        'st_start_date': st_start_date,
                        'is_active': 1
                    })
                
                if daily_universe:
                    df = pd.DataFrame(daily_universe)
                    if self.save_stock_universe_snapshot(trade_date, df):
                        success_count += 1
                    else:
                        fail_count += 1
            
            logger.info(f"✅ 历史股票池快照构建完成: 成功 {success_count} 天, 失败 {fail_count} 天")
            return True
        
        except Exception as e:
            logger.error(f"❌ 构建历史股票池快照失败: {str(e)}")
            return False
    
    # ==================== 财务数据与Point-in-Time处理相关方法 ====================
    
    def save_financial_report(self, df: pd.DataFrame) -> bool:
        """
        保存财务报表数据（原始数据，包含公告日期）
        
        Args:
            df: 包含财务报表数据的DataFrame，需包含以下字段:
                - code: 股票代码
                - report_type: 报表类型(annual/semi/quarterly)
                - report_period: 报告期（如2024Q4）
                - announcement_date: 公告日期（关键！）
                - publish_time: 发布时间
                - end_date: 报告截止日期
                - fiscal_year: 会计年度
                - fiscal_quarter: 会计季度
                - total_assets: 总资产
                - total_liabilities: 总负债
                - total_equity: 股东权益
                - revenue: 营业收入
                - operating_profit: 营业利润
                - net_profit: 净利润
                - eps: 每股收益
                - bps: 每股净资产
                - roe: 净资产收益率
                - roa: 总资产收益率
                - gross_margin: 毛利率
                - operating_margin: 营业利润率
                - cash_flow: 经营活动现金流
        
        Returns:
            是否成功
        """
        if df.empty:
            logger.warning("财务报表数据为空")
            return False
        
        df = df.fillna({
            'total_assets': None, 'total_liabilities': None, 'total_equity': None,
            'revenue': None, 'operating_profit': None, 'net_profit': None,
            'eps': None, 'bps': None, 'roe': None, 'roa': None,
            'gross_margin': None, 'operating_margin': None, 'cash_flow': None,
            'extra_info': None
        })
        
        insert_data = []
        for _, row in df.iterrows():
            insert_data.append((
                row['code'],
                row['report_type'],
                row['report_period'],
                row['announcement_date'],
                row.get('publish_time', ''),
                row['end_date'],
                row.get('fiscal_year'),
                row.get('fiscal_quarter'),
                row.get('total_assets'),
                row.get('total_liabilities'),
                row.get('total_equity'),
                row.get('revenue'),
                row.get('operating_profit'),
                row.get('net_profit'),
                row.get('eps'),
                row.get('bps'),
                row.get('roe'),
                row.get('roa'),
                row.get('gross_margin'),
                row.get('operating_margin'),
                row.get('cash_flow'),
                row.get('extra_info')
            ))
        
        try:
            with self.conn:
                self.conn.executemany('''
                    INSERT OR REPLACE INTO financial_report
                    (code, report_type, report_period, announcement_date, publish_time,
                     end_date, fiscal_year, fiscal_quarter,
                     total_assets, total_liabilities, total_equity,
                     revenue, operating_profit, net_profit,
                     eps, bps, roe, roa, gross_margin, operating_margin, cash_flow,
                     extra_info)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', insert_data)
            logger.info(f"✅ 保存财务报表: {len(insert_data)} 条")
            return True
        except Exception as e:
            logger.error(f"❌ 保存财务报表失败: {str(e)}")
            return False
    
    def get_financial_report(self, code: str = None, report_type: str = None, 
                            start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        获取财务报表原始数据
        
        Args:
            code: 股票代码
            report_type: 报表类型
            start_date: 公告日期开始
            end_date: 公告日期结束
        
        Returns:
            财务报表DataFrame
        """
        query = 'SELECT * FROM financial_report WHERE 1=1'
        params = []
        
        if code:
            query += ' AND code = ?'
            params.append(code)
        
        if report_type:
            query += ' AND report_type = ?'
            params.append(report_type)
        
        if start_date:
            query += ' AND announcement_date >= ?'
            params.append(start_date)
        
        if end_date:
            query += ' AND announcement_date <= ?'
            params.append(end_date)
        
        query += ' ORDER BY code, announcement_date, report_type'
        
        return pd.read_sql_query(query, self.conn, params=params)
    
    def build_financial_pit(self, code: str = None, rebuild_all: bool = False) -> bool:
        """
        构建Point-in-Time财务数据表（核心方法，解决未来函数问题）
        
        核心逻辑：
        1. 获取所有财务报表数据，按公告日期排序
        2. 获取交易日历
        3. 对于每个交易日，确定当天可用的最新财务数据
        4. 确保只有 trade_date >= announcement_date 的数据才可用
        
        Args:
            code: 股票代码（可选，指定则只处理该股票）
            rebuild_all: 是否重建全部数据（否则只增量更新）
        
        Returns:
            是否成功
        """
        logger.info(f"📊 开始构建PIT财务数据, code={code}, rebuild_all={rebuild_all}")
        
        try:
            # 获取财务报表数据
            report_df = self.get_financial_report(code=code)
            if report_df.empty:
                logger.warning("未获取到财务报表数据")
                return False
            
            # 获取交易日历（只获取有财务数据的日期范围）
            min_announcement_date = report_df['announcement_date'].min()
            max_announcement_date = report_df['announcement_date'].max()
            
            calendar_df = self.get_trade_calendar(min_announcement_date, max_announcement_date, is_open=1)
            if calendar_df.empty:
                logger.warning("未获取到交易日历")
                return False
            
            # 删除已存在的数据（如果重建全部或指定股票）
            if rebuild_all or code:
                with self.conn:
                    if code:
                        self.conn.execute('DELETE FROM financial_pit WHERE code = ?', (code,))
                    else:
                        self.conn.execute('DELETE FROM financial_pit')
            
            # 按股票分组处理
            grouped = report_df.groupby(['code', 'report_type'])
            total_records = 0
            
            for (stock_code, rpt_type), group_df in grouped:
                # 按公告日期排序
                sorted_df = group_df.sort_values('announcement_date').reset_index(drop=True)
                
                # 获取该股票的所有公告日期
                announcement_dates = sorted_df['announcement_date'].unique()
                
                # 遍历每个公告日期区间
                for i, announcement_date in enumerate(announcement_dates):
                    # 获取当前报表数据
                    current_report = sorted_df[sorted_df['announcement_date'] == announcement_date].iloc[0]
                    
                    # 确定生效起始日期（公告日期的下一个交易日）
                    start_date = self.get_next_trade_date(announcement_date)
                    if not start_date:
                        continue
                    
                    # 确定生效结束日期（下一个公告日期的前一个交易日）
                    if i < len(announcement_dates) - 1:
                        next_announcement = announcement_dates[i + 1]
                        # 找到下一个公告日期之前的最后一个交易日
                        end_date = self._get_last_trade_date_before(next_announcement)
                    else:
                        # 最后一个公告，结束日期为最新交易日
                        end_date = calendar_df['cal_date'].max()
                    
                    if not end_date or start_date > end_date:
                        continue
                    
                    # 获取此区间内的所有交易日
                    date_range = calendar_df[
                        (calendar_df['cal_date'] >= start_date) & 
                        (calendar_df['cal_date'] <= end_date)
                    ]['cal_date'].tolist()
                    
                    # 生成PIT记录
                    pit_records = []
                    for as_of_date in date_range:
                        pit_records.append((
                            stock_code,
                            as_of_date,
                            rpt_type,
                            current_report['report_period'],
                            announcement_date,
                            current_report['end_date'],
                            current_report['total_assets'],
                            current_report['total_liabilities'],
                            current_report['total_equity'],
                            current_report['revenue'],
                            current_report['operating_profit'],
                            current_report['net_profit'],
                            current_report['eps'],
                            current_report['bps'],
                            current_report['roe'],
                            current_report['roa'],
                            current_report['gross_margin'],
                            current_report['operating_margin'],
                            current_report['cash_flow']
                        ))
                    
                    # 批量写入
                    if pit_records:
                        with self.conn:
                            self.conn.executemany('''
                                INSERT OR REPLACE INTO financial_pit
                                (code, as_of_date, report_type, report_period,
                                 announcement_date, end_date,
                                 total_assets, total_liabilities, total_equity,
                                 revenue, operating_profit, net_profit,
                                 eps, bps, roe, roa, gross_margin, operating_margin, cash_flow)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', pit_records)
                        total_records += len(pit_records)
            
            logger.info(f"✅ PIT财务数据构建完成: {total_records} 条记录")
            return True
        
        except Exception as e:
            logger.error(f"❌ 构建PIT财务数据失败: {str(e)}")
            return False
    
    def _get_last_trade_date_before(self, date: str) -> Optional[str]:
        """获取指定日期之前的最后一个交易日"""
        cursor = self.conn.execute('''
            SELECT cal_date FROM trade_calendar
            WHERE cal_date < ? AND is_open = 1
            ORDER BY cal_date DESC LIMIT 1
        ''', (date,))
        
        row = cursor.fetchone()
        return row[0] if row else None
    
    def get_financial_pit(self, code: str, as_of_date: str, report_type: str = None) -> Optional[pd.Series]:
        """
        获取指定日期可用的财务数据（解决未来函数问题的核心查询方法）
        
        Args:
            code: 股票代码
            as_of_date: 查询日期（交易日期）
            report_type: 报表类型（可选）
        
        Returns:
            该日期可用的财务数据Series，若不存在则返回None
        """
        query = '''
            SELECT * FROM financial_pit
            WHERE code = ? AND as_of_date = ?
        '''
        params = [code, as_of_date]
        
        if report_type:
            query += ' AND report_type = ?'
            params.append(report_type)
        
        df = pd.read_sql_query(query, self.conn, params=params)
        
        if df.empty:
            return None
        
        return df.iloc[0]
    
    def get_financial_pit_range(self, code: str, start_date: str, end_date: str, 
                                report_type: str = None) -> pd.DataFrame:
        """
        获取日期范围内的PIT财务数据
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            report_type: 报表类型（可选）
        
        Returns:
            PIT财务数据DataFrame
        """
        query = '''
            SELECT * FROM financial_pit
            WHERE code = ? AND as_of_date >= ? AND as_of_date <= ?
        '''
        params = [code, start_date, end_date]
        
        if report_type:
            query += ' AND report_type = ?'
            params.append(report_type)
        
        query += ' ORDER BY as_of_date'
        
        return pd.read_sql_query(query, self.conn, params=params)
    
    def get_latest_financial_before_date(self, code: str, as_of_date: str, 
                                         report_type: str = None) -> Optional[pd.Series]:
        """
        获取指定日期之前可用的最新财务数据
        
        Args:
            code: 股票代码
            as_of_date: 查询日期
            report_type: 报表类型（可选）
        
        Returns:
            最新可用财务数据Series，若不存在则返回None
        """
        query = '''
            SELECT * FROM financial_pit
            WHERE code = ? AND as_of_date <= ?
        '''
        params = [code, as_of_date]
        
        if report_type:
            query += ' AND report_type = ?'
            params.append(report_type)
        
        query += ' ORDER BY as_of_date DESC LIMIT 1'
        
        df = pd.read_sql_query(query, self.conn, params=params)
        
        if df.empty:
            return None
        
        return df.iloc[0]


# 测试函数
if __name__ == '__main__':
    storage = SQLiteStorage()
    if storage.connect():
        stats = storage.get_stats()
        print(f"股票数量: {stats['stock_count']}")
        print(f"热数据数量: {stats['hot_quotes_count']}")
        print(f"冷数据数量: {stats['cold_quotes_count']}")
        print(f"总数据数量: {stats['total_quotes_count']}")
        print(f"已存储周期: {stats['cycles']}")
        print(f"交易日历数据: {stats['calendar_count']}")
        print(f"进行中任务: {stats['running_tasks']}")
        print(f"冷数据年份: {stats['cold_data_years']}")
        print(f"热数据起始年份: {stats['hot_data_years_threshold']}")
        
        # 测试冷数据迁移
        print("\n🔄 测试冷数据迁移...")
        storage.migrate_cold_data()
        
        # 获取冷数据统计
        cold_stats = storage.get_cold_data_stats()
        print(f"\n冷数据按年统计: {cold_stats}")
        
        storage.disconnect()

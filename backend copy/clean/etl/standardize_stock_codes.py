#!/usr/bin/env python3
"""
股票代码格式标准化脚本

问题描述：
- stock_basic 表存储格式: SZ.000001, SH.600001
- stock_quotes 表存储格式: 000001（纯数字）或 000001.SZ（带后缀）
- 这种格式不统一导致数据关联失败，监控页面覆盖率计算异常

解决方案：
1. 将所有股票代码统一为纯数字格式（如 000001）
2. 处理重复记录
3. 更新相关索引和约束

执行方式：
    python backend/clean/etl/standardize_stock_codes.py
"""

import os
import sys
import logging
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from sqlalchemy import text
from backend.collector.db.database import engine
from backend.utils.logger import setup_logger

logger = setup_logger('standardize_stock_codes')


def standardize_code(code: str) -> str:
    """
    将股票代码标准化为纯数字格式
    
    Args:
        code: 股票代码，支持格式：
              - SZ.000001, SH.600001, BJ.830001（前缀格式）
              - 000001.SZ, 600001.SH（后缀格式）
              - 000001（纯数字格式）
    
    Returns:
        纯数字格式的股票代码
    """
    code = str(code).strip()
    
    # 前缀格式: SZ.000001, SH.600001, BJ.830001
    if code.startswith('SZ.') or code.startswith('SH.') or code.startswith('BJ.'):
        return code[3:]
    
    # 后缀格式: 000001.SZ, 600001.SH
    if '.' in code:
        parts = code.split('.')
        if len(parts) == 2 and len(parts[0]) >= 6:
            return parts[0]
    
    # 小写前缀格式: sz.000001, sh.600001
    if code.startswith('sz.') or code.startswith('sh.') or code.startswith('bj.'):
        return code[3:]
    
    # 纯数字格式，直接返回
    return code


def standardize_stock_basic(conn):
    """标准化 stock_basic 表的股票代码"""
    # 查询所有需要标准化的记录
    result = conn.execute(text("SELECT code FROM stock_basic WHERE code LIKE 'SZ.%' OR code LIKE 'SH.%' OR code LIKE 'BJ.%'"))
    rows = result.fetchall()
    
    if not rows:
        logger.info("✅ stock_basic 表已无需标准化")
        return 0
    
    logger.info(f"📊 stock_basic 表需要标准化 {len(rows)} 条记录")
    
    # 逐行更新代码格式
    update_count = 0
    for (old_code,) in rows:
        new_code = standardize_code(old_code)
        
        if old_code == new_code:
            continue
        
        try:
            # 检查新代码是否已存在
            result = conn.execute(text("SELECT code FROM stock_basic WHERE code = :new_code"), {"new_code": new_code})
            if result.fetchone():
                # 已存在，删除旧记录
                conn.execute(text("DELETE FROM stock_basic WHERE code = :old_code"), {"old_code": old_code})
                logger.debug(f"🗑️ 删除重复记录: {old_code}")
            else:
                # 更新代码
                conn.execute(text("UPDATE stock_basic SET code = :new_code WHERE code = :old_code"), 
                           {"new_code": new_code, "old_code": old_code})
                update_count += 1
                logger.debug(f"🔄 更新代码: {old_code} -> {new_code}")
            
            conn.commit()
        except Exception as e:
            logger.error(f"❌ 更新 stock_basic 失败 {old_code}: {str(e)}")
            conn.rollback()
    
    logger.info(f"✅ stock_basic 表标准化完成，更新 {update_count} 条，删除重复 {len(rows) - update_count} 条")
    return update_count


def standardize_stock_quotes(conn):
    """标准化 stock_quotes 表的股票代码"""
    # 查询所有需要标准化的记录
    result = conn.execute(text("""
        SELECT DISTINCT code FROM stock_quotes 
        WHERE code LIKE '%.SZ' OR code LIKE '%.SH' OR code LIKE '%.BJ'
    """))
    rows = result.fetchall()
    
    if not rows:
        logger.info("✅ stock_quotes 表已无需标准化")
        return 0
    
    logger.info(f"📊 stock_quotes 表需要标准化 {len(rows)} 种不同的代码")
    
    # 处理每种代码格式
    total_updated = 0
    for (old_code,) in rows:
        new_code = standardize_code(old_code)
        
        if old_code == new_code:
            continue
        
        try:
            # 检查是否有冲突（新代码已存在同日期数据）
            result = conn.execute(text("""
                SELECT COUNT(*) FROM stock_quotes 
                WHERE code = :new_code AND cycle = '1d'
                AND EXISTS (
                    SELECT 1 FROM stock_quotes q2 
                    WHERE q2.code = :old_code AND q2.cycle = q.cycle AND q2.trade_date = q.trade_date
                )
            """), {"new_code": new_code, "old_code": old_code})
            conflict_count = result.scalar()
            
            if conflict_count > 0:
                # 有冲突，删除旧格式的数据
                conn.execute(text("DELETE FROM stock_quotes WHERE code = :old_code"), {"old_code": old_code})
                logger.debug(f"🗑️ 删除冲突记录: {old_code}")
            else:
                # 更新代码
                conn.execute(text("UPDATE stock_quotes SET code = :new_code WHERE code = :old_code"), 
                           {"new_code": new_code, "old_code": old_code})
                total_updated += 1
                logger.debug(f"🔄 更新代码: {old_code} -> {new_code}")
            
            conn.commit()
        except Exception as e:
            logger.error(f"❌ 更新 stock_quotes 失败 {old_code}: {str(e)}")
            conn.rollback()
    
    logger.info(f"✅ stock_quotes 表标准化完成，更新 {total_updated} 条")
    return total_updated


def standardize_stock_indicators(conn):
    """标准化 stock_indicators 表的股票代码"""
    result = conn.execute(text("""
        SELECT DISTINCT code FROM stock_indicators 
        WHERE code LIKE '%.SZ' OR code LIKE '%.SH' OR code LIKE '%.BJ'
    """))
    rows = result.fetchall()
    
    if not rows:
        logger.info("✅ stock_indicators 表已无需标准化")
        return 0
    
    logger.info(f"📊 stock_indicators 表需要标准化 {len(rows)} 种不同的代码")
    
    total_updated = 0
    for (old_code,) in rows:
        new_code = standardize_code(old_code)
        
        if old_code == new_code:
            continue
        
        try:
            conn.execute(text("UPDATE stock_indicators SET code = :new_code WHERE code = :old_code"), 
                       {"new_code": new_code, "old_code": old_code})
            total_updated += 1
            conn.commit()
            logger.debug(f"🔄 更新代码: {old_code} -> {new_code}")
        except Exception as e:
            logger.error(f"❌ 更新 stock_indicators 失败 {old_code}: {str(e)}")
            conn.rollback()
    
    logger.info(f"✅ stock_indicators 表标准化完成，更新 {total_updated} 条")
    return total_updated


def standardize_stock_adj_factor(conn):
    """标准化 stock_adj_factor 表的股票代码"""
    result = conn.execute(text("""
        SELECT DISTINCT code FROM stock_adj_factor 
        WHERE code LIKE '%.SZ' OR code LIKE '%.SH' OR code LIKE '%.BJ'
    """))
    rows = result.fetchall()
    
    if not rows:
        logger.info("✅ stock_adj_factor 表已无需标准化")
        return 0
    
    logger.info(f"📊 stock_adj_factor 表需要标准化 {len(rows)} 种不同的代码")
    
    total_updated = 0
    for (old_code,) in rows:
        new_code = standardize_code(old_code)
        
        if old_code == new_code:
            continue
        
        try:
            conn.execute(text("UPDATE stock_adj_factor SET code = :new_code WHERE code = :old_code"), 
                       {"new_code": new_code, "old_code": old_code})
            total_updated += 1
            conn.commit()
            logger.debug(f"🔄 更新代码: {old_code} -> {new_code}")
        except Exception as e:
            logger.error(f"❌ 更新 stock_adj_factor 失败 {old_code}: {str(e)}")
            conn.rollback()
    
    logger.info(f"✅ stock_adj_factor 表标准化完成，更新 {total_updated} 条")
    return total_updated


def standardize_trade_signals(conn):
    """标准化 trade_signals 表的股票代码"""
    result = conn.execute(text("""
        SELECT DISTINCT code FROM trade_signals 
        WHERE code LIKE '%.SZ' OR code LIKE '%.SH' OR code LIKE '%.BJ'
    """))
    rows = result.fetchall()
    
    if not rows:
        logger.info("✅ trade_signals 表已无需标准化")
        return 0
    
    logger.info(f"📊 trade_signals 表需要标准化 {len(rows)} 种不同的代码")
    
    total_updated = 0
    for (old_code,) in rows:
        new_code = standardize_code(old_code)
        
        if old_code == new_code:
            continue
        
        try:
            conn.execute(text("UPDATE trade_signals SET code = :new_code WHERE code = :old_code"), 
                       {"new_code": new_code, "old_code": old_code})
            total_updated += 1
            conn.commit()
            logger.debug(f"🔄 更新代码: {old_code} -> {new_code}")
        except Exception as e:
            logger.error(f"❌ 更新 trade_signals 失败 {old_code}: {str(e)}")
            conn.rollback()
    
    logger.info(f"✅ trade_signals 表标准化完成，更新 {total_updated} 条")
    return total_updated


def check_data_consistency(conn):
    """检查数据一致性"""
    logger.info("🔍 检查数据一致性...")
    
    # 检查 stock_quotes 中不存在于 stock_basic 的代码
    result = conn.execute(text("""
        SELECT COUNT(DISTINCT q.code) 
        FROM stock_quotes q
        LEFT JOIN stock_basic b ON q.code = b.code
        WHERE b.code IS NULL AND q.cycle = '1d'
    """))
    orphan_count = result.scalar()
    if orphan_count > 0:
        logger.warning(f"⚠️ stock_quotes 中有 {orphan_count} 只股票不在 stock_basic 中")
    
    # 检查 stock_basic 中不存在于 stock_quotes 的代码（最新交易日）
    result = conn.execute(text("SELECT MAX(trade_date) FROM stock_quotes WHERE cycle = '1d'"))
    latest_date = result.scalar()
    
    if latest_date:
        result = conn.execute(text("""
            SELECT COUNT(*) 
            FROM stock_basic b
            LEFT JOIN stock_quotes q ON b.code = q.code AND q.cycle = '1d' AND q.trade_date = :latest_date
            WHERE q.code IS NULL
        """), {"latest_date": latest_date})
        missing_count = result.scalar()
        logger.info(f"📈 最新交易日 {latest_date}: {missing_count} 只股票缺少行情数据")
    
    logger.info("✅ 数据一致性检查完成")


def main():
    """主函数"""
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("🚀 开始执行股票代码标准化脚本")
    logger.info(f"📅 执行时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    try:
        # 连接数据库
        with engine.connect() as conn:
            # 执行标准化
            standardize_stock_basic(conn)
            standardize_stock_quotes(conn)
            standardize_stock_indicators(conn)
            standardize_stock_adj_factor(conn)
            standardize_trade_signals(conn)
            
            # 检查数据一致性
            check_data_consistency(conn)
        
        end_time = datetime.now()
        elapsed = end_time - start_time
        logger.info("=" * 60)
        logger.info(f"✅ 股票代码标准化脚本执行完成")
        logger.info(f"⏱️ 执行耗时: {elapsed.total_seconds():.2f} 秒")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 脚本执行失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()

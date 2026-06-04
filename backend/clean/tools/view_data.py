#!/usr/bin/env python3
"""
数据验证脚本 - 快速查看Parquet文件内容
支持自动识别股票代码并拼接文件路径
检查股票列表文件是否过期（超过1天提示更新）
"""
import os
import pandas as pd
import sys
from datetime import datetime, timedelta

def get_exchange(code: str) -> str:
    """
    根据股票代码前缀判断交易所
    
    规则：
    - 600/601/602/603/605 开头 → 上交所 SH
    - 其他（000/001/002/300/301等）→ 深交所 SZ
    
    Args:
        code: 股票代码（纯数字，如 '000001' 或 '600000'）
        
    Returns:
        交易所后缀 '.SZ' 或 '.SH'
    """
    if not code or len(code) < 3:
        return '.SZ'  # 默认深交所
    
    prefix = code[:3]
    
    # 上交所主板：600/601/602/603/605 开头
    if prefix in ['600', '601', '602', '603', '605']:
        return '.SH'
    
    # 其他都是深交所（000/001/002主板，300/301创业板）
    return '.SZ'

def build_file_path(code: str, freq: str = 'daily') -> str:
    """
    根据股票代码构建完整的文件路径
    
    Args:
        code: 股票代码（可以是纯数字或带后缀格式）
        freq: 数据频率（daily/weekly/monthly）
        
    Returns:
        完整的文件路径
    """
    # 如果已经带后缀，直接使用
    if '.' in code:
        ts_code = code
    else:
        # 自动识别交易所并拼接
        exchange = get_exchange(code)
        ts_code = f"{code}{exchange}"
    
    # 构建路径 - 使用绝对路径
    base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'price', freq)
    file_path = os.path.join(base_path, f"{ts_code}.parquet")
    
    return file_path

def is_file_outdated(file_path: str, days: int = 1) -> bool:
    """
    检查文件是否过期
    
    Args:
        file_path: 文件路径
        days: 过期天数（默认1天）
        
    Returns:
        True 如果文件已过期或不存在，False 如果文件是最新的
    """
    if not os.path.exists(file_path):
        return True
    
    # 获取文件修改时间
    mtime = os.path.getmtime(file_path)
    file_date = datetime.fromtimestamp(mtime)
    now = datetime.now()
    
    # 计算时间差
    age = now - file_date
    
    # 如果文件修改时间超过指定天数，认为过期
    return age > timedelta(days=days)

def view_parquet(file_path: str):
    """查看Parquet文件内容"""
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f'❌ 文件不存在: {file_path}', file=sys.stderr)
            
            # 尝试另一个交易所
            if '.SZ' in file_path:
                alt_path = file_path.replace('.SZ.parquet', '.SH.parquet')
            else:
                alt_path = file_path.replace('.SH.parquet', '.SZ.parquet')
            
            if os.path.exists(alt_path):
                print(f'📌 尝试查找替代文件: {alt_path}')
                file_path = alt_path
            else:
                print(f'❌ 替代文件也不存在: {alt_path}', file=sys.stderr)
                return
        
        # 读取数据
        df = pd.read_parquet(file_path)
        
        print('=' * 80)
        print(f'文件: {file_path}')
        print('=' * 80)
        
        # 基本信息
        print(f'\n📊 数据概况:')
        print(f'   - 行数: {len(df)}')
        print(f'   - 列数: {len(df.columns)}')
        print(f'   - 列名: {", ".join(df.columns.tolist())}')
        
        # 数据类型
        print(f'\n📋 数据类型:')
        for col in df.columns:
            print(f'   {col:12s} : {df[col].dtype}')
        
        # 前10行
        print(f'\n📝 前10行数据:')
        print(df.head(10).to_string())
        
        # 后5行
        print(f'\n📝 后5行数据:')
        print(df.tail(5).to_string())
        
        # 统计信息
        print(f'\n📈 统计摘要:')
        print(df.describe().to_string())
        
        # 日期范围
        if 'trade_date' in df.columns:
            print(f'\n📅 日期范围:')
            print(f'   - 最早: {df["trade_date"].min()}')
            print(f'   - 最晚: {df["trade_date"].max()}')
        
        print('\n' + '=' * 80)
        
    except Exception as e:
        print(f'❌ 读取失败: {str(e)}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        # 默认查看000001.SZ的数据
        print('📌 未指定股票代码，默认查看 000001.SZ')
        file_path = build_file_path('000001')
        view_parquet(file_path)
    else:
        # 获取参数
        input_param = sys.argv[1]
        
        # 检查是否指定了频率
        freq = 'daily'
        if len(sys.argv) >= 3:
            freq = sys.argv[2]
        
        # 判断是文件路径还是股票代码
        # 如果包含 '/' 或 '.parquet'，则认为是文件路径
        if '/' in input_param or input_param.endswith('.parquet'):
            # 文件路径
            file_path = input_param
            # 如果没有 .parquet 后缀，添加它
            if not file_path.endswith('.parquet'):
                file_path += '.parquet'
            print(f'🔍 正在查看文件: {file_path}')
            
            # 如果是股票列表文件，检查是否过期
            if 'stock_list' in os.path.basename(file_path):
                if os.path.exists(file_path):
                    mtime = os.path.getmtime(file_path)
                    file_date = datetime.fromtimestamp(mtime)
                    age = datetime.now() - file_date
                    
                    if is_file_outdated(file_path, days=1):
                        # 计算过期天数
                        days_old = age.days
                        print(f'⚠️  股票列表已过期 {days_old} 天，建议更新')
                        print(f'   文件更新时间: {file_date.strftime("%Y-%m-%d %H:%M:%S")}')
                        print(f'   如需更新，请运行: python backend/main.py --mode list')
                    else:
                        print(f'✅ 文件更新时间: {file_date.strftime("%Y-%m-%d %H:%M:%S")} (数据有效)')
                else:
                    print(f'⚠️  文件不存在，如需创建请运行: python src/main.py --mode list')
        else:
            # 股票代码，构建文件路径
            file_path = build_file_path(input_param, freq)
            print(f'🔍 正在查看股票: {input_param} (频率: {freq})')
        
        print(f'📁 文件路径: {file_path}')
        view_parquet(file_path)

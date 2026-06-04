#!/usr/bin/env python3
"""从 akshare 获取行业数据并更新 stock_basic """

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from sqlalchemy import create_engine, text
from utils.config import load_config
import pandas as pd
import akshare as ak

def main():
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)

    print("📡 从 akshare 获取行业分类数据...")

    try:
        # 获取沪深股票行业分类
        df = ak.stock_board_industry_name_em()
        print(f"获取到 {len(df)} 个行业板块")

        # 也获取成分股行业
        stock_df = ak.stock_info_a_code_name()
        print(f"获取到 {len(stock_df)} 只股票信息")

        # 检查 akshare 是否有单只股票行业数据
        industry_map = {}
        try:
            # 尝试获取股票实时行情（包含行业）
            quote_df = ak.stock_zh_a_spot_em()
            if '行业' in quote_df.columns:
                industry_map = dict(zip(quote_df['代码'], quote_df['行业']))
                print(f"从实时行情获取到 {len(industry_map)} 只股票的行业数据")
        except Exception as e:
            print(f"获取实时行情失败: {e}")

        # 如果没有行业数据，使用 stock_board_industry_name_em 获取
        if not industry_map:
            print("使用板块成分股方式获取行业...")

        print("\n⚠️ 注意: akshare 免费接口可能无法获取单只股票的行业分类")
        print("建议: 使用 Tushare Pro 或其他付费数据源获取完整行业数据")

    except Exception as e:
        print(f"❌ 获取行业数据失败: {e}")

if __name__ == '__main__':
    main()

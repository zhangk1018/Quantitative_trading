#!/usr/bin/env python3
"""从东方财富获取股票行业数据"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pandas as pd
import requests
from sqlalchemy import create_engine, text
from utils.config import load_config
import time

def fetch_stock_industry(code):
    """获取单只股票的行业信息"""
    url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/Index?code={code}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.eastmoney.com/',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        
        html = response.text
        
        # 解析行业信息
        # 在HTML中查找行业信息
        import re
        
        # 查找行业
        industry_match = re.search(r'行业：</span><span class="value">(.*?)</span>', html)
        industry = industry_match.group(1).strip() if industry_match else ''
        
        # 查找细分行业
        sub_industry_match = re.search(r'细分行业：</span><span class="value">(.*?)</span>', html)
        sub_industry = sub_industry_match.group(1).strip() if sub_industry_match else ''
        
        return {
            'code': code,
            'industry': industry,
            'sub_industry': sub_industry
        }
    except Exception as e:
        print(f"获取 {code} 行业信息失败: {e}")
        return None

def main():
    config = load_config()
    db_url = config.get('database', {}).get('url', 'postgresql://quant_user:quant_password@localhost:5432/quant_trading')
    engine = create_engine(db_url)
    
    # 获取需要更新行业的股票列表
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT RIGHT(code, 6) as code 
            FROM stock_basic 
            WHERE industry IS NULL OR industry = '' 
            ORDER BY code 
            LIMIT 100
        """))
        codes = [row[0] for row in result.fetchall()]
    
    print(f"需要更新行业的股票数量: {len(codes)}")
    
    # 获取行业数据并更新
    updated_count = 0
    for code in codes:
        # 构造完整代码格式
        if code.startswith('6'):
            full_code = f"SH{code}"
        else:
            full_code = f"SZ{code}"
        
        industry_data = fetch_stock_industry(full_code)
        if industry_data and industry_data['industry']:
            with engine.connect() as conn:
                conn.execute(
                    text("""
                        UPDATE stock_basic 
                        SET industry = :industry, sub_industry = :sub_industry
                        WHERE RIGHT(code, 6) = :code
                    """),
                    {
                        'industry': industry_data['industry'],
                        'sub_industry': industry_data.get('sub_industry', ''),
                        'code': code
                    }
                )
                conn.commit()
            updated_count += 1
            print(f"✅ 更新 {code}: {industry_data['industry']}")
        
        # 限速
        time.sleep(0.5)
    
    print(f"\n已更新 {updated_count} 只股票的行业信息")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""获取真实的股票列表"""
import pandas as pd
import os

def main():
    try:
        import akshare
        print('正在从 akshare 获取股票列表...')
        df = akshare.stock_info_a_code_name()
        print(f'成功获取 {len(df)} 只股票')
        
        # 重命名列
        df = df.rename(columns={
            'code': 'ts_code',
            'name': 'name'
        })
        
        # 添加市场信息
        def get_market(ts_code):
            prefix = ts_code[:3]
            if prefix.startswith('6'):
                return 'sh_main', '上海主板'
            elif prefix in ['000', '001', '002']:
                return 'sz_main', '深圳主板'
            elif prefix in ['300', '301']:
                return 'gem', '创业板'
            elif prefix.startswith('68'):
                return 'star', '科创板'
            elif prefix.startswith('4'):
                return 'bj', '北交所'
            else:
                return 'other', '其他'
        
        df[['market', 'market_name']] = df['ts_code'].apply(
            lambda x: pd.Series(get_market(x))
        )
        
        # 保存
        os.makedirs('data/metadata', exist_ok=True)
        df.to_parquet('data/metadata/stock_list.parquet', index=False)
        print('✅ 已保存到 data/metadata/stock_list.parquet')
        print(f'\n市场分布:')
        print(df['market_name'].value_counts())
        
    except Exception as e:
        print(f'获取失败: {e}')
        # 如果 akshare 不可用，使用预定义的股票列表
        print('使用预定义的股票列表...')
        predefined_stocks = [
            ['600000.SH', '浦发银行', 'sh_main', '上海主板'],
            ['600001.SH', '邯郸钢铁', 'sh_main', '上海主板'],
            ['600004.SH', '白云机场', 'sh_main', '上海主板'],
            ['600005.SH', '武钢股份', 'sh_main', '上海主板'],
            ['600006.SH', '东风汽车', 'sh_main', '上海主板'],
            ['600007.SH', '中国国贸', 'sh_main', '上海主板'],
            ['600008.SH', '首创股份', 'sh_main', '上海主板'],
            ['600009.SH', '上海机场', 'sh_main', '上海主板'],
            ['600010.SH', '包钢股份', 'sh_main', '上海主板'],
            ['600011.SH', '华能国际', 'sh_main', '上海主板'],
            ['600012.SH', '皖通高速', 'sh_main', '上海主板'],
            ['600015.SH', '华夏银行', 'sh_main', '上海主板'],
            ['600016.SH', '民生银行', 'sh_main', '上海主板'],
            ['600018.SH', '上港集团', 'sh_main', '上海主板'],
            ['600019.SH', '宝钢股份', 'sh_main', '上海主板'],
            ['600028.SH', '中国石化', 'sh_main', '上海主板'],
            ['600029.SH', '南方航空', 'sh_main', '上海主板'],
            ['600030.SH', '中信证券', 'sh_main', '上海主板'],
            ['600031.SH', '三一重工', 'sh_main', '上海主板'],
            ['600036.SH', '招商银行', 'sh_main', '上海主板'],
            ['000001.SZ', '平安银行', 'sz_main', '深圳主板'],
            ['000002.SZ', '万科A', 'sz_main', '深圳主板'],
            ['000004.SZ', '国农科技', 'sz_main', '深圳主板'],
            ['000005.SZ', '世纪星源', 'sz_main', '深圳主板'],
            ['000006.SZ', '深振业A', 'sz_main', '深圳主板'],
            ['000007.SZ', '全新好', 'sz_main', '深圳主板'],
            ['000008.SZ', '神州高铁', 'sz_main', '深圳主板'],
            ['000009.SZ', '中国宝安', 'sz_main', '深圳主板'],
            ['000010.SZ', '美丽生态', 'sz_main', '深圳主板'],
            ['000011.SZ', '深物业A', 'sz_main', '深圳主板'],
            ['000012.SZ', '南玻A', 'sz_main', '深圳主板'],
            ['000014.SZ', '沙河股份', 'sz_main', '深圳主板'],
            ['000016.SZ', '深康佳A', 'sz_main', '深圳主板'],
            ['000017.SZ', '深中华A', 'sz_main', '深圳主板'],
            ['000018.SZ', '神州长城', 'sz_main', '深圳主板'],
            ['002001.SZ', '新和成', 'sz_main', '深圳主板'],
            ['002002.SZ', '鸿达兴业', 'sz_main', '深圳主板'],
            ['002003.SZ', '伟星股份', 'sz_main', '深圳主板'],
            ['002004.SZ', '华邦健康', 'sz_main', '深圳主板'],
            ['002005.SZ', '德豪润达', 'sz_main', '深圳主板'],
            ['300001.SZ', '特锐德', 'gem', '创业板'],
            ['300002.SZ', '神州泰岳', 'gem', '创业板'],
            ['300003.SZ', '乐普医疗', 'gem', '创业板'],
            ['300004.SZ', '南风股份', 'gem', '创业板'],
            ['300005.SZ', '探路者', 'gem', '创业板'],
            ['300006.SZ', '莱美药业', 'gem', '创业板'],
            ['300007.SZ', '汉威科技', 'gem', '创业板'],
            ['300008.SZ', '天海防务', 'gem', '创业板'],
            ['300009.SZ', '安科生物', 'gem', '创业板'],
            ['300010.SZ', '立思辰', 'gem', '创业板'],
            ['300011.SZ', '鼎汉技术', 'gem', '创业板'],
            ['300012.SZ', '华测检测', 'gem', '创业板'],
            ['300013.SZ', '新宁物流', 'gem', '创业板'],
            ['300014.SZ', '亿纬锂能', 'gem', '创业板'],
            ['300015.SZ', '爱尔眼科', 'gem', '创业板'],
        ]
        df = pd.DataFrame(predefined_stocks, columns=['ts_code', 'name', 'market', 'market_name'])
        df.to_parquet('data/metadata/stock_list.parquet', index=False)
        print(f'✅ 已保存 {len(df)} 只预定义股票')

if __name__ == '__main__':
    main()

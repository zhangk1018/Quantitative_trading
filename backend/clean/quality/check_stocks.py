
import pandas as pd
import os
import glob
from datetime import datetime, timedelta

def get_all_stocks():
    files = glob.glob('data/price/daily/*.parquet')
    return [os.path.basename(f).replace('.parquet', '') for f in files]

def get_latest_date(filepath):
    df = pd.read_parquet(filepath)
    if df.empty:
        return None
    latest_date = df['trade_date'].max()
    # 确保返回字符串格式 'YYYYMMDD'
    if isinstance(latest_date, pd.Timestamp):
        return latest_date.strftime('%Y%m%d')
    return str(latest_date)

def main():
    stocks = get_all_stocks()
    print('='*70)
    print('Total stocks:', len(stocks))
    print('='*70)
    print()
    
    today = datetime.now()
    yesterday = (today - timedelta(days=1)).strftime('%Y%m%d')
    
    outdated = []
    updated = []
    
    for stock in stocks:
        filepath = 'data/price/daily/' + stock + '.parquet'
        latest_date = get_latest_date(filepath)
        
        if latest_date and latest_date &gt;= yesterday:
            updated.append((stock, latest_date))
        else:
            outdated.append((stock, latest_date))
    
    print('Already updated to yesterday:', len(updated))
    print('Need update:', len(outdated))
    print()
    
    if outdated:
        print('Need update list:')
        print('-' * 40)
        for stock, date in sorted(outdated)[:50]:
            date_str = date if date else 'No data'
            print('  %-12s Latest date: %s' % (stock, date_str))
        
        if len(outdated) &gt; 50:
            print()
            print('... and %d more' % (len(outdated) - 50))
        print()
    
    if updated:
        print('Updated examples (first 20):')
        print('-' * 40)
        for stock, date in sorted(updated)[:20]:
            print('  %-12s Latest date: %s' % (stock, date))
    
    print()
    print('='*70)
    print('Summary')
    print('  Total:   %d' % len(stocks))
    print('  Updated: %d' % len(updated))
    print('  Outdated:%d' % len(outdated))
    print('='*70)

if __name__ == '__main__':
    main()


"""K 线图 - plotly 版 (支持中文, 输出 HTML)."""
import os
import psycopg2
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

CONN = dict(host="localhost", port=5432, dbname="quant_trading", user="quant_user", password="990518")

PATTERN_STYLE = {
    'pattern_morning_star':     {'color': '#00C853', 'symbol': 'triangle-up',   'short': 'MS', 'name': '早晨之星'},
    'pattern_evening_star':     {'color': '#D50000', 'symbol': 'triangle-down', 'short': 'ES', 'name': '黄昏之星'},
    'pattern_bullish_engulfing': {'color': '#FF6D00', 'symbol': 'triangle-up',   'short': 'BE', 'name': '看涨吞没'},
    'pattern_bearish_engulfing': {'color': '#6200EA', 'symbol': 'triangle-down', 'short': 'SE', 'name': '看跌吞没'},
    'pattern_hammer':           {'color': '#2962FF', 'symbol': 'diamond',       'short': 'HM', 'name': '锤子线'},
}

STOCK_NAMES = {
    '000001': '平安银行', '603136': '天目湖', '603639': '海利尔',
    '002724': '海洋王', '603159': '上海亚虹', '605100': '同庆楼',
}


def load_stock(code, days=90):
    conn = psycopg2.connect(**CONN)
    cur = conn.cursor()
    cur.execute('''
      SELECT trade_date, open, high, low, close, volume
      FROM stock_quotes_2026 WHERE code=%s AND cycle='1d'
      ORDER BY trade_date DESC LIMIT %s
    ''', (code, days))
    qrows = cur.fetchall()
    cur.execute('''
      SELECT trade_date, pattern_morning_star, pattern_evening_star,
             pattern_bullish_engulfing, pattern_bearish_engulfing, pattern_hammer
      FROM stock_indicators_2026 WHERE code=%s
      ORDER BY trade_date DESC LIMIT %s
    ''', (code, days))
    irows = {r[0]: r[1:] for r in cur.fetchall()}
    conn.close()

    df = pd.DataFrame(qrows, columns=['date','open','high','low','close','volume'])
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    for c in ['open','high','low','close','volume']:
        df[c] = df[c].astype(float)

    for col in PATTERN_STYLE:
        df[col] = 0
    for date, vals in irows.items():
        ts = pd.Timestamp(date)
        if ts in df['date'].values:
            for i, col in enumerate(PATTERN_STYLE):
                df.loc[df['date'] == ts, col] = vals[i]
    return df


def draw(code, days=90):
    df = load_stock(code, days)
    name = STOCK_NAMES.get(code, code)
    out = f'/Users/zhangk/workspace/Quantitative_trading/tmp/kline_{code}.html'

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=[0.75, 0.25])

    # K 线
    fig.add_trace(go.Candlestick(
        x=df['date'], open=df['open'], high=df['high'],
        low=df['low'], close=df['close'], name='K线',
        increasing_line_color='#E53935', increasing_fillcolor='#E53935',
        decreasing_line_color='#43A047', decreasing_fillcolor='#43A047',
    ), row=1, col=1)

    # 成交量
    colors = ['#E53935' if c >= o else '#43A047' for c, o in zip(df['close'], df['open'])]
    fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name='成交量',
                         marker_color=colors, showlegend=False), row=2, col=1)

    # 形态标注
    for col, sty in PATTERN_STYLE.items():
        hit = df[df[col] != 0]
        if len(hit) == 0:
            continue
        # 在 high 之上 2% 位置
        text_labels = [f"{sty['short']}{'+' if int(v) > 0 else ''}{int(v)}"
                       for v in hit[col]]
        fig.add_trace(go.Scatter(
            x=hit['date'], y=hit['high'] * 1.02,
            mode='markers+text',
            marker=dict(symbol=sty['symbol'], size=14, color=sty['color'],
                        line=dict(color='black', width=0.5)),
            text=text_labels,
            textposition='top center',
            textfont=dict(size=10, color=sty['color']),
            name=sty['name'],
        ), row=1, col=1)

    # 标题
    total_hits = int((df[list(PATTERN_STYLE)] != 0).any(axis=1).sum())
    fig.update_layout(
        title=dict(
            text=f'{code} {name} - 最近 {len(df)} 个交易日 (2026年), 共 {total_hits} 个形态命中',
            x=0.5, xanchor='center',
            font=dict(family='PingFang SC, STHeiti, Heiti SC, Microsoft YaHei, sans-serif', size=18)
        ),
        xaxis_rangeslider_visible=False,
        height=700, width=1400,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        font=dict(family='PingFang SC, STHeiti, Heiti SC, Microsoft YaHei, sans-serif', size=12),
        hovermode='x unified',
    )
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    fig.update_yaxes(title_text='价格 (元)', row=1, col=1)
    fig.update_yaxes(title_text='成交量', row=2, col=1)

    fig.write_html(out, include_plotlyjs='cdn')
    print(f'OK {code} {name}: {total_hits} 个形态 -> {out}')
    return out


if __name__ == '__main__':
    for code in ['000001', '603136']:
        draw(code, days=90)

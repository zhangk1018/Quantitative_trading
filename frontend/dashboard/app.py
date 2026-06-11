"""
app.py - Streamlit 看板入口

【启动方式】
    cd /Users/zhangk/workspace/Quantitative_trading
    streamlit run frontend/dashboard/app.py

【功能页面】
1. 股票筛选（与 stocks 路由对接）
2. K线 + 信号可视化（与 kline/signals 路由对接）
3. 策略回测（本地 engine + 后台 K线）
4. 绩效分析（metrics.py）

【依赖】
    pip install streamlit plotly pandas
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from frontend.utils import BackendClient
from frontend.strategies import (
    DoubleMAStrategy,
    MACrossStrategy,
    RSIStrategy,
    BollBandStrategy,
)
from frontend.backtester import BacktestEngine


# ============================================
# 页面配置
# ============================================

st.set_page_config(
    page_title='量化策略看板',
    page_icon='📈',
    layout='wide',
    initial_sidebar_state='expanded',
)


# ============================================
# 后台客户端
# ============================================

@st.cache_resource
def get_client() -> BackendClient:
    """获取后台客户端（缓存，避免重复创建）"""
    return BackendClient(base_url='http://localhost:8000')


# ============================================
# 侧边栏
# ============================================

st.sidebar.title('📊 量化策略看板')
page = st.sidebar.radio(
    '功能页面',
    ['🔍 股票筛选', '📈 K线 + 信号', '🧪 策略回测', '📊 绩效分析'],
)

st.sidebar.markdown('---')
st.sidebar.markdown('### ⚙️ 后台状态')
client = get_client()
if client.health_check():
    st.sidebar.success('✅ 后台在线')
else:
    st.sidebar.error('❌ 后台离线')
    st.sidebar.info('请先启动后台: `cd backend && python main.py`')


# ============================================
# 页面 1: 股票筛选
# ============================================

if page == '🔍 股票筛选':
    st.title('🔍 股票筛选')
    st.caption('调用后台 /api/stocks 路由')

    col1, col2, col3 = st.columns(3)
    with col1:
        as_of_date = st.date_input('数据日期', value=pd.Timestamp('2026-06-05'))
    with col2:
        sort_by = st.selectbox('排序字段', ['change_pct', 'close', 'volume', 'pe', 'pb'])
    with col3:
        sort_asc = st.checkbox('升序', value=False)

    industry = st.text_input('行业过滤（逗号分隔）', '')

    if st.button('🔍 查询'):
        try:
            result = client.get_stocks(
                as_of_date=str(as_of_date),
                sort_by=sort_by,
                sort_asc=sort_asc,
                limit=50,
                industry=industry if industry else None,
            )
            st.success(f'✅ 找到 {result.get("total", 0)} 只股票')

            df = pd.DataFrame(result.get('data', []))
            if not df.empty:
                st.dataframe(
                    df[['stock_code', 'stock_name', 'industry', 'close', 'change_pct', 'turnover_rate', 'pe']],
                    use_container_width=True,
                )
        except Exception as e:
            st.error(f'查询失败: {e}')


# ============================================
# 页面 2: K线 + 信号
# ============================================

elif page == '📈 K线 + 信号':
    st.title('📈 K线 + 买卖信号')

    col1, col2, col3 = st.columns(3)
    with col1:
        stock_code = st.text_input('股票代码', '000001.SZ')
    with col2:
        start = st.date_input('开始日期', value=pd.Timestamp('2024-01-01'))
    with col3:
        end = st.date_input('结束日期', value=pd.Timestamp('2026-06-05'))

    adj = st.selectbox('复权方式', ['none', 'forward', 'backward'], index=1, format_func=lambda x: {'none': '不复权', 'forward': '前复权', 'backward': '后复权'}[x])

    if st.button('📈 加载K线'):
        try:
            kline = client.get_kline(
                stock_code=stock_code,
                start=str(start),
                end=str(end),
                adj=adj,
            )
            signals = client.get_signals(stock_code, str(start), str(end))

            if not kline:
                st.warning('无数据')
            else:
                df = pd.DataFrame(kline)
                df['trade_date'] = pd.to_datetime(df['trade_date'])

                # 画 K线 + 均线
                fig = make_subplots(
                    rows=2, cols=1, shared_xaxes=True,
                    row_heights=[0.7, 0.3], vertical_spacing=0.05,
                )
                fig.add_trace(go.Candlestick(
                    x=df['trade_date'], open=df['open'], high=df['high'],
                    low=df['low'], close=df['close'], name='K线',
                ), row=1, col=1)

                # 叠加 MA
                for ma_col, color in [('ma5', 'blue'), ('ma10', 'orange'), ('ma20', 'purple')]:
                    if ma_col in df.columns and df[ma_col].notna().any():
                        fig.add_trace(go.Scatter(
                            x=df['trade_date'], y=df[ma_col],
                            mode='lines', name=ma_col.upper(), line=dict(color=color, width=1),
                        ), row=1, col=1)

                # 信号点
                if signals:
                    sig_df = pd.DataFrame(signals)
                    sig_df['trade_date'] = pd.to_datetime(sig_df['trade_date'])
                    buys = sig_df[sig_df['signal_type'] == 'buy']
                    sells = sig_df[sig_df['signal_type'] == 'sell']
                    if not buys.empty:
                        fig.add_trace(go.Scatter(
                            x=buys['trade_date'], y=buys['price'],
                            mode='markers', name='买入', marker=dict(symbol='triangle-up', size=12, color='red'),
                        ), row=1, col=1)
                    if not sells.empty:
                        fig.add_trace(go.Scatter(
                            x=sells['trade_date'], y=sells['price'],
                            mode='markers', name='卖出', marker=dict(symbol='triangle-down', size=12, color='green'),
                        ), row=1, col=1)

                # 成交量
                fig.add_trace(go.Bar(
                    x=df['trade_date'], y=df['volume'], name='成交量',
                ), row=2, col=1)

                fig.update_layout(height=600, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f'加载失败: {e}')


# ============================================
# 页面 3: 策略回测
# ============================================

elif page == '🧪 策略回测':
    st.title('🧪 策略回测')

    col1, col2 = st.columns(2)
    with col1:
        stock_code = st.text_input('股票代码', '000001.SZ', key='bt_code')
        strategy_name = st.selectbox('策略', ['双均线', '金叉死叉', 'RSI超买超卖', '布林带'])
    with col2:
        start = st.date_input('开始日期', value=pd.Timestamp('2024-01-01'), key='bt_start')
        end = st.date_input('结束日期', value=pd.Timestamp('2026-06-05'), key='bt_end')
        initial_cash = st.number_input('初始资金', value=1_000_000)

    if strategy_name == '双均线':
        fast = st.slider('快线周期', 2, 30, 5)
        slow = st.slider('慢线周期', 5, 60, 20)
        strategy = DoubleMAStrategy(fast=fast, slow=slow)
    elif strategy_name == '金叉死叉':
        fast = st.slider('快线周期', 2, 30, 5)
        slow = st.slider('慢线周期', 5, 60, 20)
        strategy = MACrossStrategy(fast=fast, slow=slow)
    elif strategy_name == 'RSI超买超卖':
        period = st.slider('RSI周期', 5, 30, 14)
        oversold = st.slider('超卖线', 10, 40, 30)
        overbought = st.slider('超买线', 60, 90, 70)
        strategy = RSIStrategy(period=period, oversold=oversold, overbought=overbought)
    else:
        period = st.slider('布林带周期', 10, 60, 20)
        num_std = st.slider('标准差倍数', 1.0, 3.0, 2.0)
        strategy = BollBandStrategy(period=period, num_std=num_std)

    if st.button('🚀 开始回测'):
        try:
            kline = client.get_kline(stock_code, str(start), str(end), adj='forward')
            if not kline:
                st.warning('无数据')
            else:
                df = pd.DataFrame(kline)
                engine = BacktestEngine(strategy=strategy, initial_cash=initial_cash)
                result = engine.run(df, stock_code=stock_code)

                # 显示绩效
                col1, col2, col3, col4 = st.columns(4)
                col1.metric('总收益率', f'{result.metrics.total_return*100:.2f}%')
                col2.metric('年化', f'{result.metrics.annual_return*100:.2f}%')
                col3.metric('最大回撤', f'{result.metrics.max_drawdown*100:.2f}%')
                col4.metric('夏普', f'{result.metrics.sharpe_ratio:.2f}')

                # 资金曲线
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=result.equity_curve.index, y=result.equity_curve.values,
                    mode='lines', name='资金曲线', line=dict(color='blue'),
                ))
                fig.update_layout(title='资金曲线', xaxis_title='日期', yaxis_title='资产', height=400)
                st.plotly_chart(fig, use_container_width=True)

                # 交易记录
                if result.trades:
                    st.subheader('📋 交易记录')
                    st.dataframe(pd.DataFrame(result.trades), use_container_width=True)
        except Exception as e:
            st.error(f'回测失败: {e}')


# ============================================
# 页面 4: 绩效分析
# ============================================

elif page == '📊 绩效分析':
    st.title('📊 绩效分析')
    st.info('💡 在【策略回测】页面跑完策略后，可以上传交易记录做深度分析')
    st.markdown('待开发：归因分析、基准对比、参数敏感性分析')


# ============================================
# 页脚
# ============================================

st.sidebar.markdown('---')
st.sidebar.caption('Version 0.1.0 | 量量 © 2026')

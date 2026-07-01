"""
ETL 全流程监控仪表盘
运行环境要求：
Python 3.9+
pip install streamlit sqlalchemy psycopg2-binary plotly pandas python-dotenv
配置文件（项目根目录 .env）：
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=quant_trading
PG_USER=postgres
PG_PASSWORD=your_password
运行方式：
streamlit run ui_dashboard.py
"""

# ============================================================
# 1. 导入依赖
# ============================================================
import os
import json
from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, ProgrammingError
from dotenv import load_dotenv

# 任务名称 → 中文显示映射（仅用于部分场景，但仪表盘显示将直接使用程序名）
TASK_DISPLAY_NAMES = {
    "pipeline_health_check": "健康检查",
    "stock_list_sync": "股票列表同步",
    "daily_import": "日线数据下载",
    "adj_factor_sync": "复权因子同步",
    "daily_basic_sync": "基本面数据同步",
    "fill_missing_data": "缺失数据补全",
    "indicators_compute": "技术指标计算",
    "signal_precompute": "生成交易信号",
    "daily_sync": "宽表同步",
    "parquet_export": "导出 Parquet",
    "restart_backend": "重启后端服务",
}

# 任务名称 → 标准阶段序号（覆盖数据库中的 stage 字段）
TASK_STAGE_MAP = {
    "pipeline_health_check": 1,
    "stock_list_sync": 2,
    "daily_import": 3,
    "adj_factor_sync": 4,
    "daily_basic_sync": 5,
    "fill_missing_data": 6,
    "indicators_compute": 7,
    "signal_precompute": 8,
    "daily_sync": 9,
    "parquet_export": 10,
    "restart_backend": 11,
}

# ============================================================
# 2. 页面配置
# ============================================================
st.set_page_config(
    page_title="ETL 监控仪表盘",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 3. 自定义样式（深色主题适配 + 只隐藏Deploy按钮，保留侧边栏切换）
# ============================================================
st.markdown(
    """
    <style>
    /* 调整主容器padding */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 0rem;
    }
    
    /* 深色主题下的 metric 卡片样式 */
    div[data-testid="stMetric"] {
        background-color: #1a1d23;
        border: 1px solid #2d3139;
        padding: 15px 10px;
        border-radius: 0.5rem;
    }
    
    div[data-testid="stMetric"] label {
        color: #8b949e;
    }
    
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #e6edf3;
    }
    
    /* 减小详情面板中 metric 的字体大小 */
    div[data-testid="stExpander"] div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 1rem !important;
        font-weight: normal !important;
    }
    
    div[data-testid="stExpander"] div[data-testid="stMetric"] label {
        font-size: 0.875rem !important;
    }
    
    /* Expander 深色适配 */
    .streamlit-expanderHeader {
        background-color: #1a1d23 !important;
        color: #e6edf3 !important;
    }
    
    /* 只隐藏Deploy按钮，不隐藏header和MainMenu（保留侧边栏切换功能） */
    .stDeployButton {
        display: none !important;
    }
    
    [data-testid="stDeployButton"] {
        display: none !important;
    }
    
    /* 隐藏Deploy按钮但保留其他header元素 */
    header .stDeployButton,
    header [data-testid="stDeployButton"] {
        visibility: hidden !important;
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# 4. 加载环境变量
# ============================================================
load_dotenv()
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DATABASE = os.getenv("PG_DATABASE", "quant_trading")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
DATABASE_URL = (
    f"postgresql://{PG_USER}:{PG_PASSWORD}"
    f"@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
)

# ============================================================
# 5. 常量定义
# ============================================================
# 所有状态（英文键值，用于数据库查询）
ALL_STATUSES = ["success", "failed", "running", "skipped", "not_started"]

# 阶段序号与中文名映射
STAGE_NAMES = {
    1: "健康检查",
    2: "股票列表同步",
    3: "日线数据下载",
    4: "复权因子同步",
    5: "基本面数据同步",
    6: "缺失数据补全",
    7: "技术指标计算",
    8: "生成交易信号",
    9: "宽表同步",
    10: "导出 Parquet",
    11: "重启后端服务",
}

# 状态中英文映射（用于显示）
STATUS_DISPLAY_NAMES = {
    "success": "成功",
    "failed": "失败",
    "running": "运行中",
    "skipped": "跳过",
    "not_started": "未开始",
}

# 状态 Emoji 映射
STATUS_EMOJI = {
    "success": "✅ 成功",
    "failed": "❌ 失败",
    "running": "🔄 运行中",
    "skipped": "️ 跳过",
    "not_started": "⏸️ 未开始",
}

STATUS_COLORS = {
    "success": "#00cc96",
    "failed": "#ef553b",
    "running": "#636EFA",
    "skipped": "#ab63fa",
    "not_started": "#ABA7A7",
}

# ============================================================
# 6. 数据库连接（连接池复用）
# ============================================================
@st.cache_resource
def get_engine():
    """创建并缓存 SQLAlchemy Engine，全局复用连接池。"""
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    return engine

# ============================================================
# 7. 数据加载函数（30 秒缓存）
# ============================================================
@st.cache_data(ttl=30)
def load_task_data(_engine, days, statuses, batch_filter=None):
    """从 task_run_log 表加载任务执行数据。
    
    Parameters
    ----------
    _engine : SQLAlchemy Engine
    days : int
        查询近 N 天的数据
    statuses : list
        要筛选的任务状态列表（英文）
    batch_filter : str or None
        - None 或 "__all__"：返回所有符合条件的记录
        - "__latest__"：每个 data_date 只保留最新批次的记录（去重）
        - 具体 batch_id 字符串：只返回该批次的记录
    """
    # 动态构建状态 IN 子句
    status_conditions = " OR ".join(
        [f"status = :status_{i}" for i in range(len(statuses))]
    )

    batch_clause = ""
    params = {"days": days}
    if batch_filter and batch_filter not in ("__latest__", "__all__"):
        batch_clause = " AND batch_id = :batch_id"
        params["batch_id"] = batch_filter

    query_str = f"""
    SELECT
        id, task_name, stage, start_time, end_time,
        status, exit_code, error_message, rows_affected,
        extra_metrics, created_at, data_date, batch_id,
        CASE
            WHEN end_time IS NOT NULL
            THEN EXTRACT(EPOCH FROM (end_time - start_time))
            WHEN status = 'not_started'
            THEN 0
            ELSE EXTRACT(EPOCH FROM (NOW() - start_time))
        END AS duration_seconds
    FROM task_run_log
    WHERE start_time >= NOW() - make_interval(days => :days)
      AND ({status_conditions})
      {batch_clause}
    ORDER BY start_time DESC
    """

    # 绑定参数
    for i, s in enumerate(statuses):
        params[f"status_{i}"] = s

    df = pd.read_sql(text(query_str), _engine, params=params)

    # 处理 extra_metrics JSONB 字段
    if "extra_metrics" in df.columns:
        df["extra_metrics"] = df["extra_metrics"].apply(
            lambda x: json.loads(x)
            if isinstance(x, str) and x
            else (x if isinstance(x, dict) else {})
        )

    # 使用 task_name 映射标准阶段，覆盖数据库中的 stage
    df['stage'] = df['task_name'].map(TASK_STAGE_MAP)
    df['stage'] = df['stage'].fillna(df['stage']).astype(int)

    # 如果 batch_filter == "__latest__"，进行去重：每个 data_date 只保留最新批次
    if batch_filter == "__latest__":
        df_with_date = df[df['data_date'].notna()]
        if not df_with_date.empty:
            idx = df_with_date.groupby('data_date')['start_time'].idxmax()
            latest_batch_ids = df_with_date.loc[idx, 'batch_id'].unique()
            df = df[df['batch_id'].isin(latest_batch_ids)]
        else:
            df = pd.DataFrame()

    # 增加阶段中文名映射列
    def format_stage(x):
        if pd.isna(x):
            return "未知阶段"
        idx = int(x)
        return f"{idx} - {STAGE_NAMES.get(idx, '未知阶段')}"

    df["stage_name"] = df["stage"].apply(format_stage)

    # 【修改】任务名称直接显示程序名（英文 task_name），不再使用中文映射
    df["task_display_name"] = df["task_name"]  # 直接用程序名

    return df


@st.cache_data(ttl=60)
def load_available_batches(_engine, days=7):
    """获取可用的批次列表（用于侧边栏筛选器）。"""
    query_str = """
    SELECT batch_id,
           COUNT(*) as task_count,
           MIN(start_time) as first_start,
           MAX(start_time) as last_end,
           STRING_AGG(DISTINCT status::text, ',') as statuses
    FROM task_run_log
    WHERE batch_id IS NOT NULL
      AND start_time >= NOW() - make_interval(days => :days)
    GROUP BY batch_id
    ORDER BY MAX(start_time) DESC
    """
    df = pd.read_sql(text(query_str), _engine, params={"days": days})
    return df

# ============================================================
# 8. 侧边栏 —— 筛选器
# ============================================================
def render_sidebar(engine):
    """渲染侧边栏筛选器。"""
    with st.sidebar:
        st.header("数据筛选")

        # 时间范围
        time_options = {
            "近 1 天": 1,
            "近 3 天": 3,
            "近 7 天": 7,
            "近 30 天": 30,
        }
        time_label = st.selectbox(
            "时间范围",
            options=list(time_options.keys()),
            index=0,
        )
        days = time_options[time_label]

        st.divider()

        # 任务状态 (下拉菜单，中文显示)
        status_options = ["全部"] + [STATUS_DISPLAY_NAMES[s] for s in ALL_STATUSES]
        selected_status = st.selectbox("📌 任务状态", options=status_options)

        # 反向映射：中文 -> 英文
        status_reverse_map = {v: k for k, v in STATUS_DISPLAY_NAMES.items()}
        if selected_status == "全部":
            statuses = ALL_STATUSES
        else:
            statuses = [status_reverse_map[selected_status]]

        # 执行阶段筛选 (下拉菜单，显示所有 11 个阶段)
        stage_options = ["全部"] + [f"{k} - {v}" for k, v in STAGE_NAMES.items()]
        selected_stage = st.selectbox("📍 执行阶段", options=stage_options)

        if selected_stage == "全部":
            stages = list(STAGE_NAMES.keys())
        else:
            stage_num = int(selected_stage.split(" - ")[0])
            stages = [stage_num]

        st.divider()

        # 批次筛选（默认"最新有效批次"）
        try:
            batches_df = load_available_batches(engine, days)
            batch_labels = {"__latest__": "最新有效批次（自动去重）", "__all__": "全部记录（含重复）"}
            if not batches_df.empty:
                for _, row in batches_df.iterrows():
                    bid = row["batch_id"]
                    short_id = bid[:19] + "..." if len(bid) > 22 else bid
                    cnt = int(row["task_count"])
                    ts = str(row["last_end"])[:16] if pd.notna(row["last_end"]) else ""
                    batch_labels[bid] = f"{short_id} ({cnt}任务, {ts})"
            batch_keys = list(batch_labels.keys())
            selected_batch_key = st.selectbox(
                "📦 批次筛选",
                options=batch_keys,
                format_func=lambda x: batch_labels.get(x, x),
                index=0,
            )
        except Exception:
            selected_batch_key = "__latest__"
            st.caption("⚠️ 批次列表加载失败，使用默认去重模式")

        st.divider()

        # 手动刷新
        if st.button("🔄 手动刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.caption("💡 数据每 30 秒自动刷新一次")

        return days, statuses, stages, selected_batch_key

# ============================================================
# 9. KPI 指标卡片
# ============================================================
def render_kpi_cards(df_today):
    """渲染顶部 4 个 KPI 指标卡（基于今日数据）。"""
    col1, col2, col3, col4 = st.columns(4)
    
    total = len(df_today)
    success = len(df_today[df_today["status"] == "success"]) if total > 0 else 0
    failed = len(df_today[df_today["status"] == "failed"]) if total > 0 else 0
    
    if total > 0 and df_today["duration_seconds"].notna().any():
        avg_duration = df_today["duration_seconds"].mean()
    else:
        avg_duration = 0.0
    
    with col1:
        st.metric(label="📋 今日总任务数", value=total)
    
    with col2:
        st.metric(label="✅ 今日成功数", value=success)
    
    with col3:
        st.metric(label="❌ 今日失败数", value=failed)
    
    with col4:
        st.metric(label="⏱️ 今日平均耗时", value=f"{avg_duration:.1f}s")

# ============================================================
# 10. 图表区域
# ============================================================
def render_charts(df):
    """渲染左（柱状图：耗时 Top 10）右（饼图：阶段分布）两个图表。"""
    col_left, col_right = st.columns(2)
    
    # --- 左图：耗时最长 Top 10 ---
    with col_left:
        st.subheader("⏱️ 耗时最长 Top 10 任务")
        if df.empty:
            st.info("暂无数据")
        else:
            # 先取 Top 10（按耗时），再按阶段序号从小到大排序
            df_top10 = df.nlargest(10, "duration_seconds")
            df_sorted = df_top10.sort_values("stage")
            
            fig_bar = px.bar(
                df_sorted,
                x="stage_name",
                y="duration_seconds",
                color="status",
                color_discrete_map=STATUS_COLORS,
                labels={
                    "stage_name": "阶段",
                    "duration_seconds": "耗时 (秒)",
                    "status": "状态",
                },
                hover_data={
                    "task_display_name": True,  # 此时为程序名
                    "duration_seconds": ":.1f",
                    "stage_name": False,
                },
            )
            fig_bar.update_layout(
                xaxis_tickangle=-45,
                height=400,
                margin=dict(b=120),
                showlegend=True,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e6edf3",
            )
            st.plotly_chart(fig_bar, use_container_width=True)
    
    # --- 右图：各阶段任务数量分布（环形图）---
    with col_right:
        st.subheader("📊 各阶段任务数量分布")
        if df.empty:
            st.info("暂无数据")
        else:
            stage_counts = df.groupby("stage_name").size().reset_index(name="count")
            fig_pie = px.pie(
                stage_counts,
                values="count",
                names="stage_name",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3,
            )
            fig_pie.update_traces(
                textposition="inside",
                textinfo="label+value+percent",
                marker_line_color="#0d1117",
                marker_line_width=1,
            )
            fig_pie.update_layout(
                height=400,
                showlegend=True,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="#e6edf3",
                annotations=[
                    dict(
                        text=f"总计<br><b>{len(df)}</b>",
                        x=0.5,
                        y=0.5,
                        font_size=16,
                        font_color="#e6edf3",
                        showarrow=False,
                    )
                ],
            )
            st.plotly_chart(fig_pie, use_container_width=True)

# ============================================================
# 11. 任务明细表
# ============================================================
def render_data_table(df):
    """渲染筛选后的任务明细表。"""
    st.subheader("📋 任务执行明细")
    
    if df.empty:
        st.info("当前筛选条件下暂无数据，请调整筛选条件或检查 ETL 任务是否已运行。")
        return
    
    # 构建展示用 DataFrame
    display_df = df.copy()
    
    # 按阶段序号从小到大排序
    display_df = display_df.sort_values("stage")
    
    display_df["开始时间"] = display_df["start_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    display_df["数据日期"] = display_df["data_date"].apply(
        lambda x: str(x)[:10] if pd.notna(x) else "—"
    )
    display_df["批次"] = display_df["batch_id"].apply(
        lambda x: (x[:16] + "..") if pd.notna(x) and len(str(x)) > 18 else (str(x)[:18] if pd.notna(x) else "—")
    )
    display_df["耗时"] = display_df["duration_seconds"].apply(
        lambda x: f"{x:.1f}s" if pd.notna(x) else "N/A"
    )
    display_df["状态"] = display_df["status"].map(STATUS_EMOJI)
    display_df["影响行数"] = display_df["rows_affected"].apply(
        lambda x: f"{int(x):,}" if pd.notna(x) else "N/A"
    )
    
    display_df = display_df.rename(
        columns={
            "stage_name": "阶段",
            "task_display_name": "程序名",  # 修改列标签为“程序名”
        }
    )
    
    display_df = display_df[
        ["数据日期", "批次", "阶段", "程序名", "开始时间", "耗时", "影响行数", "状态"]
    ]
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=400,
    )

# ============================================================
# 12. 详情查看（下拉选择 + 展开面板）
# ============================================================
def render_detail_panel(df, engine):
    """渲染任务详情查看区域（含同任务历史执行列表）。"""
    st.subheader(" 任务详情查看")

    if df.empty:
        st.info("暂无可查看详情的任务。")
        return

    # 构建下拉选项，使用程序名显示
    options = []
    id_map = {}
    for _, row in df.iterrows():
        label = f"ID {int(row['id'])} - {row['task_display_name']} [{row['stage_name']}]"
        options.append(label)
        id_map[label] = row["id"]

    selected_label = st.selectbox("选择任务 ID 查看详情", options=options)

    if selected_label:
        selected_id = id_map[selected_label]
        task = df[df["id"] == selected_id].iloc[0]

        with st.expander(
            f"📌 详情 —— {task['task_display_name']} ({task['stage_name']})",
            expanded=True,
        ):
            # 基础指标（增加批次列）
            info_cols = st.columns(6)
            info_cols[0].metric(
                "数据日期",
                str(task.get("data_date"))[:10] if pd.notna(task.get("data_date")) else "—"
            )
            info_cols[1].metric("阶段", task['stage_name'])
            info_cols[2].metric(
                "状态",
                STATUS_EMOJI.get(task["status"], str(task["status"]))
            )
            info_cols[3].metric(
                "耗时",
                f"{task['duration_seconds']:.1f}s" if pd.notna(task['duration_seconds']) else "N/A"
            )
            info_cols[4].metric(
                "影响行数",
                int(task["rows_affected"]) if pd.notna(task["rows_affected"]) else "N/A"
            )
            bid = task.get("batch_id", "")
            info_cols[5].metric(
                "批次",
                (bid[:14] + "..") if pd.notna(bid) and len(str(bid)) > 16 else (str(bid)[:16] if pd.notna(bid) else "—")
            )

            st.divider()

            # 状态消息
            status = task["status"]
            if status == "failed":
                error_msg = task.get("error_message") or "未记录错误信息"
                st.error(f"❌ **任务执行失败**\n\n```\n{error_msg}\n```")
                if pd.notna(task.get("exit_code")):
                    st.caption(f"Exit Code: {int(task['exit_code'])}")
            elif status == "success":
                st.success("✅ 任务执行成功，数据已正常入库。")
            elif status == "running":
                st.info("🔄 任务正在运行中，请等待完成...")
            elif status == "skipped":
                st.warning("⏭️ 任务已被跳过。")
            elif status == "not_started":
                st.info("⏸️ 任务尚未开始执行。")

            # 额外指标（JSONB 字段）
            extra = task.get("extra_metrics")
            if extra and isinstance(extra, dict) and len(extra) > 0:
                st.markdown("##### 📈 额外指标 (extra_metrics)")
                st.json(extra)

            # --- 同任务历史执行记录 ---
            st.divider()
            task_name = task["task_name"]
            try:
                # 加载最近 7 天全部状态的任务（不限制阶段）
                history_df = load_task_data(engine, 7, ALL_STATUSES)
                same_task = history_df[history_df["task_name"] == task_name].copy()
                same_task = same_task.sort_values("start_time", ascending=False)

                if len(same_task) > 1:
                    st.markdown(f"##### 📜 同任务「{task.get('task_display_name', task_name)}」历史执行 ({len(same_task)} 次)")

                    hist_display = same_task.copy()
                    hist_display["开始时间"] = hist_display["start_time"].dt.strftime("%m-%d %H:%M")
                    hist_display["批次"] = hist_display["batch_id"].apply(
                        lambda x: (x[:12] + "..") if pd.notna(x) and len(str(x)) > 14 else (str(x)[:14] if pd.notna(x) else "—")
                    )
                    hist_display["状态"] = hist_display["status"].map(STATUS_EMOJI)
                    hist_display["耗时"] = hist_display["duration_seconds"].apply(
                        lambda x: f"{x:.0f}s" if pd.notna(x) else "N/A"
                    )

                    st.dataframe(
                        hist_display[["开始时间", "批次", "状态", "耗时", "影响行数"]],
                        use_container_width=True,
                        hide_index=True,
                        height=min(40 * (len(same_task) + 1), 200),
                    )
                else:
                    st.caption(f"📜 同任务仅 1 条记录，无更多历史。")
            except Exception:
                st.caption("⚠️ 历史数据加载失败")

# ============================================================
# 13. 主程序
# ============================================================
def main():
    st.title("📊 ETL 全流程监控仪表盘")
    st.caption(
        f"量化交易系统数据管道监控 · 共 11 个阶段 · "
        f"最后刷新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    # --- 初始化数据库连接 ---
    engine = get_engine()

    # --- 侧边栏筛选 ---
    days, statuses, stages, batch_filter = render_sidebar(engine)

    # 校验筛选条件
    if not statuses:
        st.warning("⚠️ 请至少选择一个任务状态。")
        st.stop()
    if not stages:
        st.warning("⚠️ 请至少选择一个执行阶段。")
        st.stop()

    # --- 加载数据（不再依赖数据库 stage 字段，由 TASK_STAGE_MAP 统一映射）---
    try:
        with st.spinner("正在加载数据..."):
            df = load_task_data(engine, days, statuses, batch_filter=batch_filter)
    except ProgrammingError as e:
        error_str = str(e.orig) if hasattr(e, "orig") and e.orig else str(e)
        if "does not exist" in error_str.lower():
            st.error("❌ **数据库表 `task_run_log` 不存在！**\n\n请先在 PostgreSQL 中创建该表。")
        else:
            st.error(f"❌ SQL 执行错误：\n\n```\n{e}\n```")
        st.stop()
    except SQLAlchemyError as e:
        st.error(
            f"🚫 **数据库连接失败！**\n\n"
            f"请检查 `.env` 文件中的数据库配置是否正确。\n\n"
            f"错误详情：\n```\n{e}\n```"
        )
        st.stop()
    except Exception as e:
        st.error(f"🚫 **发生未知错误：**\n\n```\n{e}\n```")
        st.stop()
    
    # --- 在 pandas 中应用阶段筛选（基于标准化后的 stage）---
    if stages != list(STAGE_NAMES.keys()):
        df = df[df['stage'].isin(stages)]

    # --- 今日数据（用于 KPI 卡片，始终使用最新有效批次去重，全部阶段）---
    try:
        df_today = load_task_data(engine, 1, ALL_STATUSES, batch_filter="__latest__")
    except Exception:
        df_today = pd.DataFrame()
    
    # --- 渲染界面 ---
    render_kpi_cards(df_today)
    st.divider()
    render_charts(df)
    st.divider()
    render_data_table(df)
    st.divider()
    render_detail_panel(df, engine)

if __name__ == "__main__":
    main()
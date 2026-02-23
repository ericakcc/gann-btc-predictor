"""
江恩比特幣轉折點預測 — Streamlit 互動式儀表板

啟動方式：
    uv run streamlit run app/dashboard.py
"""

import sys
import math
from pathlib import Path
from datetime import datetime, timedelta

import plotly.graph_objects as go
import streamlit as st

# 將 scripts/ 加入 import 路徑，以便重用 gann_calc.py 的函數
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import gann_calc  # noqa: E402

# ── 重用的函數別名 ──────────────────────────────────────────────────
_fetch_price = gann_calc.fetch_current_price
_fetch_ohlc = gann_calc.fetch_ohlc_history
_detect_pivots = gann_calc.detect_pivots
_gen_projections = gann_calc.generate_projections
_detect_confluences = gann_calc.detect_confluences
_sq9 = gann_calc.calculate_square_of_nine
_harmonic = gann_calc.calculate_harmonic_levels
_pct_levels = gann_calc.calculate_percentage_levels
_seasonal = gann_calc.get_seasonal_dates
_seasonal_enhance = gann_calc.check_seasonal_enhancement


# ── 共用工具函數 ───────────────────────────────────────────────────
def days_from_today(date_str: str, today) -> int:
    """回傳 date_str 距今天數（正=未來，負=過去）。"""
    return (datetime.strptime(date_str, "%Y-%m-%d").date() - today).days


def format_days_label(days: int) -> str:
    """將天數差格式化為人類可讀標籤。"""
    if days == 0:
        return "今天"
    elif days > 0:
        label = f"距今 {days} 天後"
        if days >= 30:
            label += f"（約 {days // 30} 個月）"
        return label
    else:
        return f"{abs(days)} 天前"


# ── Streamlit 頁面設定 ─────────────────────────────────────────────
st.set_page_config(
    page_title="江恩 BTC 轉折點預測儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("江恩 BTC 轉折點預測儀表板")
st.caption("基於 W.D. Gann 時間週期理論分析比特幣轉折時間點")


# ── 快取包裝 ──────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def cached_fetch_price() -> float:
    """快取即時 BTC 價格（5 分鐘 TTL）。"""
    try:
        return _fetch_price()
    except SystemExit:
        st.error("無法取得即時價格，請改用手動模式")
        return 0.0


@st.cache_data(ttl=300)
def cached_fetch_ohlc(days: int) -> list[dict]:
    """快取 OHLC 歷史資料（5 分鐘 TTL）。"""
    try:
        return _fetch_ohlc(days)
    except SystemExit:
        st.error("無法取得歷史資料，請改用手動模式")
        return []


# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("分析參數")

    mode = st.radio("模式", ["自動（從 Binance 抓取）", "手動輸入"])

    st.divider()

    if mode == "自動（從 Binance 抓取）":
        lookback = st.slider("轉折偵測 Lookback 天數", 7, 30, 14)
        min_change = st.slider("最小波動幅度 (%)", 5.0, 30.0, 10.0, step=0.5)
        history_days = st.slider("歷史資料天數", 180, 1000, 730, step=30)
        pred_range = st.slider("預測範圍（天）", 90, 720, 360, step=30)
        manual_pivots_raw = ""
        manual_price = 0.0
    else:
        st.markdown("**轉折點（每行一個，格式：YYYY-MM-DD high/low 價格）**")
        manual_pivots_raw = st.text_area(
            "轉折點",
            value="2024-11-10 high 93000\n2024-01-23 low 38500",
            height=120,
            label_visibility="collapsed",
        )
        manual_price = st.number_input("目前 BTC 價格（USD）", value=95000.0, step=100.0)
        pred_range = st.slider("預測範圍（天）", 90, 720, 360, step=30)
        lookback = 14
        min_change = 10.0
        history_days = 730

    run_btn = st.button("執行分析", type="primary", use_container_width=True)


# ── Session State 初始化 ──────────────────────────────────────────
if "result" not in st.session_state:
    st.session_state.result = None


# ── 分析執行 ──────────────────────────────────────────────────────
def parse_manual_pivots(raw: str) -> list[dict]:
    """解析手動輸入的轉折點文字。"""
    pivots = []
    for line in raw.strip().splitlines():
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        try:
            pivots.append({
                "date": parts[0],
                "type": parts[1].lower(),
                "price": float(parts[2]),
            })
        except (ValueError, IndexError):
            st.warning(f"無法解析行：{line}")
    return pivots


def run_analysis(
    mode: str,
    lookback: int,
    min_change: float,
    history_days: int,
    pred_range: int,
    manual_pivots_raw: str,
    manual_price: float,
) -> dict | None:
    """執行完整的江恩分析並回傳結果字典。"""
    today = datetime.now().date()
    end_date = today + timedelta(days=pred_range)

    with st.spinner("分析中..."):
        if mode == "自動（從 Binance 抓取）":
            current_price = cached_fetch_price()
            if current_price == 0.0:
                return None
            ohlc = cached_fetch_ohlc(history_days)
            if not ohlc:
                return None
            pivots = _detect_pivots(ohlc, lookback, min_change)
        else:
            current_price = manual_price
            ohlc = cached_fetch_ohlc(history_days)  # 仍需要 K 線顯示
            pivots = parse_manual_pivots(manual_pivots_raw)

        if not pivots:
            st.error("未找到任何轉折點，請調整參數或改用手動模式")
            return None

        projections = _gen_projections(pivots, today, end_date)
        confluences = _detect_confluences(projections)
        seasonal_dates = _seasonal(today, end_date)
        confluences = _seasonal_enhance(confluences, seasonal_dates)
        sq9_levels = _sq9(current_price)
        harmonic_levels = _harmonic(current_price)
        pct_level_list = _pct_levels(pivots, current_price)

    return {
        "today": today,
        "end_date": end_date,
        "current_price": current_price,
        "ohlc": ohlc,
        "pivots": pivots,
        "projections": projections,
        "confluences": confluences,
        "seasonal_dates": seasonal_dates,
        "sq9_levels": sq9_levels,
        "harmonic_levels": harmonic_levels,
        "pct_levels": pct_level_list,
        "lookback": lookback,
        "min_change": min_change,
    }


if run_btn:
    result = run_analysis(
        mode, lookback, min_change, history_days, pred_range,
        manual_pivots_raw, manual_price
    )
    st.session_state.result = result

result = st.session_state.result

if result is None:
    st.info("請在左側設定參數，然後點擊「執行分析」")
    st.stop()


# ── 頂部摘要資訊 ──────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("BTC 即時價格", f"${result['current_price']:,.0f}")
col2.metric("偵測到的轉折點", len(result["pivots"]))
col3.metric("匯聚點數量", len(result["confluences"]))
if result["confluences"]:
    top = result["confluences"][0]
    col4.metric("最強匯聚日", f"{top['date']} (分數 {top['score']})")
else:
    col4.metric("最強匯聚日", "無")


# ── 5 個分頁 ──────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 K 線與轉折點偵測",
    "🕸️ 時間週期投射地圖",
    "🔮 匯聚分數時間線",
    "📐 價格支撐/阻力",
    "📚 方法論說明",
])


# ══════════════════════════════════════════════════════════════════
# Tab 1：K 線與轉折點偵測
# ══════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("K 線圖與轉折點標記")

    ohlc = result["ohlc"]
    pivots = result["pivots"]

    if not ohlc:
        st.warning("無法載入歷史 K 線資料")
    else:
        # 準備 K 線資料
        dates = [d["date"] for d in ohlc]
        opens = [d["open"] for d in ohlc]
        highs = [d["high"] for d in ohlc]
        lows = [d["low"] for d in ohlc]
        closes = [d["close"] for d in ohlc]

        # 分離高低轉折點
        high_pivots = [p for p in pivots if p["type"] == "high"]
        low_pivots = [p for p in pivots if p["type"] == "low"]

        fig = go.Figure()

        # Candlestick
        fig.add_trace(go.Candlestick(
            x=dates,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name="BTC/USDT",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ))

        # 高轉折點 ▼（標在 K 線上方）
        if high_pivots:
            fig.add_trace(go.Scatter(
                x=[p["date"] for p in high_pivots],
                y=[p["price"] * 1.02 for p in high_pivots],
                mode="markers+text",
                marker=dict(symbol="triangle-down", size=12, color="#ef5350"),
                text=[f"H ${p['price']:,.0f}" for p in high_pivots],
                textposition="top center",
                textfont=dict(size=9, color="#ef5350"),
                name="高轉折點",
                hovertemplate=(
                    "<b>高轉折點</b><br>"
                    "日期: %{x}<br>"
                    "價格: $%{customdata:,.0f}<extra></extra>"
                ),
                customdata=[p["price"] for p in high_pivots],
            ))

        # 低轉折點 ▲（標在 K 線下方）
        if low_pivots:
            fig.add_trace(go.Scatter(
                x=[p["date"] for p in low_pivots],
                y=[p["price"] * 0.98 for p in low_pivots],
                mode="markers+text",
                marker=dict(symbol="triangle-up", size=12, color="#26a69a"),
                text=[f"L ${p['price']:,.0f}" for p in low_pivots],
                textposition="bottom center",
                textfont=dict(size=9, color="#26a69a"),
                name="低轉折點",
                hovertemplate=(
                    "<b>低轉折點</b><br>"
                    "日期: %{x}<br>"
                    "價格: $%{customdata:,.0f}<extra></extra>"
                ),
                customdata=[p["price"] for p in low_pivots],
            ))

        fig.update_layout(
            height=550,
            xaxis_rangeslider_visible=False,
            xaxis_title="日期",
            yaxis_title="價格 (USD)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=40, b=40),
        )

        st.plotly_chart(fig, width="stretch")

        st.caption(
            f"**Lookback 窗口**：前後各 {result['lookback']} 天比較，"
            f"若為最高/最低即為轉折。"
            f"**最小波動門檻**：{result['min_change']}%。"
            f"共偵測到 **{len(pivots)}** 個顯著轉折點。"
        )

    # 轉折點清單表格
    if pivots:
        st.subheader("轉折點清單")
        pivot_rows = [
            {
                "日期": p["date"],
                "類型": "高點" if p["type"] == "high" else "低點",
                "價格 (USD)": f"${p['price']:,.0f}",
            }
            for p in pivots
        ]
        st.dataframe(pivot_rows, width="stretch", hide_index=True)


# ══════════════════════════════════════════════════════════════════
# Tab 2：時間週期投射地圖
# ══════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("時間週期投射地圖")

    with st.expander("📖 這個分頁在看什麼？"):
        st.markdown("""
        **每一橫列 = 一個歷史轉折點**，每個點 = 從該轉折點投射出的一個未來到期日。

        | 顏色 | 週期類型 |
        |------|---------|
        | 🟠 橘色 | 標準週期（30/60/90/180/360 天等） |
        | 🔵 藍色 | 平方週期（7²/8²/9²… 天） |
        | 🟢 綠色 | 費波那契週期（21/34/55/89/144… 天） |

        **點越密集的日期 = 匯聚越強 = 變盤機率越高。**
        下方長條圖顯示每個匯聚群組的強度分數（🔴 ≥5 強 | 🟠 ≥3 中 | 灰 弱）。黃色垂直線 = 今天。
        """)

    projections = result["projections"]
    today = result["today"]
    today_str = today.isoformat()
    confluences = result["confluences"]

    if not projections:
        st.warning("無投射資料")
    else:
        from plotly.subplots import make_subplots

        # 類型 → 顏色映射
        color_map = {"標準": "#f97316", "平方": "#3b82f6", "費波那契": "#22c55e"}
        symbol_map = {"high": "circle", "low": "diamond"}

        def pivot_type_from_source(source: str) -> str:
            return "high" if "high" in source else "low"

        def short_pivot_label(source: str) -> str:
            """'2024-11-10 high 93000' → '24-11-10 H'"""
            parts = source.split()
            if len(parts) >= 2:
                date_short = parts[0][2:] if len(parts[0]) == 10 else parts[0]
                ptype = "H" if "high" in parts[1] else "L"
                return f"{date_short} {ptype}"
            return source[:12]

        # 取得唯一轉折點來源，按日期倒序（最新在上）
        unique_sources_ordered = []
        seen_sources: set[str] = set()
        for p in sorted(projections, key=lambda x: x["source"], reverse=True):
            src = p["source"]
            if src not in seen_sources:
                seen_sources.add(src)
                unique_sources_ordered.append(src)
        # 簡短標籤映射
        source_label_map = {s: short_pivot_label(s) for s in unique_sources_ordered}
        unique_labels = [source_label_map[s] for s in unique_sources_ordered]

        # 匯聚分數資料（用於下層 bar）
        bar_dates = [c["date"] for c in confluences]
        bar_scores = [c["score"] for c in confluences]

        # 建立雙層子圖
        fig2 = make_subplots(
            rows=2, cols=1,
            row_heights=[0.75, 0.25],
            shared_xaxes=True,
            vertical_spacing=0.05,
        )

        # ── 上層：散點（Y = 轉折點縮短標籤） ──
        for cat, color in color_map.items():
            cat_data = [p for p in projections if p["category"] == cat]
            if not cat_data:
                continue
            for ptype, symbol in symbol_map.items():
                sub = [p for p in cat_data if pivot_type_from_source(p["source"]) == ptype]
                if not sub:
                    continue
                hover_custom = []
                for p in sub:
                    d = days_from_today(p["date"], today)
                    days_label = format_days_label(d)
                    hover_custom.append([
                        p["source"], p["category"], p["days"],
                        days_label, source_label_map[p["source"]]
                    ])
                fig2.add_trace(go.Scatter(
                    x=[p["date"] for p in sub],
                    y=[source_label_map[p["source"]] for p in sub],
                    mode="markers",
                    marker=dict(symbol=symbol, size=9, color=color, opacity=0.75),
                    name=f"{cat} ({'高點' if ptype == 'high' else '低點'})",
                    hovertemplate=(
                        "<b>%{customdata[4]}</b><br>"
                        "投射日：%{x}<br>"
                        "週期天數：%{customdata[2]} 天<br>"
                        "類型：%{customdata[1]}<br>"
                        "<b>%{customdata[3]}</b><extra></extra>"
                    ),
                    customdata=hover_custom,
                ), row=1, col=1)

        # Y 軸排序（最新轉折點在上）
        fig2.update_yaxes(
            categoryorder="array",
            categoryarray=unique_labels[::-1],
            row=1, col=1,
        )

        # ── ±3 天視窗帶（分數 ≥ 3 的匯聚日） ──
        from datetime import timedelta

        top_conf_band = [c for c in confluences if c["score"] >= 3]
        for c in top_conf_band:
            d_center = datetime.strptime(c["date"], "%Y-%m-%d")
            x0 = (d_center - timedelta(days=3)).strftime("%Y-%m-%d")
            x1 = (d_center + timedelta(days=3)).strftime("%Y-%m-%d")
            alpha = min(0.08 + 0.04 * (c["score"] - 3), 0.20)
            fig2.add_shape(
                type="rect",
                x0=x0, x1=x1, y0=0, y1=1,
                xref="x", yref="y domain",
                fillcolor=f"rgba(239,83,80,{alpha:.2f})",
                line_width=0, layer="below",
                row=1, col=1,
            )
            fig2.add_annotation(
                x=c["date"], y=0.99,
                yref="y domain",
                text=f"分數 {c['score']}",
                showarrow=False,
                font=dict(size=8, color="#ef5350"),
                xanchor="center", yanchor="top",
                row=1, col=1,
            )

        # ── 下層：匯聚分數長條圖 ──
        bar_colors_conf = [
            "#ef5350" if s >= 5 else ("#ffa726" if s >= 3 else "#90a4ae")
            for s in bar_scores
        ]
        bar_hover = [
            f"{format_days_label(days_from_today(c['date'], today))}<br>分數：{c['score']}"
            for c in confluences
        ]
        fig2.add_trace(go.Bar(
            x=bar_dates,
            y=bar_scores,
            marker_color=bar_colors_conf,
            name="匯聚分數",
            showlegend=False,
            hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>",
            customdata=bar_hover,
        ), row=2, col=1)

        # ── 今日垂直線 ──
        for row_idx in [1, 2]:
            fig2.add_shape(
                type="line",
                x0=today_str, x1=today_str,
                y0=0, y1=1,
                yref=f"y{'' if row_idx == 1 else '2'} domain",
                xref="x",
                line=dict(color="#f59e0b", width=2, dash="solid"),
            )
        fig2.add_annotation(
            x=today_str, y=1,
            yref="y domain",
            text="今日",
            showarrow=False,
            font=dict(size=10, color="#f59e0b"),
            xanchor="left", yanchor="bottom",
            row=1, col=1,
        )

        fig2.update_layout(
            height=580,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=40, b=40),
            xaxis2_title="投射日期",
            yaxis_title="轉折點來源",
            yaxis2_title="匯聚分數",
        )

        st.plotly_chart(fig2, width="stretch")

        colA, colB, colC = st.columns(3)
        colA.markdown("**顏色**：🟠 標準 | 🔵 平方 | 🟢 費波那契")
        colB.markdown("**形狀**：圓 = 來自高點 | 菱 = 來自低點")
        colC.markdown(f"**共 {len(projections)} 個投射點**")


# ══════════════════════════════════════════════════════════════════
# Tab 3：匯聚分數時間線（主頁）
# ══════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("匯聚分數時間線")

    st.info(
        "**匯聚分數** = 幾條獨立江恩週期在同一時段（±3天）到期。"
        "分數越高，變盤機率越大。🔴 ≥5 強信號 | 🟡 ≥3 中等信號 | ⚪ 弱信號。"
        "🌟 = 季節日期（春分/夏至/秋分/冬至）強化。"
    )

    confluences = result["confluences"]
    seasonal_dates = result["seasonal_dates"]
    today = result["today"]
    today_str = today.isoformat()

    if not confluences:
        st.warning("無匯聚點資料")
    else:
        conf_dates = [c["date"] for c in confluences]
        conf_scores = [c["score"] for c in confluences]
        conf_signals = [c["signal"] for c in confluences]
        conf_seasonal = [c.get("seasonal") or "" for c in confluences]

        # 柱子顏色
        bar_colors = []
        for score in conf_scores:
            if score >= 5:
                bar_colors.append("#ef5350")
            elif score >= 3:
                bar_colors.append("#ffa726")
            else:
                bar_colors.append("#90a4ae")

        # hover 加「距今幾天」
        hover_customdata = []
        for c, s in zip(confluences, conf_seasonal):
            d = days_from_today(c["date"], today)
            days_label = format_days_label(d)
            seasonal_part = f"季節強化：{s}" if s else "無季節強化"
            hover_customdata.append(f"{days_label}<br>{seasonal_part}")

        fig3 = go.Figure()

        fig3.add_trace(go.Bar(
            x=conf_dates,
            y=conf_scores,
            marker_color=bar_colors,
            name="匯聚分數",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "匯聚分數：%{y}<br>"
                "%{customdata}<extra></extra>"
            ),
            customdata=hover_customdata,
        ))

        # 今日標記
        if today_str in conf_dates:
            fig3.add_shape(
                type="line",
                x0=today_str, x1=today_str,
                y0=0, y1=1,
                yref="paper",
                line=dict(color="#f59e0b", width=2, dash="solid"),
            )
            fig3.add_annotation(
                x=today_str, y=1, yref="paper",
                text="今日",
                showarrow=False,
                font=dict(size=10, color="#f59e0b"),
                xanchor="left", yanchor="bottom",
            )
        else:
            # 找最近的 conf_date
            future_dates = [d for d in conf_dates if d >= today_str]
            if future_dates:
                nearest = min(future_dates)
                fig3.add_annotation(
                    x=nearest, y=max(conf_scores) * 0.9,
                    text="← 今日在此左側",
                    showarrow=False,
                    font=dict(size=9, color="#f59e0b"),
                    xanchor="right",
                )

        # 頂部標記前 3 個最高分
        top3 = sorted(confluences, key=lambda x: -x["score"])[:3]
        for c in top3:
            seasonal_icon = "🌟" if c.get("seasonal") else ""
            d = days_from_today(c["date"], today)
            days_label = format_days_label(d)
            fig3.add_annotation(
                x=c["date"],
                y=c["score"],
                text=f"{seasonal_icon}分數 {c['score']}<br>{days_label}",
                showarrow=True,
                arrowhead=2,
                ax=0,
                ay=-40,
                font=dict(size=10, color="#ef5350"),
                bgcolor="rgba(255,255,255,0.85)",
            )

        # 季節日期垂直標線
        for sd in seasonal_dates:
            if sd["date"] in conf_dates:
                continue
            fig3.add_shape(
                type="line",
                x0=sd["date"], x1=sd["date"],
                y0=0, y1=1,
                yref="paper",
                line=dict(dash="dot", color="#a855f7", width=1),
                opacity=0.5,
            )
            fig3.add_annotation(
                x=sd["date"],
                y=1,
                yref="paper",
                text=f"🌟{sd['event']}",
                showarrow=False,
                font=dict(size=9, color="#a855f7"),
                textangle=-45,
                xanchor="left",
                yanchor="bottom",
            )

        # 顏色參考線
        fig3.add_hline(y=5, line_dash="dash", line_color="#ef5350", opacity=0.4,
                       annotation_text="強 (≥5)", annotation_position="right")
        fig3.add_hline(y=3, line_dash="dash", line_color="#ffa726", opacity=0.4,
                       annotation_text="中 (≥3)", annotation_position="right")

        fig3.update_layout(
            height=450,
            xaxis_title="日期",
            yaxis_title="匯聚分數",
            showlegend=False,
            margin=dict(t=40, b=80, r=80),
        )

        st.plotly_chart(fig3, width="stretch")

        # 匯聚點明細表
        st.subheader("Top 匯聚點明細")
        for i, c in enumerate(confluences):
            score_emoji = "🔴" if c["score"] >= 5 else ("🟡" if c["score"] >= 3 else "⚪")
            seasonal_mark = f" 🌟{c['seasonal']}" if c.get("seasonal") else ""
            d = days_from_today(c["date"], today)
            days_label = format_days_label(d)

            with st.expander(
                f"{score_emoji} {c['date']}（{days_label}）— 分數 {c['score']} ({c['signal']}){seasonal_mark}"
            ):
                for contrib in c["contributions"]:
                    st.markdown(f"- {contrib}")


# ══════════════════════════════════════════════════════════════════
# Tab 4：價格支撐/阻力總覽
# ══════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("價格支撐 / 阻力總覽")

    with st.expander("📖 這個分頁在看什麼？"):
        st.markdown("""
        以**近 90 天 K 線**為底圖，疊加三種方法計算的支撐/阻力水平線：

        | 顏色 | 方法 | 說明 |
        |------|------|------|
        | 🟠 橘色 | 九宮格（Square of Nine） | 以現價平方根計算 Gann 角度位階 |
        | 🔵 藍色 | 音階比率（Harmonic） | 源自十二平均律的頻率比率位階 |
        | 🔴🟢 紅/綠 | 百分比分割（1/8 法則） | 從轉折點計算重要回撤比例位置 |

        **線越粗 = 距現價越近**；僅顯示現價 ±15% 以內的水平線。
        """)

    current_price = result["current_price"]
    sq9_levels = result["sq9_levels"]
    harmonic_levels = result["harmonic_levels"]
    pct_level_list = result["pct_levels"]
    ohlc_all = result["ohlc"]

    # 取近 90 天 OHLC
    cutoff_90 = (result["today"] - timedelta(days=90)).isoformat()
    recent_ohlc = [d for d in ohlc_all if d["date"] >= cutoff_90] if ohlc_all else []

    # 彙整所有水平線（過濾至 ±15%）
    price_low = current_price * 0.85
    price_high = current_price * 1.15
    all_levels: list[dict] = []

    for row in sq9_levels:
        for level, sr_label, angle in [
            (row["resistance_1"], "R1", row["angle"]),
            (row["resistance_2"], "R2", row["angle"]),
            (row["support_1"], "S1", row["angle"]),
            (row["support_2"], "S2", row["angle"]),
        ]:
            if price_low <= level <= price_high:
                pct = (level - current_price) / current_price * 100
                all_levels.append({
                    "level": level,
                    "source": f"九宮格 {angle}°",
                    "label": f"九宮格 {angle}° {sr_label}",
                    "sr": "阻力" if level > current_price else "支撐",
                    "color": "#f97316" if level > current_price else "#22c55e",
                    "dash": "dot",
                    "pct": pct,
                })

    for h in harmonic_levels:
        for level, sr_label in [
            (h["resistance"], "R"),
            (h["support"], "S"),
        ]:
            if price_low <= level <= price_high:
                pct = (level - current_price) / current_price * 100
                all_levels.append({
                    "level": level,
                    "source": f"音階 {h['interval']}",
                    "label": f"音階 {h['interval']} {sr_label}",
                    "sr": "阻力" if level > current_price else "支撐",
                    "color": "#3b82f6" if level > current_price else "#818cf8",
                    "dash": "longdash",
                    "pct": pct,
                })

    for pl in pct_level_list[:10]:
        level = pl["level"]
        if price_low <= level <= price_high:
            pct = (level - current_price) / current_price * 100
            all_levels.append({
                "level": level,
                "source": pl.get("source", "")[:25],
                "label": pl["method"],
                "sr": "阻力" if level > current_price else "支撐",
                "color": "#ef5350" if level > current_price else "#4caf50",
                "dash": "dash",
                "pct": pct,
            })

    # ── 繪製圖表 ──
    fig4 = go.Figure()

    # 底圖：K 線（近 90 天）
    if recent_ohlc:
        fig4.add_trace(go.Candlestick(
            x=[d["date"] for d in recent_ohlc],
            open=[d["open"] for d in recent_ohlc],
            high=[d["high"] for d in recent_ohlc],
            low=[d["low"] for d in recent_ohlc],
            close=[d["close"] for d in recent_ohlc],
            name="BTC/USDT",
            showlegend=False,
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ))
    else:
        st.warning("手動模式下 K 線資料不可用，僅顯示水平線示意圖。")

    # 水平線
    plotted_labels: set[str] = set()
    for lv in sorted(all_levels, key=lambda x: abs(x["pct"])):
        line_width = max(0.5, 2.5 - abs(lv["pct"]) * 0.1)
        pct_str = f"+{lv['pct']:.1f}%" if lv["pct"] > 0 else f"{lv['pct']:.1f}%"
        leg_label = lv["label"]
        show_legend = leg_label not in plotted_labels
        plotted_labels.add(leg_label)
        fig4.add_hline(
            y=lv["level"],
            line_dash=lv["dash"],
            line_color=lv["color"],
            line_width=line_width,
            opacity=0.75,
            annotation_text=f"{lv['label']} ({pct_str})",
            annotation_position="right",
            annotation_font_size=9,
        )

    # 現價黃線
    fig4.add_hline(
        y=current_price,
        line_width=3,
        line_color="#f59e0b",
        annotation_text=f"現價 ${current_price:,.0f}",
        annotation_position="right",
        annotation_font_size=11,
        annotation_font_color="#f59e0b",
    )

    # Y 軸範圍：±20%
    fig4.update_layout(
        height=600,
        xaxis_rangeslider_visible=False,
        xaxis_title="日期",
        yaxis=dict(title="價格 (USD)", range=[current_price * 0.80, current_price * 1.20]),
        margin=dict(t=40, b=20, l=60, r=240),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    st.plotly_chart(fig4, width="stretch")

    # ── 統一合併價位表 ──
    if all_levels:
        st.subheader("支撐 / 阻力價位表（距現價由近至遠）")
        merged_rows = []
        for lv in sorted(all_levels, key=lambda x: abs(x["pct"])):
            pct_str = f"+{lv['pct']:.1f}%" if lv["pct"] > 0 else f"{lv['pct']:.1f}%"
            merged_rows.append({
                "類型": lv["sr"],
                "來源": lv["source"],
                "說明": lv["label"],
                "價位 (USD)": f"${lv['level']:,.0f}",
                "距現價": pct_str,
            })
        st.dataframe(merged_rows, width="stretch", hide_index=True)


# ══════════════════════════════════════════════════════════════════
# Tab 5：方法論說明
# ══════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("江恩分析方法論")

    with st.expander("步驟 1：江恩時間週期常數", expanded=True):
        st.markdown("""
        W.D. Gann 認為市場在特定的時間週期後會產生轉折。本工具使用三類週期：

        | 類型 | 週期天數 |
        |------|---------|
        | **標準週期** | 30, 45, 60, 72, 90, 120, 144, 150, 180, 210, 225, 240, 270, 300, 315, 330, 360, 720 |
        | **平方週期** | 49, 64, 81, 100, 121, 144, 169, 196, 225, 256, 289, 324, 361, 400 |
        | **費波那契週期** | 21, 34, 55, 89, 144, 233, 377 |

        **原理**：以每個歷史高低轉折點為起點，向未來投射各週期的到期日，
        形成「預期轉折窗口」。
        """)

    with st.expander("步驟 2：匯聚偵測算法"):
        st.markdown("""
        **匯聚（Confluence）**：多個不同週期的投射日期落在同一時間窗口內。

        **算法流程**：
        1. 將所有投射日期排序
        2. 使用滑動分組：若某投射日與群組中心相差 ≤ 3 天，歸入同組
        3. 計算每組的「獨立來源-週期對」數量 → 即**匯聚分數**
        4. 分數 ≥ 5：🔴 強信號 | 分數 ≥ 3：🟡 中等信號

        **± 3 天容差說明**：市場不會精確在某天變盤，±3 天為合理容差範圍。
        """)

        # 文字流程說明（三欄）
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("""
**① 各轉折點投射**

```
高點A（2025-06-01）
  + 90 天 → 2025-08-30
  + 144 天 → 2025-10-23
  + 233 天 → 2026-01-21

低點B（2025-08-15）
  + 45 天→ 2025-09-29
  + 180 天→ 2026-02-11
```
每個轉折點各自投射多個未來日期 ↓
""")
        with col_b:
            st.markdown("""
**② 投射日期落在同一窗口**

```
2026-02-28 ～ 2026-03-05
    ┌────────────────────┐
    │ 高點A +144d (Mar01) │ 🟠
    │ 低點B +180d (Mar01) │ 🔵
    │ 高點C +360d (Mar04) │ 🟠
    │ 低點A +233d (Mar03) │ 🟢
    └────────────────────┘
```
±3 天內的投射歸為同一群組 ↓
""")
        with col_c:
            st.markdown("""
**③ 計算匯聚分數**

```
群組中心：2026-03-02
獨立來源-週期對數：4

→ 匯聚分數 = 4
→ 🔴 強信號（≥5 極強）
```

分數 ≥ 5 → 🔴 強
分數 ≥ 3 → 🟡 中
分數 < 3 → ⚪ 弱
""")

    with st.expander("步驟 3：九宮格（Square of Nine）"):
        st.markdown("""
        **公式**：以目前價格的**平方根**為基準，加減 Gann 角度對應的增量。

        ```
        增量 = 角度 / 360 × 2
        阻力 = (√Price + 增量)²
        支撐 = (√Price - 增量)²
        ```

        **常用角度**：45° (×0.25)、90° (×0.5)、180° (×1.0)、270° (×1.5)、360° (×2.0)

        **範例**（BTC = $95,000）：
        - √95,000 ≈ 308.22
        - 45° 增量 = 0.25 → 阻力1 = (308.22 + 0.25)² ≈ $95,154
        - 45° 增量 = 0.25 → 支撐1 = (308.22 - 0.25)² ≈ $94,847
        """)

    with st.expander("步驟 4：季節強化規則"):
        st.markdown("""
        Gann 認為天文季節轉換點（春分、夏至、秋分、冬至）及其中間點，
        往往與市場重要轉折點吻合。

        **規則**：若匯聚點與季節日期相差 ≤ 5 天，則**加強信號**（🌟 標記）。

        | 季節日期 | 事件 |
        |---------|------|
        | 3/20 | 春分 |
        | 6/21 | 夏至 |
        | 9/22 | 秋分 |
        | 12/21 | 冬至 |
        | 2/4, 5/6, 8/6, 11/6 | 各季中間點 |
        """)

    with st.expander("步驟 5：音階比率（Harmonic Ratio）"):
        st.markdown(r"""
        **原理**：源自十二平均律，每個半音的頻率比率固定為 2^(1/12) ≈ 1.05946。

        Gann 認為價格的自然分割遵循音樂的和聲比率：

        ```
        半音比率 = 2^(1/12) ≈ 1.05946
        阻力 = Price × 比率^n
        支撐 = Price ÷ 比率^n
        ```

        | 層數 | 音程 | 比率 |
        |-----|------|------|
        | 1 | 半音 | 1.05946 |
        | 2 | 全音 | 1.12246 |
        | 3 | 小三度 | 1.18921 |
        | 4 | 大三度 | 1.25992 |
        """)

    with st.expander("步驟 6：百分比分割（1/8 法則）"):
        st.markdown("""
        **江恩 1/8 法則**：以重要高點或低點為基準，計算關鍵百分比位置。

        | 比例 | 說明 |
        |-----|------|
        | 8% (1/12) | 最小修正 |
        | 12.5% (1/8) | 小型回調 |
        | 25% (1/4) | 四分之一回撤 |
        | 33.3% (1/3) | 三分之一回撤 |
        | 50% (1/2) | **最重要**的半程回撤 |

        從高點向下回撤，或從低點向上反彈，這些比例對應的價格往往是強支撐/阻力。
        """)

    st.divider()
    st.markdown("""
    **完整分析流程**：
    1. 從歷史 K 線偵測顯著轉折點
    2. 從每個轉折點投射三類時間週期
    3. 偵測多週期匯聚，計算匯聚分數
    4. 季節日期強化匯聚信號
    5. 計算九宮格、音階比率、百分比分割提供價格參考

    > **免責聲明**：本工具僅供學習研究江恩理論，不構成任何投資建議。
    """)

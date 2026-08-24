"""
app.py
------
Streamlit dashboard for the NSE Momentum Screener.

Run
---
    streamlit run src/ui/app.py

Features
--------
  • Sidebar filters  (volume spike, 50-DMA, near 52w high, breakout, big mover,
                      min score slider, min volume ratio)
  • KPI cards         (total stocks, matches, avg score, avg vol ratio)
  • Sortable results  table with colour-coded signal columns
  • Price + Volume    chart for any selected stock
  • Score distribution histogram
  • Top-20 momentum   bar chart
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so `src.*` imports work when
# Streamlit launches the file directly (it doesn't use the package runner).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_RAW_DIR = _PROJECT_ROOT / "data" / "raw"
_EXPORTS_DIR = _PROJECT_ROOT / "data" / "exports"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="NSE Momentum Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Running momentum scan…", ttl=300)
def load_scan() -> pd.DataFrame:
    from src.screener.momentum_screener import run_scan
    return run_scan(data_dir=_RAW_DIR)


@st.cache_data(show_spinner="Loading price data…")
def load_ohlcv(symbol: str) -> pd.DataFrame:
    path = _RAW_DIR / f"{symbol}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------

st.sidebar.title("🔍 Filters")

with st.sidebar:
    st.markdown("**Signal filters**")
    f_volume_spike  = st.checkbox("Volume spike  (>2× avg)",      value=True)
    f_above_50dma   = st.checkbox("Above 50-day MA",               value=False)
    f_near_high     = st.checkbox("Near 52-week high  (≤5%)",      value=False)
    f_breakout      = st.checkbox("Breakout above resistance",     value=False)
    f_big_mover     = st.checkbox("Big mover  (|1D%| ≥ 8%)",      value=False)

    st.markdown("---")
    st.markdown("**Thresholds**")
    min_score       = st.slider("Min momentum score", 0, 100, 0, step=5)
    min_vol_ratio   = st.slider("Min volume ratio",   0.0, 20.0, 0.0, step=0.5)

    st.markdown("---")
    sort_col = st.selectbox(
        "Sort by",
        ["momentum_score", "pct_1d", "pct_5d", "pct_20d", "volume_ratio"],
        index=0,
    )
    top_n = st.slider("Rows to display", 10, 200, 50, step=10)

# ---------------------------------------------------------------------------
# Load + filter data
# ---------------------------------------------------------------------------

with st.spinner("Scanning 2,600+ stocks…"):
    df_all = load_scan()

df = df_all.copy()

if f_volume_spike:
    df = df[df["volume_spike"]]
if f_above_50dma:
    df = df[df["above_50dma"]]
if f_near_high:
    df = df[df["near_52w_high"]]
if f_breakout:
    df = df[df["breakout"]]
if f_big_mover:
    df = df[df["big_mover"]]
if min_score > 0:
    df = df[df["momentum_score"] >= min_score]
if min_vol_ratio > 0:
    df = df[df["volume_ratio"] >= min_vol_ratio]

df = df.sort_values(sort_col, ascending=False)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("📈 NSE Momentum Screener")
st.caption("Data source: NSE Bhavcopy archives  •  Signals based on OHLCV only")

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total stocks", f"{len(df_all):,}")
c2.metric("Matching filters", f"{len(df):,}")
c3.metric("Avg score", f"{df['momentum_score'].mean():.1f}" if not df.empty else "—")
c4.metric("Avg vol ratio", f"{df['volume_ratio'].mean():.1f}×" if not df.empty else "—")
c5.metric("Breakouts", f"{df['breakout'].sum():,}" if not df.empty else "—")

st.divider()

# ---------------------------------------------------------------------------
# Main layout: table  |  charts
# ---------------------------------------------------------------------------

left, right = st.columns([3, 2], gap="large")

# ── Results table ──────────────────────────────────────────────────────────
with left:
    st.subheader(f"Results  ({len(df)} stocks)")

    if df.empty:
        st.info("No stocks match the current filters.")
    else:
        display = df.head(top_n)[[
            "last_close", "pct_1d", "pct_5d", "pct_20d",
            "volume_ratio", "above_50dma", "near_52w_high",
            "breakout", "volume_spike", "big_mover", "momentum_score",
        ]].copy()

        display.index.name = "Symbol"
        display.columns = [
            "Close ₹", "1D %", "5D %", "20D %",
            "Vol/Avg", ">50DMA", "NearHigh",
            "Breakout", "VolSpike", "BigMover", "Score",
        ]

        def _colour_pct(val):
            colour = "#1a9c3e" if val > 0 else ("#d93025" if val < 0 else "")
            return f"color: {colour}; font-weight: bold" if colour else ""

        def _bg_score(val):
            """Green gradient 0-100 without matplotlib."""
            try:
                ratio = max(0.0, min(float(val) / 100, 1.0))
                r = int(255 - ratio * 155)
                g = int(200 + ratio * 55)
                b = int(150 - ratio * 100)
                return f"background-color: rgb({r},{g},{b})"
            except (TypeError, ValueError):
                return ""

        def _bg_vol(val):
            """Blue gradient 0-20 without matplotlib."""
            try:
                ratio = max(0.0, min(float(val) / 20, 1.0))
                r = int(240 - ratio * 190)
                g = int(240 - ratio * 140)
                b = 255
                return f"background-color: rgb({r},{g},{b})"
            except (TypeError, ValueError):
                return ""

        styled = (
            display.style
            .map(_colour_pct, subset=["1D %", "5D %", "20D %"])
            .map(_bg_score, subset=["Score"])
            .map(_bg_vol, subset=["Vol/Avg"])
            .format({
                "Close ₹": "₹{:.2f}",
                "1D %": "{:+.2f}%",
                "5D %": "{:+.2f}%",
                "20D %": "{:+.2f}%",
                "Vol/Avg": "{:.1f}×",
                "Score": "{:.0f}",
            })
        )

        st.dataframe(styled, use_container_width=True, height=520)

        # Export button
        csv = df.to_csv().encode()
        st.download_button(
            "⬇ Download full results CSV",
            data=csv,
            file_name="momentum_scan.csv",
            mime="text/csv",
        )

# ── Right-side charts ──────────────────────────────────────────────────────
with right:
    # Top-20 bar chart
    st.subheader("Top 20 by momentum score")
    if not df.empty:
        top20 = df.head(20)[["momentum_score", "pct_1d"]].reset_index()
        fig_bar = px.bar(
            top20,
            x="symbol",
            y="momentum_score",
            color="pct_1d",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            labels={"symbol": "", "momentum_score": "Score", "pct_1d": "1D %"},
            height=300,
        )
        fig_bar.update_layout(margin=dict(t=10, b=10), coloraxis_showscale=False)
        st.plotly_chart(fig_bar, use_container_width=True)

    # Score distribution
    st.subheader("Score distribution")
    if not df.empty:
        fig_hist = px.histogram(
            df, x="momentum_score", nbins=20,
            labels={"momentum_score": "Momentum Score"},
            color_discrete_sequence=["#4a90e2"],
            height=220,
        )
        fig_hist.update_layout(margin=dict(t=10, b=10), showlegend=False)
        st.plotly_chart(fig_hist, use_container_width=True)

# ---------------------------------------------------------------------------
# Stock detail — price + volume chart
# ---------------------------------------------------------------------------

st.divider()
st.subheader("📊 Stock detail")

symbols_available = sorted(df.index.tolist()) if not df.empty else []
selected = st.selectbox(
    "Select a stock to view its price & volume chart",
    options=symbols_available,
    index=0 if symbols_available else None,
)

if selected:
    ohlcv = load_ohlcv(selected)
    if ohlcv.empty:
        st.warning(f"No price data found for {selected}.")
    else:
        ohlcv = ohlcv.sort_index()
        signals_row = df.loc[selected] if selected in df.index else None

        if signals_row is not None:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Last close", f"₹{signals_row['last_close']:,.2f}")
            m2.metric("1-day return", f"{signals_row['pct_1d']:+.2f}%")
            m3.metric("Volume ratio", f"{signals_row['volume_ratio']:.1f}×")
            m4.metric("Momentum score", f"{signals_row['momentum_score']:.0f}/100")

        # Candlestick + volume
        fig = go.Figure()

        fig.add_trace(go.Candlestick(
            x=ohlcv.index,
            open=ohlcv["Open"], high=ohlcv["High"],
            low=ohlcv["Low"],   close=ohlcv["Close"],
            name="OHLC",
            increasing_line_color="#1a9c3e",
            decreasing_line_color="#d93025",
        ))

        # 20-day MA overlay
        if len(ohlcv) >= 20:
            ohlcv["SMA20"] = ohlcv["Close"].rolling(20).mean()
            fig.add_trace(go.Scatter(
                x=ohlcv.index, y=ohlcv["SMA20"],
                name="20-day MA", line=dict(color="#f5a623", width=1.5, dash="dot"),
            ))

        # 50-day MA overlay
        if len(ohlcv) >= 50:
            ohlcv["SMA50"] = ohlcv["Close"].rolling(50).mean()
            fig.add_trace(go.Scatter(
                x=ohlcv.index, y=ohlcv["SMA50"],
                name="50-day MA", line=dict(color="#4a90e2", width=1.5),
            ))

        fig.update_layout(
            title=f"{selected} — Price",
            xaxis_rangeslider_visible=False,
            height=380,
            margin=dict(t=40, b=10),
            legend=dict(orientation="h", y=1.05),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Volume bar chart
        avg_vol = ohlcv["Volume"].iloc[:-1].rolling(20).mean()
        fig_vol = go.Figure()
        fig_vol.add_trace(go.Bar(
            x=ohlcv.index, y=ohlcv["Volume"],
            name="Volume",
            marker_color=[
                "#1a9c3e" if c >= o else "#d93025"
                for c, o in zip(ohlcv["Close"], ohlcv["Open"])
            ],
        ))
        fig_vol.add_trace(go.Scatter(
            x=ohlcv.index, y=avg_vol,
            name="20-day avg", line=dict(color="#f5a623", width=1.5),
        ))
        fig_vol.update_layout(
            title=f"{selected} — Volume",
            height=220,
            margin=dict(t=40, b=10),
            showlegend=True,
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_vol, use_container_width=True)

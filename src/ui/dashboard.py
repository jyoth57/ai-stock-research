"""
dashboard.py
------------
Streamlit dashboard for NSE stock ranking and filtering.

Run
---
    streamlit run src/ui/dashboard.py

Data source
-----------
Loads  data/processed/fundamentals.parquet  produced by FundamentalsEngine.
If the file is missing, a demo dataset is generated so the UI is always usable.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FUNDAMENTALS_PARQUET = _PROJECT_ROOT / "data" / "processed" / "fundamentals.parquet"

# ---------------------------------------------------------------------------
# Metric metadata  (display label, higher-is-better flag, % suffix)
# ---------------------------------------------------------------------------

METRICS: dict[str, dict] = {
    "roe_pct":          {"label": "ROE (%)",            "higher_better": True,  "fmt": "{:.1f}%"},
    "roce_pct":         {"label": "ROCE (%)",           "higher_better": True,  "fmt": "{:.1f}%"},
    "eps_growth_pct":   {"label": "EPS Growth (%)",     "higher_better": True,  "fmt": "{:.1f}%"},
    "revenue_cagr_pct": {"label": "Revenue CAGR (%)",   "higher_better": True,  "fmt": "{:.1f}%"},
    "debt_to_equity":   {"label": "Debt / Equity",      "higher_better": False, "fmt": "{:.2f}x"},
    "free_cash_flow":   {"label": "Free Cash Flow",     "higher_better": True,  "fmt": "{:,.0f}"},
}

SCORE_COLS = list(METRICS.keys())

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading fundamentals…")
def load_data() -> pd.DataFrame:
    if _FUNDAMENTALS_PARQUET.exists():
        df = pd.read_parquet(_FUNDAMENTALS_PARQUET)
    else:
        st.warning(
            f"`{_FUNDAMENTALS_PARQUET.relative_to(_PROJECT_ROOT)}` not found — "
            "showing **demo data**. Run `FundamentalsEngine` to generate real data.",
            icon="⚠️",
        )
        df = _demo_data()

    df["date"] = pd.to_datetime(df["date"])
    return df


def _demo_data() -> pd.DataFrame:
    """Minimal synthetic dataset so the dashboard works out of the box."""
    import numpy as np

    rng = np.random.default_rng(42)
    symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "WIPRO",
               "BAJFINANCE", "LTIM", "ASIANPAINT", "MARUTI", "SUNPHARMA"]
    years = [2020, 2021, 2022, 2023, 2024]
    rows = []
    for sym in symbols:
        base_rev = rng.uniform(5_000, 80_000)
        for yr in years:
            rows.append({
                "symbol": sym,
                "date": pd.Timestamp(f"{yr}-03-31"),
                "revenue": base_rev * (1 + rng.uniform(0.03, 0.18)) ** (yr - 2020),
                "net_income": base_rev * rng.uniform(0.08, 0.22),
                "eps": rng.uniform(20, 120),
                "ebit": base_rev * rng.uniform(0.10, 0.28),
                "total_equity": base_rev * rng.uniform(1.5, 4.0),
                "total_assets": base_rev * rng.uniform(3.0, 8.0),
                "total_debt": base_rev * rng.uniform(0.1, 1.5),
                "capital_employed": base_rev * rng.uniform(2.0, 6.0),
                "free_cash_flow": base_rev * rng.uniform(-0.05, 0.15),
                "roe_pct": rng.uniform(8, 35),
                "roce_pct": rng.uniform(10, 40),
                "eps_growth_pct": rng.uniform(-5, 30),
                "revenue_cagr_pct": rng.uniform(5, 25),
                "debt_to_equity": rng.uniform(0.1, 2.5),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def add_composite_score(df: pd.DataFrame) -> pd.DataFrame:
    """Rank-normalise each metric then average into a 0–100 composite score."""
    df = df.copy()
    for col, meta in METRICS.items():
        if col not in df.columns:
            continue
        ranks = df[col].rank(pct=True, na_option="bottom")
        df[f"_norm_{col}"] = ranks if meta["higher_better"] else (1 - ranks)

    norm_cols = [f"_norm_{c}" for c in SCORE_COLS if f"_norm_{c}" in df.columns]
    if norm_cols:
        df["composite_score"] = (df[norm_cols].mean(axis=1) * 100).round(1)
    else:
        df["composite_score"] = float("nan")

    df.drop(columns=norm_cols, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Stock Research",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Load & prepare data
# ---------------------------------------------------------------------------

raw = load_data()

all_symbols = sorted(raw["symbol"].unique())
all_dates   = sorted(raw["date"].dt.year.unique())

# ---------------------------------------------------------------------------
# Sidebar — Filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("📊 Filters")

    # Symbol picker
    selected_symbols = st.multiselect(
        "Symbols",
        options=all_symbols,
        default=all_symbols,
        placeholder="All symbols",
    )

    # Year range
    year_min, year_max = int(min(all_dates)), int(max(all_dates))
    selected_years = st.slider(
        "Fiscal year range",
        min_value=year_min,
        max_value=year_max,
        value=(year_min, year_max),
    )

    st.divider()
    st.subheader("Threshold filters")

    min_roe   = st.number_input("Min ROE (%)",          value=0.0,  step=1.0)
    min_roce  = st.number_input("Min ROCE (%)",         value=0.0,  step=1.0)
    max_de    = st.number_input("Max Debt / Equity",    value=10.0, step=0.1)
    min_fcf   = st.number_input("Min Free Cash Flow",   value=float("-inf"), step=100.0,
                                format="%.0f")

    st.divider()
    st.subheader("Ranking")
    rank_metric = st.selectbox(
        "Primary sort metric",
        options=["composite_score"] + SCORE_COLS,
        format_func=lambda c: "Composite Score" if c == "composite_score"
                              else METRICS[c]["label"],
    )
    top_n = st.slider("Show top N stocks", min_value=5, max_value=50, value=20)

# ---------------------------------------------------------------------------
# Filter data
# ---------------------------------------------------------------------------

df = raw.copy()

if selected_symbols:
    df = df[df["symbol"].isin(selected_symbols)]

df = df[df["date"].dt.year.between(*selected_years)]

# Keep latest year per symbol for ranking view
latest = (
    df.sort_values("date")
      .groupby("symbol")
      .last()
      .reset_index()
)

# Apply threshold filters
if "roe_pct" in latest.columns:
    latest = latest[latest["roe_pct"].fillna(0) >= min_roe]
if "roce_pct" in latest.columns:
    latest = latest[latest["roce_pct"].fillna(0) >= min_roce]
if "debt_to_equity" in latest.columns:
    latest = latest[latest["debt_to_equity"].fillna(0) <= max_de]
if "free_cash_flow" in latest.columns:
    latest = latest[latest["free_cash_flow"].fillna(0) >= min_fcf]

latest = add_composite_score(latest)

# Sort and trim
ascending = not METRICS.get(rank_metric, {}).get("higher_better", True)
ranked = (
    latest.sort_values(rank_metric, ascending=ascending)
           .head(top_n)
           .reset_index(drop=True)
)
ranked.index += 1  # 1-based rank

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("📈 AI Stock Research — Fundamental Rankings")
st.caption(f"Showing top {len(ranked)} of {len(latest)} stocks after filters · "
           f"Latest year per symbol · Sorted by **{rank_metric}**")

# ---- KPI strip ----
col1, col2, col3, col4 = st.columns(4)
col1.metric("Stocks shown",     len(ranked))
col2.metric("Avg ROE (%)",      f"{ranked['roe_pct'].mean():.1f}"   if "roe_pct"   in ranked.columns else "—")
col3.metric("Avg ROCE (%)",     f"{ranked['roce_pct'].mean():.1f}"  if "roce_pct"  in ranked.columns else "—")
col4.metric("Avg D/E",          f"{ranked['debt_to_equity'].mean():.2f}" if "debt_to_equity" in ranked.columns else "—")

st.divider()

# ---- Ranked table ----
st.subheader("🏆 Ranked Table")

display_cols = (
    ["symbol", "composite_score"]
    + [c for c in SCORE_COLS if c in ranked.columns]
)
display_df = ranked[display_cols].copy()

# Human-readable column names
rename = {"symbol": "Symbol", "composite_score": "Score"}
rename.update({k: v["label"] for k, v in METRICS.items()})
display_df = display_df.rename(columns=rename)

st.dataframe(
    display_df.style.background_gradient(subset=["Score"], cmap="RdYlGn"),
    use_container_width=True,
    height=min(60 + len(display_df) * 35, 600),
)

st.divider()

# ---- Bar chart ----
st.subheader(f"📊 Top stocks by {rename.get(rank_metric, rank_metric)}")

chart_col = rank_metric
if chart_col in ranked.columns:
    fig = px.bar(
        ranked.head(15),
        x="symbol",
        y=chart_col,
        color=chart_col,
        color_continuous_scale="RdYlGn" if METRICS.get(chart_col, {}).get("higher_better") else "RdYlGn_r",
        labels={"symbol": "Symbol", chart_col: rename.get(chart_col, chart_col)},
        text_auto=".1f",
    )
    fig.update_layout(coloraxis_showscale=False, plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ---- Trend lines for a selected stock ----
st.subheader("📉 Metric trends over time")

trend_symbol = st.selectbox("Select stock", options=ranked["symbol"].tolist())
trend_metric = st.selectbox(
    "Select metric",
    options=SCORE_COLS,
    format_func=lambda c: METRICS[c]["label"],
    key="trend_metric",
)

trend_df = df[df["symbol"] == trend_symbol].sort_values("date")

if trend_metric in trend_df.columns and not trend_df.empty:
    fig2 = px.line(
        trend_df,
        x="date",
        y=trend_metric,
        markers=True,
        labels={"date": "Date", trend_metric: METRICS[trend_metric]["label"]},
        title=f"{trend_symbol} — {METRICS[trend_metric]['label']}",
    )
    fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("No trend data available for this selection.")

st.divider()

# ---- Scatter: ROE vs ROCE ----
st.subheader("🔵 ROE vs ROCE (bubble = composite score)")

if {"roe_pct", "roce_pct", "composite_score"}.issubset(latest.columns):
    fig3 = px.scatter(
        latest,
        x="roe_pct",
        y="roce_pct",
        size="composite_score",
        color="composite_score",
        hover_name="symbol",
        color_continuous_scale="RdYlGn",
        labels={"roe_pct": "ROE (%)", "roce_pct": "ROCE (%)", "composite_score": "Score"},
        size_max=40,
    )
    fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig3, use_container_width=True)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.caption("Data: `data/processed/fundamentals.parquet` · Refresh via `FundamentalsEngine`")

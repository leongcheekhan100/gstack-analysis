"""
HYPE P/E Dashboard
------------------
Live Streamlit dashboard for Hyperliquid (HYPE) "price to earnings" where the
earnings proxy is the protocol's daily buyback (Assistance Fund burn).

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import data as hype

st.set_page_config(
    page_title="HYPE P/E Dashboard",
    page_icon="📈",
    layout="wide",
)

if hype.DEMO_MODE:
    st.warning(
        "⚠️ **Demo mode** — synthetic data. The live APIs are unreachable in "
        "this environment. Numbers below are illustrative, not real HYPE values."
    )


# ---------- caching --------------------------------------------------------

@st.cache_data(ttl=60)  # refresh live numbers every minute
def _snapshot():
    return hype.get_snapshot()


@st.cache_data(ttl=10 * 60)  # 10 min for historical series
def _history(days: int):
    return hype.build_history(days=days)


# ---------- formatting helpers --------------------------------------------

def fmt_usd(x: float) -> str:
    if x is None or pd.isna(x):
        return "—"
    a = abs(x)
    if a >= 1e9:
        return f"${x/1e9:,.2f}B"
    if a >= 1e6:
        return f"${x/1e6:,.2f}M"
    if a >= 1e3:
        return f"${x/1e3:,.2f}K"
    return f"${x:,.2f}"


def fmt_num(x: float, suffix: str = "") -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:,.2f}{suffix}"


# ---------- UI -------------------------------------------------------------

st.title("📈 HYPE Price-to-Earnings Dashboard")
st.caption(
    "Hyperliquid (HYPE) valued against its Assistance Fund buyback / burn. "
    "Live price & supply from Hyperliquid's official API; historical daily "
    "buybacks from DeFiLlama (holders revenue series)."
)

with st.sidebar:
    st.header("Settings")
    days = st.slider(
        "History window (days)", min_value=60, max_value=730, value=365, step=30
    )
    smoothing = st.radio(
        "P/E earnings basis",
        options=["Annualized daily buyback", "Annualized 30-day average"],
        index=1,
        help=(
            "Daily: today's buyback × 365 (real-time, noisy).\n"
            "30-day: trailing 30-day mean × 365 (smoother)."
        ),
    )
    st.markdown("---")
    st.markdown(
        "**Methodology**\n\n"
        "- *Market cap* = price × circulating supply\n"
        "- *Earnings* = USD value of HYPE bought back/burned by the "
        "Assistance Fund\n"
        "- *Annualization* = daily × 365\n"
        "- *P/E* = market cap ÷ annualized earnings\n"
    )
    if st.button("🔄 Force refresh"):
        st.cache_data.clear()
        st.rerun()

# --- live snapshot ---------------------------------------------------------
try:
    snap = _snapshot()
except Exception as e:  # pragma: no cover - depends on network
    st.error(f"Failed to load live data: {e}")
    st.stop()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("HYPE Price", f"${snap.price:,.2f}")
c2.metric("Circulating Supply", f"{snap.circulating_supply/1e6:,.2f}M HYPE")
c3.metric("Market Cap", fmt_usd(snap.market_cap))
c4.metric("Daily Buyback (latest)", fmt_usd(snap.latest_daily_buyback_usd))
c5.metric(
    "Annualized Earnings",
    fmt_usd(snap.annualized_earnings_usd),
    help="latest daily buyback × 365",
)

st.markdown(
    f"### Current P/E (annualized daily buyback): "
    f"**{snap.pe_ratio:,.1f}×**"
    f" &nbsp;·&nbsp; <sub>as of {snap.as_of:%Y-%m-%d %H:%M UTC}</sub>",
    unsafe_allow_html=True,
)

# --- historical series -----------------------------------------------------
try:
    hist = _history(days=days)
except Exception as e:  # pragma: no cover
    st.error(f"Failed to load history: {e}")
    st.stop()

if hist.empty:
    st.warning("No overlapping price + buyback history available.")
    st.stop()

pe_col = "pe_ratio_30d" if smoothing.startswith("Annualized 30") else "pe_ratio"
earn_col = (
    "annualized_earnings_30d"
    if smoothing.startswith("Annualized 30")
    else "annualized_earnings"
)

# Current P/E recomputed on the chosen basis (using latest live mcap)
latest_earn = hist[earn_col].dropna()
if not latest_earn.empty:
    live_pe_alt = snap.market_cap / float(latest_earn.iloc[-1])
    st.markdown(
        f"### P/E on **{smoothing.lower()}** basis: **{live_pe_alt:,.1f}×**"
    )

# --- chart 1: P/E over time -----------------------------------------------
st.subheader("Historical P/E ratio")
fig_pe = go.Figure()
fig_pe.add_trace(
    go.Scatter(
        x=hist.index,
        y=hist[pe_col],
        mode="lines",
        name=f"P/E ({smoothing})",
        line=dict(color="#58a6ff", width=2),
    )
)
fig_pe.update_layout(
    height=380,
    margin=dict(l=20, r=20, t=10, b=20),
    yaxis_title="P/E (×)",
    xaxis_title=None,
    hovermode="x unified",
    template="plotly_dark",
)
st.plotly_chart(fig_pe, use_container_width=True)

# Stats row
c1, c2, c3, c4 = st.columns(4)
pe_series = hist[pe_col].dropna()
c1.metric("Median P/E", fmt_num(pe_series.median(), "×"))
c2.metric("Min P/E", fmt_num(pe_series.min(), "×"))
c3.metric("Max P/E", fmt_num(pe_series.max(), "×"))
c4.metric(
    "Percentile of latest",
    fmt_num((pe_series <= pe_series.iloc[-1]).mean() * 100, "%"),
    help="What % of historical days had a P/E ≤ today's value",
)

# --- chart 2: Price + buyback ---------------------------------------------
st.subheader("Price and daily buyback")
fig2 = make_subplots(specs=[[{"secondary_y": True}]])
fig2.add_trace(
    go.Scatter(
        x=hist.index,
        y=hist["close"],
        name="HYPE price (USD)",
        line=dict(color="#f0f6fc", width=2),
    ),
    secondary_y=False,
)
fig2.add_trace(
    go.Bar(
        x=hist.index,
        y=hist["buyback_usd"],
        name="Daily buyback (USD)",
        marker=dict(color="#3fb950"),
        opacity=0.6,
    ),
    secondary_y=True,
)
fig2.add_trace(
    go.Scatter(
        x=hist.index,
        y=hist["buyback_30d_avg"],
        name="Buyback 30d avg",
        line=dict(color="#f0883e", width=2, dash="dot"),
    ),
    secondary_y=True,
)
fig2.update_yaxes(title_text="HYPE (USD)", secondary_y=False)
fig2.update_yaxes(title_text="Buyback (USD)", secondary_y=True)
fig2.update_layout(
    height=420,
    margin=dict(l=20, r=20, t=10, b=20),
    template="plotly_dark",
    hovermode="x unified",
    legend=dict(orientation="h", y=1.05),
)
st.plotly_chart(fig2, use_container_width=True)

# --- chart 3: Market cap vs annualized earnings ---------------------------
st.subheader("Market cap vs annualized earnings")
fig3 = go.Figure()
fig3.add_trace(
    go.Scatter(
        x=hist.index,
        y=hist["market_cap"],
        name="Market cap",
        line=dict(color="#58a6ff", width=2),
    )
)
fig3.add_trace(
    go.Scatter(
        x=hist.index,
        y=hist[earn_col],
        name=f"Annualized earnings ({smoothing.lower()})",
        line=dict(color="#3fb950", width=2),
    )
)
fig3.update_layout(
    height=380,
    margin=dict(l=20, r=20, t=10, b=20),
    template="plotly_dark",
    hovermode="x unified",
    yaxis_type="log",
    yaxis_title="USD (log scale)",
    legend=dict(orientation="h", y=1.05),
)
st.plotly_chart(fig3, use_container_width=True)

# --- data table -----------------------------------------------------------
with st.expander("Show data table"):
    show = hist.copy()
    show.index = show.index.astype(str)
    show = show.rename(
        columns={
            "close": "price",
            "buyback_usd": "buyback_usd",
            "buyback_30d_avg": "buyback_30d_avg_usd",
            "annualized_earnings": "earn_ann_daily_usd",
            "annualized_earnings_30d": "earn_ann_30d_usd",
            "market_cap": "market_cap_usd",
            "pe_ratio": "pe_daily",
            "pe_ratio_30d": "pe_30d",
        }
    )
    st.dataframe(show.iloc[::-1], use_container_width=True, height=420)
    st.download_button(
        "Download CSV",
        data=show.to_csv().encode(),
        file_name="hype_pe_history.csv",
        mime="text/csv",
    )

st.markdown(
    """
    <hr style="margin-top:32px;margin-bottom:8px;border-color:#30363d">
    <small style="color:#8b949e">
    Sources: Hyperliquid Info API (price, supply), DeFiLlama
    <code>summary/fees/hyperliquid?dataType=dailyHoldersRevenue</code>
    (daily HYPE buyback / burn).
    Note: market cap uses the <em>current</em> circulating supply for all
    historical points (Hyperliquid does not expose historical circulating
    supply); P/E is therefore a clean valuation multiple on today's float,
    not a point-in-time mcap. The buyback "earnings" interpretation is a
    crypto convention, not GAAP — for a token holder it represents the
    cash flow used to retire supply.
    </small>
    """,
    unsafe_allow_html=True,
)

# HYPE P/E Dashboard

A live Streamlit dashboard that values **Hyperliquid (HYPE)** on a
price-to-earnings basis, using the protocol's **daily Assistance Fund
buyback / burn** as the earnings proxy.

## What it shows

- **Live**: HYPE price, circulating supply, market cap, latest daily buyback,
  annualized earnings, and the current P/E.
- **Historical**: P/E ratio over time, daily buybacks (with a 30-day moving
  average), and market cap vs annualized earnings.
- Stats row: median / min / max historical P/E, and where the latest P/E
  ranks vs history.
- Downloadable CSV of the full table.

## Methodology

| Field | Formula |
|---|---|
| Market cap | `price × circulating_supply` |
| Daily earnings | USD value of HYPE bought back & burned by the Assistance Fund |
| Annualized earnings (daily basis) | `latest_daily_buyback × 365` |
| Annualized earnings (30d basis) | `mean(last 30 days buybacks) × 365` |
| P/E | `market_cap / annualized_earnings` |

The dashboard lets you toggle between the **daily** (real-time, noisy) and
**30-day** (smoothed) earnings basis in the sidebar.

> ⚠️ Market cap on historical points uses **today's** circulating supply
> (Hyperliquid's API does not expose historical circulating supply). The
> chart is therefore a clean *valuation multiple on today's float*, not a
> reconstruction of point-in-time mcap.

## Data sources

| Field | Source |
|---|---|
| HYPE live price (mid) | Hyperliquid `info` API → `allMids` → `@107` |
| HYPE historical price | Hyperliquid `info` API → `candleSnapshot` (1d) |
| HYPE circulating supply | Hyperliquid `info` API → `tokenDetails` |
| Daily buybacks (USD) | DeFiLlama `summary/fees/hyperliquid?dataType=dailyHoldersRevenue` |

**Why DeFiLlama for buybacks?** Hyperliquid's `userFillsByTime` endpoint
only exposes the most recent ~10,000 fills, which on the Assistance Fund
(`0xfefe…fefe`) covers only a few days. DeFiLlama aggregates the full
history daily as "Holders Revenue", which for Hyperliquid is the AF
buyback notional.

## Setup

```bash
cd hype-pe-dashboard
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (usually <http://localhost:8501>).

The live snapshot refreshes every 60s; historical series every 10 min. Use
the **🔄 Force refresh** button in the sidebar to clear caches.

## Files

- `app.py` — Streamlit UI
- `data.py` — data fetchers (Hyperliquid + DeFiLlama)
- `requirements.txt` — Python deps

## Deploying

The cheapest path is **Streamlit Community Cloud**:
1. Push this repo (or just the `hype-pe-dashboard/` folder) to GitHub.
2. Sign in at <https://streamlit.io/cloud>, "New app", point at this folder's
   `app.py`. No env vars needed.

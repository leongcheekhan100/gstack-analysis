"""
Data fetchers for the HYPE P/E dashboard.

Sources
-------
- Hyperliquid official API (https://api.hyperliquid.xyz/info):
    * live HYPE/USDC mid price (allMids)
    * daily price candles (candleSnapshot)
    * circulating supply (tokenDetails)
- DeFiLlama (https://api.llama.fi):
    * historical daily "Holders Revenue" = USD value of HYPE that the
      Assistance Fund buys back / burns each day. Used as the earnings proxy.
      We use DeFiLlama because Hyperliquid's userFillsByTime endpoint only
      exposes the most recent ~10k fills, which on the AF address covers only
      a few days. DeFiLlama aggregates the full history.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
import requests

HL_INFO_URL = "https://api.hyperliquid.xyz/info"

# DeFiLlama exposes Hyperliquid fees under several adapter slugs depending on
# segment (perps vs spot vs the combined protocol). We try them in order and
# use the first one that returns a non-empty daily series. `hyperliquid-perps`
# is the dominant one — perp fees fund essentially all of the AF buybacks.
DEFILLAMA_FEE_SLUGS = ("hyperliquid-perps", "hyperliquid", "hyperliquid-spot")
DEFILLAMA_FEES_URL_TMPL = (
    "https://api.llama.fi/summary/fees/{slug}?dataType=dailyHoldersRevenue"
)

HYPE_SPOT_PAIR = "@107"  # HYPE/USDC spot pair index on Hyperliquid
HYPE_TOKEN_NAME = "HYPE"


def _post_info(body: dict, timeout: int = 20) -> dict | list:
    r = requests.post(HL_INFO_URL, json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---------- Hyperliquid ----------------------------------------------------

def get_hype_mid_price() -> float:
    """Latest HYPE/USDC mid price from Hyperliquid."""
    mids = _post_info({"type": "allMids"})
    px = mids.get(HYPE_SPOT_PAIR)
    if px is None:
        raise RuntimeError(f"HYPE mid price not found at key {HYPE_SPOT_PAIR}")
    return float(px)


def _find_hype_token_id() -> str:
    """Resolve the HYPE token's on-chain id (hex) from spotMeta."""
    meta = _post_info({"type": "spotMeta"})
    for tok in meta.get("tokens", []):
        if tok.get("name") == HYPE_TOKEN_NAME:
            return tok["tokenId"]
    raise RuntimeError("HYPE token not found in spotMeta")


def get_hype_supply() -> dict:
    """Returns dict with circulatingSupply, totalSupply, maxSupply (floats)."""
    token_id = _find_hype_token_id()
    details = _post_info({"type": "tokenDetails", "tokenId": token_id})
    return {
        "circulatingSupply": float(details.get("circulatingSupply", 0) or 0),
        "totalSupply": float(details.get("totalSupply", 0) or 0),
        "maxSupply": float(details.get("maxSupply", 0) or 0),
        "name": details.get("name", HYPE_TOKEN_NAME),
    }


def get_hype_price_history(days: int = 400) -> pd.DataFrame:
    """Daily HYPE/USDC candles for the last `days` days.

    Returns DataFrame indexed by UTC date with columns: open, high, low, close, volume.
    """
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 24 * 60 * 60 * 1000
    body = {
        "type": "candleSnapshot",
        "req": {
            "coin": HYPE_SPOT_PAIR,
            "interval": "1d",
            "startTime": start_ms,
            "endTime": end_ms,
        },
    }
    candles = _post_info(body)
    if not candles:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"]
        )
    rows = []
    for c in candles:
        rows.append(
            {
                "date": datetime.fromtimestamp(c["t"] / 1000, tz=timezone.utc).date(),
                "open": float(c["o"]),
                "high": float(c["h"]),
                "low": float(c["l"]),
                "close": float(c["c"]),
                "volume": float(c["v"]),
            }
        )
    df = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date")
    df = df.set_index("date")
    return df


# ---------- DeFiLlama: holders revenue (=daily buybacks) -------------------

def _fetch_defillama_holders_revenue(slug: str) -> list:
    url = DEFILLAMA_FEES_URL_TMPL.format(slug=slug)
    r = requests.get(url, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    payload = r.json()
    series = payload.get("totalDataChart") or []
    if not series and "totalDataChartBreakdown" in payload:
        breakdown = payload["totalDataChartBreakdown"]
        agg: dict[int, float] = {}
        for ts, by_chain in breakdown:
            total = 0.0
            for _chain, by_proto in (by_chain or {}).items():
                for _proto, v in (by_proto or {}).items():
                    try:
                        total += float(v or 0)
                    except (TypeError, ValueError):
                        pass
            agg[int(ts)] = total
        series = sorted(agg.items())
    return series


def get_daily_buybacks() -> pd.DataFrame:
    """Daily USD holders revenue (=AF buyback notional) for Hyperliquid.

    Returns DataFrame indexed by UTC date with one column: buyback_usd.
    """
    series: list = []
    last_err: Exception | None = None
    for slug in DEFILLAMA_FEE_SLUGS:
        try:
            s = _fetch_defillama_holders_revenue(slug)
        except Exception as e:  # network / parsing error: try next slug
            last_err = e
            continue
        if s:
            series = s
            break
    if not series:
        if last_err is not None:
            raise RuntimeError(f"DeFiLlama fetch failed: {last_err}")
        return pd.DataFrame(columns=["buyback_usd"]).rename_axis("date")

    rows = []
    for ts, val in series:
        try:
            v = float(val or 0)
        except (TypeError, ValueError):
            v = 0.0
        rows.append(
            {
                "date": datetime.fromtimestamp(int(ts), tz=timezone.utc).date(),
                "buyback_usd": v,
            }
        )
    df = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date")
    if df.empty:
        return df.set_index("date") if "date" in df.columns else df
    return df.set_index("date")


# ---------- Combined view --------------------------------------------------

@dataclass
class HypeSnapshot:
    price: float
    circulating_supply: float
    market_cap: float
    latest_daily_buyback_usd: float
    annualized_earnings_usd: float
    pe_ratio: float
    as_of: datetime


def build_history(days: int = 400) -> pd.DataFrame:
    """Build the full historical PE table.

    Columns
    -------
    close              : HYPE/USDC close price (USD)
    buyback_usd        : USD value of HYPE bought back that day (DeFiLlama)
    buyback_30d_avg    : 30-day trailing average of buyback_usd
    annualized_earnings: buyback_usd * 365
    market_cap         : close * circulating_supply  (uses CURRENT supply)
    pe_ratio           : market_cap / annualized_earnings
    pe_ratio_30d       : market_cap / (buyback_30d_avg * 365)  (smoother)
    """
    prices = get_hype_price_history(days=days)
    buybacks = get_daily_buybacks()
    supply = get_hype_supply()["circulatingSupply"]

    df = prices[["close"]].join(buybacks, how="inner")
    df["buyback_30d_avg"] = df["buyback_usd"].rolling(30, min_periods=7).mean()
    df["annualized_earnings"] = df["buyback_usd"] * 365.0
    df["annualized_earnings_30d"] = df["buyback_30d_avg"] * 365.0
    df["market_cap"] = df["close"] * supply
    df["pe_ratio"] = df["market_cap"] / df["annualized_earnings"].replace(0, pd.NA)
    df["pe_ratio_30d"] = df["market_cap"] / df["annualized_earnings_30d"].replace(0, pd.NA)
    return df


def get_snapshot() -> HypeSnapshot:
    price = get_hype_mid_price()
    supply = get_hype_supply()
    buybacks = get_daily_buybacks()

    if buybacks.empty:
        raise RuntimeError("DeFiLlama returned no buyback data for Hyperliquid")

    latest_daily_buyback = float(buybacks["buyback_usd"].iloc[-1])
    annualized = latest_daily_buyback * 365.0
    market_cap = price * supply["circulatingSupply"]
    pe = market_cap / annualized if annualized > 0 else float("nan")

    return HypeSnapshot(
        price=price,
        circulating_supply=supply["circulatingSupply"],
        market_cap=market_cap,
        latest_daily_buyback_usd=latest_daily_buyback,
        annualized_earnings_usd=annualized,
        pe_ratio=pe,
        as_of=datetime.now(timezone.utc),
    )

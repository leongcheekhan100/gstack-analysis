"""
Offline demo data so the dashboard can render in environments where the
Hyperliquid / DeFiLlama APIs are unreachable (e.g. sandboxes, CI).

Enable by setting HYPE_DASHBOARD_DEMO=1 in the environment.

The numbers below are illustrative — shaped to roughly match publicly
known HYPE figures so the charts look sensible — and are NOT live values.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd


def _seeded(seed: int) -> float:
    # Tiny LCG-ish pseudo-random for reproducibility without numpy.
    x = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    return (x % 10_000) / 10_000.0


def _build_synthetic() -> tuple[pd.DataFrame, dict]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=400)
    days = (today - start).days + 1

    rows = []
    price = 8.0  # early-launch reference
    base_fee = 200_000.0  # daily AF buyback USD at launch
    for i in range(days):
        d = start + timedelta(days=i)
        # Long-run drift: price ramps from $8 toward ~$50; buybacks ramp from
        # ~$0.2M/day to ~$3M/day with weekly volatility.
        t = i / max(1, days - 1)
        trend = 8.0 + (50.0 - 8.0) * (t ** 1.2)
        noise = (_seeded(i + 1) - 0.5) * 0.08 * trend
        price = max(1.0, 0.6 * price + 0.4 * trend + noise)

        fee_trend = base_fee + (3_000_000.0 - base_fee) * (t ** 1.1)
        fee_noise = (_seeded(i * 7 + 3) - 0.5) * 0.6 * fee_trend
        buyback = max(10_000.0, fee_trend + fee_noise)

        rows.append(
            {
                "date": d,
                "open": price * (0.99 + 0.02 * _seeded(i * 13)),
                "high": price * (1.01 + 0.03 * _seeded(i * 17)),
                "low": price * (0.95 + 0.02 * _seeded(i * 19)),
                "close": price,
                "volume": 5e7 + 2e8 * _seeded(i * 23),
                "buyback_usd": buyback,
            }
        )

    df = pd.DataFrame(rows).set_index("date")
    supply = {
        "circulatingSupply": 333_000_000.0,
        "totalSupply": 1_000_000_000.0,
        "maxSupply": 1_000_000_000.0,
        "name": "HYPE",
    }
    return df, supply


_DF, _SUPPLY = _build_synthetic()


def get_hype_mid_price() -> float:
    return float(_DF["close"].iloc[-1])


def get_hype_supply() -> dict:
    return dict(_SUPPLY)


def get_hype_price_history(days: int = 400) -> pd.DataFrame:
    cutoff = _DF.index.max() - timedelta(days=days)
    return _DF.loc[_DF.index >= cutoff, ["open", "high", "low", "close", "volume"]].copy()


def get_daily_buybacks() -> pd.DataFrame:
    return _DF[["buyback_usd"]].copy()

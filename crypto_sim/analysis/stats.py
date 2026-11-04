"""Simple crypto return / volatility stats."""

from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_returns(df: pd.DataFrame, price_col: str = "close") -> dict[str, float]:
    """Summary stats suitable for 24/7 crypto series (daily bars assumed)."""
    price = df[price_col].astype(float).dropna()
    rets = price.pct_change().dropna()
    if rets.empty:
        return {
            "bars": float(len(price)),
            "last_price": float(price.iloc[-1]) if len(price) else float("nan"),
            "total_return_pct": float("nan"),
            "vol_ann_pct": float("nan"),
            "max_drawdown_pct": float("nan"),
            "avg_daily_abs_pct": float("nan"),
        }

    total_return = float(price.iloc[-1] / price.iloc[0] - 1.0)
    # Crypto trades ~365 days/year
    vol_ann = float(rets.std(ddof=0) * np.sqrt(365))
    equity = (1 + rets).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    return {
        "bars": float(len(price)),
        "last_price": float(price.iloc[-1]),
        "total_return_pct": total_return * 100.0,
        "vol_ann_pct": vol_ann * 100.0,
        "max_drawdown_pct": float(drawdown.min()) * 100.0,
        "avg_daily_abs_pct": float(rets.abs().mean()) * 100.0,
    }


def score_opportunity(
    market_row: pd.Series,
    stats: dict[str, float] | None = None,
) -> float:
    """Rank score within Bitpanda universe — higher = more interesting for signals.

    Combines liquidity (volume), realized/proxy volatility, and optional OHLC stats.
    Does not remove assets from the universe; only ranks.
    """
    volume = float(market_row.get("total_volume") or 0.0)
    vol_proxy = float(market_row.get("volatility_proxy_pct") or 0.0)
    chg_24h = abs(float(market_row.get("price_change_24h_pct") or 0.0))
    score = np.log10(max(volume, 1.0)) * 10.0 + vol_proxy * 0.5 + chg_24h * 0.25
    if stats:
        score += min(abs(stats.get("vol_ann_pct") or 0.0), 200.0) * 0.05
        # Prefer coins that are not in free-fall only; mild boost for positive trend
        tr = stats.get("total_return_pct") or 0.0
        score += max(min(tr, 50.0), -20.0) * 0.05
    if market_row.get("in_core_holdings"):
        score += 5.0  # Bitpanda BTC/ETH holdings context
    return float(score)

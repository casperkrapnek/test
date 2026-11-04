"""Opportunity ranking within the Bitpanda crypto universe (does not shrink universe)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .bitpanda_universe import CORE_HOLDINGS


@dataclass
class OpportunityRankConfig:
    """Rank/filter knobs for *opportunities* inside the Bitpanda universe.

    The tradable universe itself stays the full Bitpanda crypto list.
    These thresholds only affect which names get OHLCV analysis / paper-trade focus.
    """

    min_market_cap: float = 0.0
    min_volume_24h: float = 1_000_000.0
    min_volatility_proxy_pct: float = 1.0
    max_focus_assets: int = 15
    always_include_pairs: tuple[str, ...] = field(default_factory=lambda: CORE_HOLDINGS)
    exclude_stable_symbols: tuple[str, ...] = (
        "USDT",
        "USDC",
        "DAI",
        "FDUSD",
        "TUSD",
        "USDE",
        "USD1",
        "BUSD",
        "EURC",
        "EUROC",
        "AGEUR",
    )


# Back-compat alias
UniverseFilterConfig = OpportunityRankConfig


def restrict_markets_to_bitpanda(
    markets: pd.DataFrame,
    bitpanda_symbols: set[str] | frozenset[str],
) -> pd.DataFrame:
    """Keep only CoinGecko market rows whose symbol is in the Bitpanda crypto universe."""
    df = markets.copy()
    df["symbol"] = df["symbol"].astype(str).str.upper()
    return df[df["symbol"].isin(bitpanda_symbols)].reset_index(drop=True)


def rank_opportunities(
    markets: pd.DataFrame,
    config: OpportunityRankConfig | None = None,
) -> pd.DataFrame:
    """Rank Bitpanda-universe market rows for signal focus; core BTC/ETH always included."""
    cfg = config or OpportunityRankConfig()
    if markets.empty:
        return markets.copy()

    df = markets.copy()
    df["pair"] = df["pair"].astype(str).str.upper()
    df["symbol"] = df["symbol"].astype(str).str.upper()
    df = df[~df["symbol"].isin(cfg.exclude_stable_symbols)]

    core = {p.upper() for p in cfg.always_include_pairs}
    core_bases = {p.split("/")[0] for p in core}
    df["in_core_holdings"] = df["pair"].isin(core) | df["symbol"].isin(core_bases)

    core_rows = df[df["in_core_holdings"]].copy()
    ranked = df[
        (df["market_cap"].fillna(0) >= cfg.min_market_cap)
        & (df["total_volume"].fillna(0) >= cfg.min_volume_24h)
        & (df["volatility_proxy_pct"].fillna(0) >= cfg.min_volatility_proxy_pct)
    ].copy()

    # Score: liquidity + volatility proxy
    import numpy as np

    vol = ranked["total_volume"].fillna(0).clip(lower=1.0)
    ranked["opportunity_score"] = (
        np.log10(vol) * 10.0
        + ranked["volatility_proxy_pct"].fillna(0).abs() * 0.5
        + ranked["price_change_24h_pct"].fillna(0).abs() * 0.25
        + ranked["in_core_holdings"].astype(float) * 5.0
    )
    ranked = ranked.sort_values("opportunity_score", ascending=False)

    # Align columns before concat (ranked has opportunity_score; core may not)
    if "opportunity_score" not in core_rows.columns:
        core_rows = core_rows.copy()
        core_rows["opportunity_score"] = 1e9  # force-include core
    core_rows = core_rows.loc[:, ~core_rows.columns.duplicated()]
    ranked = ranked.loc[:, ~ranked.columns.duplicated()]
    out = (
        pd.concat([core_rows, ranked], ignore_index=True, sort=False)
        .drop_duplicates(subset=["symbol"])
        .head(cfg.max_focus_assets)
        .reset_index(drop=True)
    )
    if "opportunity_score" not in out.columns:
        out["opportunity_score"] = 0.0
    out = out.sort_values(
        ["in_core_holdings", "opportunity_score"], ascending=[False, False]
    ).reset_index(drop=True)
    return out


# Back-compat
filter_universe = rank_opportunities

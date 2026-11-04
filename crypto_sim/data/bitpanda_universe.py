"""Bitpanda-tradable crypto universe (refreshable, no API key required).

Source: public Bitpanda ticker https://api.bitpanda.com/v1/ticker
Crypto confirmation: CoinGecko /coins/list symbol match.
Metals (XAU/XAG/XPD/XPT) excluded. Stock products are out of scope.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

BITPANDA_TICKER_URL = "https://api.bitpanda.com/v1/ticker"
COINGECKO_LIST_URL = "https://api.coingecko.com/api/v3/coins/list"

METALS = frozenset({"XAU", "XAG", "XPD", "XPT"})
CORE_HOLDINGS = ("BTC/USDT", "ETH/USDT")

# Disambiguate crowded ticker symbols → preferred CoinGecko ids
PREFERRED_COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "BEST": "bitpanda-ecosystem-token",
    "MATIC": "matic-network",
    "POL": "polygon-ecosystem-token",
    "DOGE": "dogecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "DOT": "polkadot",
    "LTC": "litecoin",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "NEAR": "near",
    "APT": "aptos",
    "SUI": "sui",
    "ARB": "arbitrum",
    "OP": "optimism",
    "TRX": "tron",
    "SHIB": "shiba-inu",
    "PEPE": "pepe",
    "TON": "the-open-network",
}

DEFAULT_UNIVERSE_PATH = Path("data/universe/bitpanda_crypto_universe.json")


def default_universe_path() -> Path:
    return DEFAULT_UNIVERSE_PATH


def load_universe(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_UNIVERSE_PATH
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def universe_assets(path: str | Path | None = None) -> list[dict[str, Any]]:
    return list(load_universe(path).get("assets") or [])


def universe_pairs(path: str | Path | None = None) -> list[str]:
    return [a["pair"] for a in universe_assets(path)]


def symbol_to_coingecko_id(path: str | Path | None = None) -> dict[str, str]:
    return {a["symbol"]: a["coingecko_id"] for a in universe_assets(path)}


def refresh_universe(
    path: str | Path | None = None,
    session: requests.Session | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Pull Bitpanda ticker + CoinGecko list; write refreshed JSON snapshot."""
    session = session or requests.Session()
    path = Path(path) if path else DEFAULT_UNIVERSE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    bp_resp = session.get(
        BITPANDA_TICKER_URL,
        timeout=timeout,
        headers={"User-Agent": "crypto-sim/0.1 (paper-trading; research)"},
    )
    bp_resp.raise_for_status()
    bp_symbols = sorted(
        s.upper() for s in bp_resp.json().keys() if s.upper() not in METALS
    )

    cg_resp = session.get(COINGECKO_LIST_URL, timeout=timeout)
    cg_resp.raise_for_status()
    by_sym: dict[str, list[dict[str, str]]] = {}
    for coin in cg_resp.json():
        sym = str(coin.get("symbol", "")).upper()
        by_sym.setdefault(sym, []).append(
            {"id": coin["id"], "name": coin.get("name") or coin["id"]}
        )

    assets: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for sym in bp_symbols:
        cands = by_sym.get(sym)
        if not cands:
            unmapped.append(sym)
            continue
        if sym in PREFERRED_COINGECKO_IDS:
            prefer = PREFERRED_COINGECKO_IDS[sym]
            pick = next((c for c in cands if c["id"] == prefer), cands[0])
        else:
            pick = cands[0]
        assets.append(
            {
                "symbol": sym,
                "name": pick["name"],
                "coingecko_id": pick["id"],
                "pair": f"{sym}/USDT",
                "exchange_context": "bitpanda",
            }
        )

    payload = {
        "source": BITPANDA_TICKER_URL,
        "source_notes": (
            "Public Bitpanda ticker (no API key). Metals excluded. "
            "Crypto confirmed via CoinGecko /coins/list symbol match. "
            "Prices via CoinGecko/Binance free APIs — simulation only, no Bitpanda orders."
        ),
        "quote": "USDT",
        "core_holdings": list(CORE_HOLDINGS),
        "refreshed_at_utc": datetime.now(timezone.utc).isoformat(),
        "asset_count": len(assets),
        "bitpanda_listed_unmapped_symbols": unmapped,
        "notes": (
            "Full Bitpanda-tradable crypto offering (mapped). "
            "Unmapped leveraged/index products listed separately."
        ),
        "assets": assets,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info(
        "Refreshed Bitpanda universe: %d assets (%d unmapped) -> %s",
        len(assets),
        len(unmapped),
        path,
    )
    return payload

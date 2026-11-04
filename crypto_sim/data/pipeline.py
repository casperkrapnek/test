"""Fetch and persist crypto market data from free public APIs (no API key).

Primary: CoinGecko public API (markets list + OHLC/chart)
Fallback OHLCV: Binance public klines (for USDT pairs when mapped)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Core Bitpanda holdings context (observation only — not live trading)
CORE_PAIRS = ("BTC/USDT", "ETH/USDT")

DEFAULT_PAIRS = CORE_PAIRS

# CoinGecko id → display / Binance base symbol helpers
_KNOWN_BINANCE_BASE = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "ripple": "XRP",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "polkadot": "DOT",
    "avalanche-2": "AVAX",
    "chainlink": "LINK",
    "litecoin": "LTC",
    "tron": "TRX",
    "polygon-ecosystem-token": "POL",
    "uniswap": "UNI",
    "stellar": "XLM",
    "near": "NEAR",
    "aptos": "APT",
    "sui": "SUI",
    "arbitrum": "ARB",
    "optimism": "OP",
}

# data-api.binance.vision is the public market-data host (api.binance.com may 451 by region)
BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
COINGECKO_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"


def pair_to_binance_symbol(pair: str) -> str:
    """BTC/USDT -> BTCUSDT."""
    return pair.replace("/", "").upper()


def pair_base_quote(pair: str) -> tuple[str, str]:
    base, quote = pair.upper().split("/")
    return base, quote


def coin_id_to_pair(coin_id: str, symbol: str, quote: str = "USDT") -> str:
    base = _KNOWN_BINANCE_BASE.get(coin_id, symbol.upper())
    return f"{base}/{quote.upper()}"


class CryptoDataPipeline:
    """Load crypto market snapshots + OHLCV; cache under data/market/."""

    def __init__(
        self,
        data_dir: str | Path = "data/market",
        session: requests.Session | None = None,
        timeout: float = 30.0,
        request_pause_s: float = 2.0,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session = session or requests.Session()
        self.timeout = timeout
        self.request_pause_s = request_pause_s

    # --- Broad market scan (CoinGecko) ---

    def fetch_markets(
        self,
        vs_currency: str = "usd",
        pages: int = 2,
        per_page: int = 100,
        order: str = "market_cap_desc",
    ) -> pd.DataFrame:
        """Fetch top coins by market cap from CoinGecko /coins/markets (no API key)."""
        frames: list[pd.DataFrame] = []
        for page in range(1, pages + 1):
            params = {
                "vs_currency": vs_currency,
                "order": order,
                "per_page": per_page,
                "page": page,
                "sparkline": "false",
                "price_change_percentage": "24h,7d",
            }
            resp = self.session.get(
                COINGECKO_MARKETS_URL, params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                break
            frames.append(pd.DataFrame(rows))
            if page < pages:
                time.sleep(self.request_pause_s)

        if not frames:
            raise RuntimeError("CoinGecko markets returned no data")

        df = pd.concat(frames, ignore_index=True)
        # Bitpanda-like naming for observation context
        price = pd.to_numeric(df["current_price"], errors="coerce")
        is_eur = vs_currency.lower() == "eur"
        quote = "EUR" if is_eur else "USDT"
        out = pd.DataFrame(
            {
                "asset_id": df["id"],
                "symbol": df["symbol"].str.upper(),
                "name": df["name"],
                "pair": [
                    coin_id_to_pair(i, s, "USDT")
                    for i, s in zip(df["id"], df["symbol"])
                ],
                "quote_currency": quote,
                "market_cap": pd.to_numeric(df["market_cap"], errors="coerce"),
                "total_volume": pd.to_numeric(df["total_volume"], errors="coerce"),
                "price_change_24h_pct": pd.to_numeric(
                    df.get("price_change_percentage_24h"), errors="coerce"
                ),
                "price_change_7d_pct": pd.to_numeric(
                    df.get("price_change_percentage_7d_in_currency"), errors="coerce"
                ),
                "ath": pd.to_numeric(df.get("ath"), errors="coerce"),
                "atl": pd.to_numeric(df.get("atl"), errors="coerce"),
                "last_updated": pd.to_datetime(df.get("last_updated"), utc=True),
                "exchange_context": "bitpanda-observation",
                "data_source": "coingecko",
                "vs_currency": vs_currency.lower(),
            }
        )
        if is_eur:
            out["price_eur"] = price
            out["price_usdt"] = float("nan")
        else:
            out["price_usdt"] = price
            out["price_eur"] = float("nan")
        out["volatility_proxy_pct"] = out["price_change_7d_pct"].abs()
        out = out.loc[:, ~out.columns.duplicated()]
        logger.info("Fetched %d market rows from CoinGecko", len(out))
        return out.drop_duplicates(subset=["asset_id"]).reset_index(drop=True)

    def persist_markets(self, df: pd.DataFrame) -> Path:
        parquet_path = self.data_dir / "markets_snapshot.parquet"
        csv_path = self.data_dir / "markets_snapshot.csv"
        df.to_parquet(parquet_path, index=False)
        df.to_csv(csv_path, index=False)
        logger.info("Persisted markets snapshot -> %s", parquet_path)
        return parquet_path

    def load_markets(self) -> pd.DataFrame | None:
        parquet_path = self.data_dir / "markets_snapshot.parquet"
        csv_path = self.data_dir / "markets_snapshot.csv"
        if parquet_path.exists():
            return pd.read_parquet(parquet_path)
        if csv_path.exists():
            return pd.read_csv(csv_path, parse_dates=["last_updated"])
        return None

    def ensure_markets(
        self,
        pages: int = 2,
        per_page: int = 100,
        refresh: bool = False,
    ) -> pd.DataFrame:
        if not refresh:
            local = self.load_markets()
            if local is not None and not local.empty:
                logger.info("Using cached markets snapshot (%d rows)", len(local))
                return local
        df = self.fetch_markets(pages=pages, per_page=per_page)
        self.persist_markets(df)
        return df

    # --- Per-pair OHLCV ---

    def fetch_pair(
        self,
        pair: str,
        coin_id: str | None = None,
        interval: str = "1d",
        limit: int = 180,
        prefer: str = "coingecko",
    ) -> pd.DataFrame:
        """Fetch OHLCV for a crypto pair. Columns: open, high, low, close, volume."""
        pair = pair.upper()
        errors: list[str] = []

        def via_coingecko() -> pd.DataFrame:
            return self._fetch_coingecko(pair, coin_id=coin_id, limit=limit)

        def via_binance() -> pd.DataFrame:
            return self._fetch_binance(pair, interval=interval, limit=limit)

        providers = (
            ("coingecko", via_coingecko),
            ("binance", via_binance),
        )
        if prefer == "binance":
            providers = tuple(reversed(providers))

        for name, fetcher in providers:
            try:
                df = fetcher()
                if df is not None and not df.empty:
                    df = df.copy()
                    df["pair"] = pair
                    df["source"] = name
                    logger.info("Fetched %s (%d bars) via %s", pair, len(df), name)
                    return df
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {exc}")
                logger.warning("Provider %s failed for %s: %s", name, pair, exc)

        raise RuntimeError(f"All providers failed for {pair}: {'; '.join(errors)}")

    def persist_ohlcv(self, df: pd.DataFrame, pair: str) -> Path:
        slug = pair_to_binance_symbol(pair).lower()
        parquet_path = self.data_dir / f"{slug}.parquet"
        csv_path = self.data_dir / f"{slug}.csv"
        out = df.copy()
        if not isinstance(out.index, pd.DatetimeIndex):
            if "timestamp" in out.columns:
                out = out.set_index("timestamp")
        out.index.name = "timestamp"
        out.to_parquet(parquet_path)
        out.to_csv(csv_path)
        logger.info("Persisted %s -> %s", pair, parquet_path)
        return parquet_path

    def load_ohlcv(self, pair: str) -> pd.DataFrame | None:
        slug = pair_to_binance_symbol(pair).lower()
        parquet_path = self.data_dir / f"{slug}.parquet"
        csv_path = self.data_dir / f"{slug}.csv"
        if parquet_path.exists():
            return self._normalize_loaded(pd.read_parquet(parquet_path), pair)
        if csv_path.exists():
            df = pd.read_csv(csv_path, parse_dates=["timestamp"], index_col="timestamp")
            return self._normalize_loaded(df, pair)
        return None

    def ensure_pairs(
        self,
        pairs: Iterable[str] = DEFAULT_PAIRS,
        coin_ids: dict[str, str] | None = None,
        interval: str = "1d",
        limit: int = 180,
        refresh: bool = False,
        prefer: str = "coingecko",
    ) -> dict[str, pd.DataFrame]:
        """Load OHLCV from disk unless missing/refresh; otherwise fetch + persist."""
        coin_ids = coin_ids or {}
        result: dict[str, pd.DataFrame] = {}
        for pair in pairs:
            pair = pair.upper()
            if not refresh:
                local = self.load_ohlcv(pair)
                if local is not None and not local.empty:
                    logger.info("Using cached OHLCV for %s (%d bars)", pair, len(local))
                    result[pair] = local
                    continue
            try:
                df = self.fetch_pair(
                    pair,
                    coin_id=coin_ids.get(pair),
                    interval=interval,
                    limit=limit,
                    prefer=prefer,
                )
                self.persist_ohlcv(df, pair)
                result[pair] = df
            except Exception as exc:  # noqa: BLE001
                logger.error("Skipping %s after provider failures: %s", pair, exc)
            time.sleep(self.request_pause_s)
        return result

    def _normalize_loaded(self, df: pd.DataFrame, pair: str) -> pd.DataFrame:
        out = df.copy()
        if "timestamp" in out.columns:
            out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
            out = out.set_index("timestamp")
        if not isinstance(out.index, pd.DatetimeIndex):
            out.index = pd.to_datetime(out.index, utc=True)
        if out.index.tz is not None:
            out.index = out.index.tz_localize(None)
        out.index.name = "timestamp"
        if "pair" not in out.columns:
            out["pair"] = pair.upper()
        return out.sort_index()

    def _fetch_binance(self, pair: str, interval: str, limit: int) -> pd.DataFrame:
        symbol = pair_to_binance_symbol(pair)
        params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}
        resp = self.session.get(BINANCE_KLINES_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            raise ValueError(f"empty klines for {symbol}")

        df = pd.DataFrame(
            rows,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_volume",
                "trades",
                "taker_buy_base",
                "taker_buy_quote",
                "ignore",
            ],
        )
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        return df.dropna().sort_index()

    def _fetch_coingecko(
        self,
        pair: str,
        coin_id: str | None,
        limit: int,
    ) -> pd.DataFrame:
        base, quote = pair_base_quote(pair)
        if quote not in {"USDT", "USD"}:
            raise ValueError(f"CoinGecko supports USD/USDT quotes only, got {quote}")

        resolved_id = coin_id
        if not resolved_id:
            # Reverse lookup from known map or use lowercase symbol heuristic
            for cid, sym in _KNOWN_BINANCE_BASE.items():
                if sym == base:
                    resolved_id = cid
                    break
        if not resolved_id:
            raise ValueError(f"No CoinGecko id for {pair}; pass coin_id explicitly")

        days = max(1, min(int(limit), 365))
        url = COINGECKO_CHART_URL.format(coin_id=resolved_id)
        params = {"vs_currency": "usd", "days": days}
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json()
        prices = payload.get("prices") or []
        volumes = payload.get("total_volumes") or []
        if not prices:
            raise ValueError(f"empty CoinGecko chart for {resolved_id}")

        price_df = pd.DataFrame(prices, columns=["ts", "close"])
        price_df["timestamp"] = pd.to_datetime(price_df["ts"], unit="ms")
        price_df = price_df.set_index("timestamp")[["close"]]

        if volumes:
            vol_df = pd.DataFrame(volumes, columns=["ts", "volume"])
            vol_df["timestamp"] = pd.to_datetime(vol_df["ts"], unit="ms")
            vol_df = vol_df.set_index("timestamp")[["volume"]]
            price_df = price_df.join(vol_df, how="left")
        else:
            price_df["volume"] = 0.0

        ohlc = price_df["close"].resample("1D").ohlc()
        vol = price_df["volume"].resample("1D").mean()
        df = ohlc.join(vol.rename("volume")).dropna(subset=["close"])
        df = df.tail(limit)
        if df.empty:
            raise ValueError("CoinGecko resample produced empty frame")
        return df

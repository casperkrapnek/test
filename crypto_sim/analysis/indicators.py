"""Technical indicators tuned for 24/7 crypto markets."""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Wilder-style RSI. Crypto default window 14 (same as classic, wider extremes later)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD line, signal, histogram — defaults work on daily crypto bars."""
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    line = fast_ema - slow_ema
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = line - sig
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": hist})


def add_indicators(
    df: pd.DataFrame,
    price_col: str = "close",
    sma_windows: tuple[int, ...] = (7, 21),  # shorter than equities — crypto is faster
    ema_windows: tuple[int, ...] = (9, 21),
    rsi_window: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
) -> pd.DataFrame:
    """Return copy of OHLCV with SMA/EMA/RSI/MACD columns."""
    out = df.copy()
    price = out[price_col].astype(float)
    for w in sma_windows:
        out[f"sma_{w}"] = sma(price, w)
    for w in ema_windows:
        out[f"ema_{w}"] = ema(price, w)
    out["rsi"] = rsi(price, rsi_window)
    out = out.join(macd(price, macd_fast, macd_slow, macd_signal))
    return out

"""Rule-based buy/sell proposals for crypto (24/7, higher volatility)."""

from __future__ import annotations

import pandas as pd

from crypto_sim.analysis.indicators import add_indicators
from .base import Signal, SignalAction, SignalProvider


class RuleBasedSignalProvider(SignalProvider):
    """SMA cross + RSI + MACD histogram — crypto-tuned thresholds.

    RSI extremes slightly wider than equities (28/72) due to crypto noise.
    Designed to be replaced/extended by a model later.
    """

    def __init__(
        self,
        rsi_buy: float = 35.0,
        rsi_sell: float = 72.0,
        require_macd_confirm: bool = True,
    ) -> None:
        self.rsi_buy = rsi_buy
        self.rsi_sell = rsi_sell
        self.require_macd_confirm = require_macd_confirm

    def propose(self, pair: str, df: pd.DataFrame) -> Signal:
        if df is None or len(df) < 30:
            return Signal(pair, SignalAction.HOLD, 0.0, "insufficient bars")

        framed = add_indicators(df)
        row = framed.iloc[-1]
        prev = framed.iloc[-2]
        price = float(row["close"])

        sma_fast = row.get("sma_7")
        sma_slow = row.get("sma_21")
        rsi = row.get("rsi")
        macd_hist = row.get("macd_hist")
        prev_hist = prev.get("macd_hist")

        if pd.isna(sma_fast) or pd.isna(sma_slow) or pd.isna(rsi):
            return Signal(pair, SignalAction.HOLD, 0.0, "indicators warming up", price)

        bullish_cross = float(sma_fast) > float(sma_slow) and float(prev["sma_7"]) <= float(
            prev["sma_21"]
        )
        bearish_cross = float(sma_fast) < float(sma_slow) and float(prev["sma_7"]) >= float(
            prev["sma_21"]
        )
        macd_up = (
            not pd.isna(macd_hist)
            and not pd.isna(prev_hist)
            and float(macd_hist) > 0
            and float(prev_hist) <= 0
        )
        macd_down = (
            not pd.isna(macd_hist)
            and not pd.isna(prev_hist)
            and float(macd_hist) < 0
            and float(prev_hist) >= 0
        )

        buy_score = 0.0
        buy_reasons: list[str] = []
        if bullish_cross:
            buy_score += 0.45
            buy_reasons.append("SMA7>SMA21 cross")
        elif float(sma_fast) > float(sma_slow):
            buy_score += 0.15
            buy_reasons.append("SMA7 above SMA21")
        if float(rsi) <= self.rsi_buy:
            buy_score += 0.35
            buy_reasons.append(f"RSI oversold ({float(rsi):.1f})")
        elif float(rsi) < 50:
            buy_score += 0.1
            buy_reasons.append(f"RSI supportive ({float(rsi):.1f})")
        if macd_up or (not self.require_macd_confirm and float(macd_hist or 0) > 0):
            buy_score += 0.25
            buy_reasons.append("MACD hist turning up")

        sell_score = 0.0
        sell_reasons: list[str] = []
        if bearish_cross:
            sell_score += 0.45
            sell_reasons.append("SMA7<SMA21 cross")
        if float(rsi) >= self.rsi_sell:
            sell_score += 0.4
            sell_reasons.append(f"RSI overbought ({float(rsi):.1f})")
        if macd_down:
            sell_score += 0.25
            sell_reasons.append("MACD hist turning down")

        if buy_score >= 0.45 and buy_score >= sell_score:
            return Signal(
                pair,
                SignalAction.BUY,
                min(buy_score, 1.0),
                "; ".join(buy_reasons) or "buy rules",
                price,
            )
        if sell_score >= 0.5 and sell_score > buy_score:
            return Signal(
                pair,
                SignalAction.SELL,
                min(sell_score, 1.0),
                "; ".join(sell_reasons) or "sell rules",
                price,
            )
        return Signal(
            pair,
            SignalAction.HOLD,
            max(buy_score, sell_score),
            f"no edge (buy={buy_score:.2f}, sell={sell_score:.2f}, rsi={float(rsi):.1f})",
            price,
        )

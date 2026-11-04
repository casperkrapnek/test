"""Extendable signal interface for crypto paper trading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    pair: str
    action: SignalAction
    strength: float  # 0..1
    reason: str
    price: float | None = None

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "action": self.action.value,
            "strength": self.strength,
            "reason": self.reason,
            "price": self.price,
        }


class SignalProvider(ABC):
    """Swap rule-based for ML later without changing the portfolio loop."""

    @abstractmethod
    def propose(self, pair: str, df: pd.DataFrame) -> Signal:
        raise NotImplementedError

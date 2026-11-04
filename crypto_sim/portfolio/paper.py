"""USDT/EUR paper portfolio — simulation only, no real orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Position:
    pair: str
    quantity: float
    avg_entry: float
    cost_basis_quote: float


@dataclass
class PaperPortfolio:
    """Virtual cash portfolio quoted in EUR (crypto pairs still named */USDT)."""

    starting_cash: float = 100.0
    cash: float = 100.0
    quote_currency: str = "EUR"
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)
    exchange_context: str = "bitpanda-paper"

    def buy(
        self,
        pair: str,
        price: float,
        stake_quote: float,
        ts: datetime | None = None,
        reason: str = "",
    ) -> dict[str, Any] | None:
        pair = pair.upper()
        if price <= 0 or stake_quote <= 0:
            return None
        stake = min(stake_quote, self.cash)
        if stake <= 0:
            return None
        qty = stake / price
        pos = self.positions.get(pair)
        if pos is None:
            self.positions[pair] = Position(
                pair=pair, quantity=qty, avg_entry=price, cost_basis_quote=stake
            )
        else:
            new_cost = pos.cost_basis_quote + stake
            new_qty = pos.quantity + qty
            pos.avg_entry = new_cost / new_qty
            pos.quantity = new_qty
            pos.cost_basis_quote = new_cost
        self.cash -= stake
        trade = {
            "ts": (ts or datetime.now(timezone.utc)).isoformat(),
            "side": "BUY",
            "pair": pair,
            "price": price,
            "quantity": qty,
            "stake_quote": stake,
            "reason": reason,
            "simulation": True,
        }
        self.trades.append(trade)
        return trade

    def sell(
        self,
        pair: str,
        price: float,
        fraction: float = 1.0,
        ts: datetime | None = None,
        reason: str = "",
    ) -> dict[str, Any] | None:
        pair = pair.upper()
        pos = self.positions.get(pair)
        if pos is None or pos.quantity <= 0 or price <= 0:
            return None
        fraction = max(0.0, min(1.0, fraction))
        qty = pos.quantity * fraction
        proceeds = qty * price
        cost = pos.cost_basis_quote * fraction
        pnl = proceeds - cost
        self.cash += proceeds
        pos.quantity -= qty
        pos.cost_basis_quote -= cost
        if pos.quantity <= 1e-12:
            del self.positions[pair]
        trade = {
            "ts": (ts or datetime.now(timezone.utc)).isoformat(),
            "side": "SELL",
            "pair": pair,
            "price": price,
            "quantity": qty,
            "stake_quote": proceeds,
            "realized_pnl": pnl,
            "reason": reason,
            "simulation": True,
        }
        self.trades.append(trade)
        return trade

    def open_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "pair": p.pair,
                "quantity": p.quantity,
                "avg_entry": p.avg_entry,
                "cost_basis_quote": p.cost_basis_quote,
            }
            for p in self.positions.values()
        ]

    def equity(self, marks: dict[str, float]) -> float:
        total = self.cash
        for pair, pos in self.positions.items():
            px = marks.get(pair) or marks.get(pair.split("/")[0]) or pos.avg_entry
            total += pos.quantity * px
        return total

    def unrealized_pnl(self, marks: dict[str, float]) -> float:
        pnl = 0.0
        for pair, pos in self.positions.items():
            px = marks.get(pair) or pos.avg_entry
            pnl += pos.quantity * px - pos.cost_basis_quote
        return pnl

    def summary(self, marks: dict[str, float]) -> dict[str, Any]:
        eq = self.equity(marks)
        return {
            "starting_cash": self.starting_cash,
            "cash": self.cash,
            "equity": eq,
            "total_pnl": eq - self.starting_cash,
            "total_pnl_pct": (eq / self.starting_cash - 1.0) * 100.0,
            "unrealized_pnl": self.unrealized_pnl(marks),
            "open_positions": self.open_positions(),
            "n_trades": len(self.trades),
            "quote_currency": self.quote_currency,
            "exchange_context": self.exchange_context,
            "simulation_only": True,
        }

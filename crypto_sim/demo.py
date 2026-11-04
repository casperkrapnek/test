#!/usr/bin/env python3
"""End-to-end demo: Bitpanda universe scan → signals → €100 paper trades → PDF.

Simulation only — no real Bitpanda orders.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crypto_sim.analysis.indicators import add_indicators
from crypto_sim.analysis.stats import summarize_returns
from crypto_sim.data.bitpanda_universe import (
    CORE_HOLDINGS,
    load_universe,
    symbol_to_coingecko_id,
)
from crypto_sim.data.pipeline import CryptoDataPipeline
from crypto_sim.data.universe import (
    OpportunityRankConfig,
    rank_opportunities,
    restrict_markets_to_bitpanda,
)
from crypto_sim.portfolio.paper import PaperPortfolio
from crypto_sim.report_pdf import write_paper_trades_pdf
from crypto_sim.signals.base import SignalAction
from crypto_sim.signals.rules import RuleBasedSignalProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("demo")
VIENNA = ZoneInfo("Europe/Vienna")


def allocate_stakes(
    buy_signals: list[dict],
    cash: float = 100.0,
    reserve_pct: float = 0.08,
    max_positions: int = 5,
) -> list[dict]:
    """Weight stakes by signal strength within €100; leave a small cash reserve."""
    picks = sorted(buy_signals, key=lambda s: s["strength"], reverse=True)[:max_positions]
    if not picks:
        return []
    budget = cash * (1.0 - reserve_pct)
    total_strength = sum(max(s["strength"], 0.05) for s in picks) or 1.0
    out = []
    remaining = budget
    for i, s in enumerate(picks):
        weight = max(s["strength"], 0.05) / total_strength
        stake = round(budget * weight, 2)
        if i == len(picks) - 1:
            stake = round(remaining, 2)
        stake = min(stake, remaining)
        remaining = round(remaining - stake, 2)
        out.append({**s, "stake_eur": stake})
    return out


def run_demo(
    starting_cash: float = 100.0,
    market_pages: int = 3,
    max_focus: int = 12,
    refresh_markets: bool = True,
    pdf_path: Path | None = None,
    reports_dir: Path | None = None,
) -> dict:
    run_ts = datetime.now(VIENNA)
    reports_dir = reports_dir or (ROOT / "reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_path or Path(
        "/cursor/stores/self/docs/krypto-paper-trades-100eur.pdf"
    )

    universe = load_universe(ROOT / "data/universe/bitpanda_crypto_universe.json")
    assets = universe.get("assets") or []
    bp_symbols = {a["symbol"] for a in assets}
    cg_map = symbol_to_coingecko_id(ROOT / "data/universe/bitpanda_crypto_universe.json")
    logger.info("Bitpanda crypto universe: %d assets", len(assets))

    pipeline = CryptoDataPipeline(data_dir=ROOT / "data/market")
    try:
        markets = pipeline.fetch_markets(
            vs_currency="eur", pages=market_pages, per_page=100
        )
        markets = markets.loc[:, ~markets.columns.duplicated()]
        pipeline.persist_markets(markets)
    except Exception as exc:  # noqa: BLE001
        logger.warning("EUR markets fetch failed, falling back to cache: %s", exc)
        markets = pipeline.ensure_markets(
            pages=market_pages, per_page=100, refresh=False
        )
        markets = markets.loc[:, ~markets.columns.duplicated()]

    if "price_eur" not in markets.columns or markets["price_eur"].isna().all():
        if "price_usdt" in markets.columns:
            markets["price_eur"] = markets["price_usdt"]

    bitpanda_markets = restrict_markets_to_bitpanda(markets, bp_symbols)
    logger.info(
        "Markets overlapping Bitpanda universe: %d / %d scan rows",
        len(bitpanda_markets),
        len(markets),
    )

    rank_cfg = OpportunityRankConfig(
        min_market_cap=50_000_000.0,
        min_volume_24h=5_000_000.0,
        min_volatility_proxy_pct=2.0,
        max_focus_assets=max_focus,
        always_include_pairs=CORE_HOLDINGS,
    )
    focus = rank_opportunities(bitpanda_markets, rank_cfg)
    logger.info("Focus shortlist (%d): %s", len(focus), ", ".join(focus["pair"].tolist()))

    pair_to_id = {}
    for _, row in focus.iterrows():
        sym = str(row["symbol"]).upper()
        pair_to_id[str(row["pair"]).upper()] = row.get("asset_id") or cg_map.get(sym)

    ohlcv = pipeline.ensure_pairs(
        pairs=focus["pair"].tolist(),
        coin_ids={p: i for p, i in pair_to_id.items() if i},
        limit=120,
        refresh=refresh_markets,
        prefer="binance",  # binance.vision public klines; CoinGecko fallback
    )

    provider = RuleBasedSignalProvider()
    signals = []
    stats_by_pair = {}
    for pair, df in ohlcv.items():
        framed = add_indicators(df)
        stats = summarize_returns(framed)
        stats_by_pair[pair] = stats
        sig = provider.propose(pair, df)
        signals.append(sig.to_dict())
        logger.info(
            "Signal %s %s strength=%.2f — %s",
            pair,
            sig.action.value,
            sig.strength,
            sig.reason,
        )

    buy_signals = [s for s in signals if s["action"] == SignalAction.BUY.value]
    # If rules are quiet, fall back to strongest non-SELL among core + top scored focus
    if not buy_signals:
        logger.warning("No BUY signals — seeding core holdings with modest stakes")
        for pair in CORE_HOLDINGS:
            if pair in ohlcv:
                px = float(ohlcv[pair]["close"].iloc[-1])
                buy_signals.append(
                    {
                        "pair": pair,
                        "action": "BUY",
                        "strength": 0.55,
                        "reason": "Kern-Holding Bitpanda-Kontext (Fallback)",
                        "price": px,
                    }
                )
        # add one high-opportunity alt if available
        for _, row in focus.iterrows():
            pair = str(row["pair"]).upper()
            if pair in CORE_HOLDINGS or pair not in ohlcv:
                continue
            px = float(ohlcv[pair]["close"].iloc[-1])
            buy_signals.append(
                {
                    "pair": pair,
                    "action": "BUY",
                    "strength": 0.5,
                    "reason": "Top Opportunity im Bitpanda-Scan (Fallback)",
                    "price": px,
                }
            )
            break

    # Attach latest price if missing
    for s in buy_signals:
        if not s.get("price") and s["pair"] in ohlcv:
            s["price"] = float(ohlcv[s["pair"]]["close"].iloc[-1])

    suggestions = allocate_stakes(buy_signals, cash=starting_cash)
    portfolio = PaperPortfolio(
        starting_cash=starting_cash,
        cash=starting_cash,
        quote_currency="EUR",
        exchange_context="bitpanda-paper",
    )
    marks: dict[str, float] = {}
    for s in suggestions:
        trade = portfolio.buy(
            s["pair"],
            price=float(s["price"]),
            stake_quote=float(s["stake_eur"]),
            ts=run_ts,
            reason=s.get("reason", ""),
        )
        marks[s["pair"]] = float(s["price"])
        logger.info("Paper BUY %s stake=€%.2f qty=%.8f", s["pair"], s["stake_eur"], trade["quantity"] if trade else 0)

    summary = portfolio.summary(marks)
    avg_abs = 0.0
    if stats_by_pair:
        vals = [v.get("avg_daily_abs_pct") or 0 for v in stats_by_pair.values()]
        avg_abs = sum(vals) / max(len(vals), 1)

    report = {
        "run_ts_vienna": run_ts.isoformat(),
        "universe_count": len(assets),
        "bitpanda_market_overlap": len(bitpanda_markets),
        "focus_pairs": focus["pair"].tolist(),
        "signals": signals,
        "suggestions": suggestions,
        "portfolio": summary,
        "trades": portfolio.trades,
        "simulation_only": True,
    }
    report_path = reports_dir / "demo_run.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote report %s", report_path)

    pdf = write_paper_trades_pdf(
        out_path=pdf_path,
        suggestions=suggestions,
        portfolio_summary=summary,
        run_ts=run_ts,
        universe_count=len(assets),
        focus_count=len(focus),
        avg_daily_abs_pct=avg_abs or 3.0,
    )
    # Also keep a copy under repo reports/
    repo_pdf = reports_dir / "krypto-paper-trades-100eur.pdf"
    repo_pdf.write_bytes(Path(pdf).read_bytes())
    logger.info("PDF ready: %s", pdf)

    print("\n=== DEMO SUMMARY ===")
    print(f"Run (Vienna): {run_ts.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"Universe assets: {len(assets)}")
    print(f"Suggestions: {suggestions}")
    print(f"Portfolio: cash={summary['cash']:.2f} equity={summary['equity']:.2f} pnl={summary['total_pnl']:.2f}")
    print(f"PDF: {pdf}")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Crypto paper-trading demo (€100)")
    p.add_argument("--cash", type=float, default=100.0)
    p.add_argument("--pages", type=int, default=3)
    p.add_argument("--focus", type=int, default=12)
    p.add_argument("--no-refresh", action="store_true")
    p.add_argument(
        "--pdf",
        default="/cursor/stores/self/docs/krypto-paper-trades-100eur.pdf",
    )
    args = p.parse_args(argv)
    run_demo(
        starting_cash=args.cash,
        market_pages=args.pages,
        max_focus=args.focus,
        refresh_markets=not args.no_refresh,
        pdf_path=Path(args.pdf),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

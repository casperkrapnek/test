# Crypto Paper-Trading Simulation

Paper-only crypto trading lab focused on the **Bitpanda-tradable cryptocurrency universe**.  
Prices come from free public APIs (**CoinGecko** preferred, **Binance** fallback).  
**No real orders**, no Bitpanda trading API, no stock/Amazon paths.

Casper’s Bitpanda holdings context: **BTC** and **ETH** (always kept in the focus set).

## Features

1. **Bitpanda universe** — refreshable list from the public Bitpanda ticker (`/v1/ticker`, no API key), crypto-confirmed via CoinGecko `/coins/list`
2. **Market scan** — CoinGecko markets pages, restricted to Bitpanda-listed cryptos
3. **Opportunity ranking** — volume / volatility filters *rank* ideas inside that universe (they do not replace it with “top coins only”)
4. **Analysis** — SMA/EMA, RSI, MACD + simple return/vol stats (crypto 24/7 defaults)
5. **Rule-based signals** — extendable `SignalProvider` interface
6. **Paper portfolio** — virtual EUR cash, multi-asset positions, trade log & P&amp;L
7. **Demo + PDF** — €100 starter book and print-ready German summary

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Refresh Bitpanda universe

```bash
python -c "from crypto_sim.data.bitpanda_universe import refresh_universe; refresh_universe()"
```

Snapshot path: `data/universe/bitpanda_crypto_universe.json`  
Source documented in that file (`source`, `source_notes`, `refreshed_at_utc`).

## Configure opportunity ranking

In code or via `OpportunityRankConfig` in `crypto_sim/data/universe.py`:

| Knob | Meaning | Demo default |
|------|---------|--------------|
| `min_market_cap` | Min mcap (quote currency) | 50_000_000 |
| `min_volume_24h` | Min 24h volume | 5_000_000 |
| `min_volatility_proxy_pct` | Min \|7d %\| proxy | 2.0 |
| `max_focus_assets` | Max coins to pull OHLCV/signals for | 12 |
| `always_include_pairs` | Core holdings | BTC/USDT, ETH/USDT |

The **universe** stays the full Bitpanda crypto list; these knobs only control the analysis focus shortlist.

## Run the demo

```bash
python -m crypto_sim.demo
# or
python crypto_sim/demo.py --cash 100 --pages 3 --focus 12
```

What it does:

1. Loads Bitpanda crypto universe  
2. Scans CoinGecko markets (EUR) ∩ Bitpanda  
3. Ranks opportunities (+ forces BTC/ETH)  
4. Fetches OHLCV → indicators → rule signals  
5. Allocates **€100** paper stakes → logs buys  
6. Writes:
   - `reports/demo_run.json`
   - `reports/krypto-paper-trades-100eur.pdf`
   - Project store PDF: `/cursor/stores/self/docs/krypto-paper-trades-100eur.pdf` (when that path exists)

## Project layout

```
crypto_sim/
  data/           # pipeline, Bitpanda universe, ranking
  analysis/       # indicators + stats
  signals/        # rule-based (extendable)
  portfolio/      # paper trading
  demo.py         # end-to-end run
  report_pdf.py   # German print PDF
data/
  universe/       # bitpanda_crypto_universe.json
  market/         # cached parquet/csv
reports/          # demo artifacts
```

## Disclaimer

Simulation / paper trading only. Not financial advice. Estimates for doubling or wiping the €100 book are illustrative heuristics, not forecasts.

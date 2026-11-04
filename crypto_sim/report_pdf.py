"""Print-ready German PDF for paper-trade suggestions (EUR 100)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import XPos, YPos


VIENNA = ZoneInfo("Europe/Vienna")


def _ascii_de(text: str) -> str:
    """Helvetica core fonts are Latin-1 — fold German/unicode to safe glyphs."""
    repl = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ß": "ss",
        "—": "-",
        "–": "-",
        "€": "EUR ",
        "„": '"',
        "“": '"',
        "”": '"',
        "’": "'",
        "→": "->",
        "×": "x",
    }
    for a, b in repl.items():
        text = text.replace(a, b)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class PaperTradePDF(FPDF):
    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(
            0,
            8,
            _ascii_de(f"Nur Paper-Trading / Simulation - Seite {self.page_no()}"),
            align="C",
        )


def _est_days_to_double_or_bust(
    avg_daily_abs_pct: float,
    n_positions: int,
) -> tuple[str, str]:
    move = max(avg_daily_abs_pct, 1.5)
    days_double = max(7, int(70 / (move * 0.35)))
    days_bust = max(5, int(45 / (move * 0.45)))
    if n_positions <= 2:
        days_bust = max(3, int(days_bust * 0.7))
        days_double = int(days_double * 1.1)
    return (
        f"ca. {days_double}-{days_double + 14} Handelstage",
        f"ca. {days_bust}-{days_bust + 10} Handelstage",
    )


def write_paper_trades_pdf(
    out_path: str | Path,
    suggestions: list[dict[str, Any]],
    portfolio_summary: dict[str, Any],
    run_ts: datetime | None = None,
    universe_count: int = 0,
    focus_count: int = 0,
    avg_daily_abs_pct: float = 3.0,
) -> Path:
    run_ts = run_ts or datetime.now(VIENNA)
    if run_ts.tzinfo is None:
        run_ts = run_ts.replace(tzinfo=VIENNA)
    else:
        run_ts = run_ts.astimezone(VIENNA)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    double_est, bust_est = _est_days_to_double_or_bust(
        avg_daily_abs_pct, len(suggestions)
    )
    stake_sum = sum(float(s["stake_eur"]) for s in suggestions)

    pdf = PaperTradePDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    def line(text: str, size: int = 11, style: str = "", h: float = 6) -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.cell(0, h, _ascii_de(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def wrapped(text: str, size: int = 10, style: str = "", h: float = 5) -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(0, h, _ascii_de(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_text_color(20, 20, 20)
    line("Krypto Paper-Trades - Startkapital EUR 100", size=16, style="B", h=10)

    pdf.set_text_color(50, 50, 50)
    line(f"Datum (Europe/Vienna): {run_ts.strftime('%d.%m.%Y')}")
    line(f"Lauf-Zeitstempel: {run_ts.strftime('%d.%m.%Y %H:%M %Z')}")
    line(
        "Kontext: Bitpanda-handelbares Crypto-Universum "
        "(Preise via CoinGecko/Binance Free-API). Simulation only."
    )
    pdf.ln(2)

    pdf.set_fill_color(255, 243, 205)
    pdf.set_font("Helvetica", "B", 10)
    pdf.multi_cell(
        0,
        5,
        _ascii_de(
            "WICHTIG: Reines Paper-Trading. Keine echten Orders, kein Bitpanda-API-Handel, "
            "keine Garantie auf Gewinn. Schaetzungen zu Verdopplung/Totalverlust sind "
            "illustrative Simulation - keine Prognose."
        ),
        fill=True,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(3)

    line("KI-/Regel-Signale: vorgeschlagene Positionen", size=12, style="B", h=8)
    wrapped(
        f"Universum: {universe_count} Bitpanda-Crypto-Assets. "
        f"Fokus-Scan: {focus_count} Paare analysiert. "
        f"Eingesetzt: EUR {stake_sum:.2f} von 100.00 "
        f"(Restcash ca. EUR {100.0 - stake_sum:.2f})."
    )
    pdf.ln(2)

    cols = [("Paar", 35), ("Einsatz EUR", 30), ("Kurs", 30), ("Staerke", 25), ("Grund", 60)]
    pdf.set_font("Helvetica", "B", 10)
    for title, w in cols:
        pdf.cell(w, 7, _ascii_de(title), border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for s in suggestions:
        row = [
            str(s["pair"]),
            f"{float(s['stake_eur']):.2f}",
            f"{float(s['price']):.4g}",
            f"{float(s['strength']):.2f}",
            str(s.get("reason", ""))[:45],
        ]
        for text, (_, w) in zip(row, cols):
            pdf.cell(w, 6, _ascii_de(text), border=1)
        pdf.ln()

    pdf.ln(4)
    line("Grobe Zeitschatzung (reine Simulation)", size=12, style="B", h=8)
    wrapped(
        f"Kapital verdoppeln (EUR 200): {double_est} - KEINE GARANTIE.\n"
        f"Kapital Richtung Null: {bust_est} - KEINE GARANTIE.\n"
        "Herleitung: Heuristik aus typischer Tagesvolatilitaet der gewaehlten Coins "
        "und dem Konzentrationsrisiko des kleinen Portfolios. "
        "Crypto handelt 24/7; Pfade sind extrem unsicher."
    )

    pdf.ln(3)
    line("Paper-Portfolio nach ersten Trades", size=12, style="B", h=8)
    ps = portfolio_summary
    for row_txt in (
        f"Startkapital: EUR {ps.get('starting_cash', 100):.2f}",
        f"Cash: EUR {ps.get('cash', 0):.2f}",
        f"Equity (Mark-to-Market): EUR {ps.get('equity', 0):.2f}",
        f"P&L: EUR {ps.get('total_pnl', 0):.2f} ({ps.get('total_pnl_pct', 0):.2f}%)",
        f"Offene Positionen: {len(ps.get('open_positions') or [])}",
        f"Trades geloggt: {ps.get('n_trades', 0)}",
    ):
        line(row_txt, size=10, h=5)

    pdf.ln(3)
    pdf.set_text_color(80, 80, 80)
    wrapped(
        "Hinweis: BTC und ETH sind Kern-Holdings-Kontext (Bitpanda). "
        "Amazon/Aktien sind ausserhalb des Projekt-Scopes. "
        "Dieses Dokument wurde automatisch aus dem Demo-Lauf erzeugt.",
        size=9,
        style="I",
    )

    pdf.output(str(out_path))
    return out_path

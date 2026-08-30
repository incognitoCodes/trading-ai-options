"""
macro_calendar.py — Upcoming US macro & sector catalysts for options timing.

Premium sellers care about *scheduled volatility*. A trade whose expiry
straddles an FOMC decision, a CPI print, or the monthly jobs report carries
event risk that a naive POP calculation ignores. This module surfaces those
catalysts so the advisory can (a) warn on trades exposed to them and (b) give
the reader the "overall US market & economy" context requested in the spec.

Two kinds of catalyst:
  1. MACRO   — market-wide: FOMC, CPI, PCE, NFP, PPI, Retail Sales, GDP, ISM.
  2. SECTOR  — segment-specific notes keyed by GICS-ish sector.

FOMC dates are exact (published Fed schedule). The monthly BLS/BEA releases
are computed from their usual cadence and flagged `approx=True` because the
exact day drifts a few days month to month; they are meant as a heads-up, not
a to-the-day calendar.

DISCLAIMER: Scheduling aid only — verify exact release dates before trading.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Exact FOMC decision dates (announcement day = 2nd day of each meeting).
# Source: Federal Reserve published schedule. Extend yearly.
# ---------------------------------------------------------------------------
FOMC_DECISION_DATES = [
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
    date(2027, 1, 27),
    date(2027, 3, 17),
]


# ---------------------------------------------------------------------------
# Sector → catalyst note. Keys are lower-cased substrings matched against the
# yfinance `sector`/`industry` string so we stay robust to naming variants.
# ---------------------------------------------------------------------------
SECTOR_CATALYSTS: dict[str, str] = {
    "technology": (
        "Semis/mega-cap tech drive index vol — watch peer earnings, "
        "AI-capex headlines, and export-control policy."
    ),
    "semiconductor": (
        "Highly cyclical & headline-sensitive — SOX moves, peer guidance, "
        "and China export policy can gap the whole group."
    ),
    "communication": (
        "Ad-spend cycle + regulatory/antitrust headlines; mega-cap earnings "
        "dominate the tape."
    ),
    "consumer cyclical": (
        "Rate-sensitive demand — Retail Sales, consumer-confidence, and "
        "holiday/e-commerce data are the swing factors."
    ),
    "consumer defensive": (
        "Lower beta but FX- and input-cost sensitive; pricing-power commentary "
        "on earnings matters most."
    ),
    "financial": (
        "Rate- and curve-sensitive — CPI, FOMC, and bank earnings/credit "
        "commentary move the group."
    ),
    "healthcare": (
        "Binary drug/FDA and policy risk (drug-pricing, reimbursement); "
        "biotech single-names can gap hard."
    ),
    "energy": (
        "Crude/nat-gas prices, OPEC+ decisions, and inventory (EIA) reports "
        "drive premium."
    ),
    "industrial": (
        "PMI/ISM, durable-goods orders, and global-growth headlines set the "
        "tone; defense names track policy."
    ),
    "utilities": (
        "Bond-proxy — moves inversely with long-end yields; rate data is the "
        "main catalyst."
    ),
    "real estate": (
        "Highly rate-sensitive (REITs) — CPI/FOMC and 10Y yields dominate."
    ),
    "basic materials": (
        "Commodity prices, the US dollar, and China-demand data drive the "
        "group."
    ),
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the date of the n-th `weekday` (Mon=0..Sun=6) in a month."""
    count = 0
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        d = date(year, month, day)
        if d.weekday() == weekday:
            count += 1
            if count == n:
                return d
    raise ValueError("no such weekday")


def _last_business_day(year: int, month: int) -> date:
    """Last weekday (Mon–Fri) of a month — proxy for month-end data (PCE)."""
    day = calendar.monthrange(year, month)[1]
    d = date(year, month, day)
    while d.weekday() >= 5:  # Sat/Sun
        d -= timedelta(days=1)
    return d


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    return date(year, month, 1)


def _month_iter(today: date, horizon: date):
    """Yield (year, month) for every month touched by [today, horizon]."""
    cur = date(today.year, today.month, 1)
    while cur <= horizon:
        yield cur.year, cur.month
        cur = _add_months(cur, 1)


# Recurring monthly releases, expressed as "the n-th <weekday>" or month-end.
# (label, impact, builder(year, month) -> date, note)
def _recurring_monthly(year: int, month: int) -> list[dict]:
    releases = []

    # Employment Situation (Non-Farm Payrolls) — 1st Friday, 8:30 ET
    try:
        nfp = _nth_weekday(year, month, 4, 1)  # Friday
        releases.append({
            "event": "Nonfarm Payrolls (Jobs Report)", "date": nfp,
            "impact": "HIGH",
            "note": "Monthly jobs report — big rate/vol driver across the market.",
        })
    except ValueError:
        pass

    # CPI — usually 2nd full week (~2nd Wednesday is a decent proxy), 8:30 ET
    try:
        cpi = _nth_weekday(year, month, 2, 2)  # 2nd Wednesday
        releases.append({
            "event": "CPI Inflation", "date": cpi, "impact": "HIGH",
            "note": "Headline inflation print — top macro catalyst for rates & indices.",
        })
        # PPI typically within a day of CPI
        releases.append({
            "event": "PPI Inflation", "date": cpi + timedelta(days=1),
            "impact": "MEDIUM",
            "note": "Producer prices — secondary inflation read.",
        })
    except ValueError:
        pass

    # Retail Sales — ~mid-month (3rd Tuesday proxy)
    try:
        rs = _nth_weekday(year, month, 1, 3)  # 3rd Tuesday
        releases.append({
            "event": "Retail Sales", "date": rs, "impact": "MEDIUM",
            "note": "Consumer-demand read — moves consumer/retail names.",
        })
    except ValueError:
        pass

    # PCE (Fed's preferred inflation gauge) — month-end
    releases.append({
        "event": "Core PCE (Fed's inflation gauge)", "date": _last_business_day(year, month),
        "impact": "MEDIUM",
        "note": "Fed's preferred inflation measure — sets rate expectations.",
    })

    return releases


def upcoming_macro_events(
    within_days: int = 30,
    today: Optional[date] = None,
) -> list[dict]:
    """Return scheduled US macro catalysts within `within_days`.

    Each event: {event, date (YYYY-MM-DD), days_away, impact, approx, note}.
    Sorted by date ascending. FOMC is exact; monthly releases are approx.
    """
    today = today or datetime.now().date()
    horizon = today + timedelta(days=within_days)
    out: list[dict] = []

    # FOMC (exact)
    for fdate in FOMC_DECISION_DATES:
        if today <= fdate <= horizon:
            out.append({
                "event": "FOMC Rate Decision", "date": fdate,
                "impact": "HIGH", "approx": False,
                "note": (
                    "Fed decision + presser — market-wide IV usually spikes "
                    "into it and crushes after."
                ),
            })

    # Recurring monthly (approx)
    for yy, mm in _month_iter(today, horizon):
        for rel in _recurring_monthly(yy, mm):
            d = rel["date"]
            if today <= d <= horizon:
                rel = dict(rel)
                rel["approx"] = True
                out.append(rel)

    for e in out:
        e["days_away"] = (e["date"] - today).days
        e["date"] = e["date"].strftime("%Y-%m-%d")

    out.sort(key=lambda e: e["date"])
    return out


def macro_events_before(expiry: str, today: Optional[date] = None) -> list[dict]:
    """Macro catalysts landing on/before an option `expiry` (YYYY-MM-DD)."""
    today = today or datetime.now().date()
    try:
        exp = datetime.strptime(expiry[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return []
    dte = (exp - today).days
    if dte <= 0:
        return []
    return [e for e in upcoming_macro_events(dte, today) if e["days_away"] <= dte]


def high_impact_macro_before(expiry: str, today: Optional[date] = None) -> list[dict]:
    """HIGH-impact macro catalysts (FOMC/CPI/NFP) before an expiry."""
    return [e for e in macro_events_before(expiry, today) if e["impact"] == "HIGH"]


def sector_catalyst_note(sector: Optional[str], industry: Optional[str] = None) -> str:
    """Map a yfinance sector/industry string to a catalyst note (or "")."""
    hay = " ".join(x for x in (sector, industry) if x).lower()
    if not hay:
        return ""
    for key, note in SECTOR_CATALYSTS.items():
        if key in hay:
            return note
    return ""


if __name__ == "__main__":  # quick manual check
    import json
    print("Upcoming 30d macro events:")
    print(json.dumps(upcoming_macro_events(30), indent=2))
    print("\nSector note (Technology):", sector_catalyst_note("Technology"))

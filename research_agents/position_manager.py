"""
position_manager.py — Defensive advisory for OPEN option positions.

Pulls the trader's live option positions from MooMoo OpenD, enriches each with
real-time quote/greeks/DTE, and recommends a concrete defensive action so an
in-trouble position doesn't turn into a large loss:

  • TAKE PROFIT   — a winner has captured most of its max profit → close early.
  • CLOSE / CUT   — near expiry + ITM/high-gamma → buy-to-close, cap the risk.
  • ROLL          — buy-to-close and re-open further OTM / later expiry.
  • ADD A HEDGE   — buy a protective wing to convert a naked short into a
                    defined-risk spread.
  • HOLD          — comfortable cushion & time → monitor with a stop.

Read-only with respect to trading: this module queries positions and quotes.
It NEVER places, modifies, or closes an order — it only recommends.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

try:
    from moomoo import (
        OpenSecTradeContext, OpenQuoteContext,
        TrdEnv, TrdMarket, SecurityFirm, RET_OK,
    )
    _MOOMOO_AVAILABLE = True
except Exception:  # pragma: no cover
    _MOOMOO_AVAILABLE = False

from research_agents import config as _rcfg
from research_agents.macro_calendar import sector_catalyst_note

logger = logging.getLogger(__name__)

# US-listed leveraged/inverse ETFs whose realized moves are amplified — a short
# option on these needs a wider safety margin.
LEVERAGED_ETFS = {
    "SOXL", "SOXS", "TQQQ", "SQQQ", "SPXL", "SPXS", "TNA", "TZA",
    "KORU", "YINN", "YANG", "LABU", "LABD", "FAS", "FAZ", "UDOW", "SDOW",
    "UVXY", "SVXY", "TSLL", "NVDL", "BOIL", "KOLD", "GUSH", "DRIP",
}

_OPT_RE = re.compile(r"^(?:US\.)?([A-Z]+)(\d{6})([CP])(\d+)$")


def parse_option_code(code: str) -> Optional[dict]:
    """Parse a MooMoo option code, e.g. 'US.SOXL260831P110000'.

    Returns {underlying, expiry(YYYY-MM-DD), type(CALL/PUT), strike} or None
    if `code` is not an option contract.
    """
    if not code:
        return None
    m = _OPT_RE.match(code.strip())
    if not m:
        return None
    und, yymmdd, cp, strike_raw = m.groups()
    try:
        expiry = datetime.strptime(yymmdd, "%y%m%d").date()
    except ValueError:
        return None
    return {
        "underlying": und,
        "expiry": expiry.strftime("%Y-%m-%d"),
        "expiry_date": expiry,
        "type": "CALL" if cp == "C" else "PUT",
        "strike": int(strike_raw) / 1000.0,
    }


def _f(v, d=0.0):
    try:
        if v is None:
            return d
        return float(v)
    except (ValueError, TypeError):
        return d


class OptionPositionAdvisor:
    """Fetch open option positions and recommend defensive actions."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or getattr(_rcfg, "OPEND_HOST", "127.0.0.1")
        self.port = port or getattr(_rcfg, "OPEND_PORT", 11111)
        self._trade_ctx = None
        self._quote_ctx = None

    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        if not _MOOMOO_AVAILABLE:
            logger.warning("moomoo SDK unavailable — position advisory disabled.")
            return False
        try:
            firm = getattr(SecurityFirm, "FUTUSG", SecurityFirm.FUTUINC)
            self._trade_ctx = OpenSecTradeContext(
                host=self.host, port=self.port,
                filter_trdmarket=TrdMarket.US, security_firm=firm,
            )
            self._quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
            logger.info("Connected to MooMoo OpenD for position advisory.")
            return True
        except Exception as e:
            logger.warning(f"Position advisor could not connect to OpenD: {e}")
            self.close()
            return False

    def close(self):
        for ctx in (self._trade_ctx, self._quote_ctx):
            try:
                if ctx is not None:
                    ctx.close()
            except Exception:
                pass
        self._trade_ctx = None
        self._quote_ctx = None

    @property
    def is_connected(self) -> bool:
        return self._trade_ctx is not None and self._quote_ctx is not None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *a):
        self.close()
        return False

    # ------------------------------------------------------------------ #
    def _snapshot(self, codes: list[str]):
        try:
            ret, data = self._quote_ctx.get_market_snapshot(codes)
            if ret != RET_OK:
                return None
            return data
        except Exception:
            return None

    def fetch_option_positions(self, trd_env=None) -> list[dict]:
        """Return enriched open OPTION positions (qty != 0)."""
        if not self.is_connected:
            return []
        trd_env = trd_env or self._default_env()
        try:
            ret, data = self._trade_ctx.position_list_query(trd_env=trd_env)
        except Exception as e:
            logger.warning(f"position_list_query failed: {e}")
            return []
        if ret != RET_OK or data is None or data.empty:
            return []

        positions = []
        for _, row in data.iterrows():
            code = row.get("code", "")
            parsed = parse_option_code(code)
            if not parsed:
                continue  # not an option
            qty = _f(row.get("qty"))
            if qty == 0:
                continue
            positions.append({
                "code": code,
                "name": row.get("stock_name", code),
                **parsed,
                "qty": qty,
                "contracts": int(abs(qty)),
                "side": "SHORT" if qty < 0 else "LONG",
                "entry_price": _f(row.get("cost_price")) or _f(row.get("average_cost")),
                "mark_price": _f(row.get("nominal_price")),
                "unrealized_pl": _f(row.get("unrealized_pl")),
                "pl_ratio": _f(row.get("pl_ratio")),
                "market_val": _f(row.get("market_val")),
            })

        # Enrich with real-time option + underlying quotes
        self._enrich(positions)
        return positions

    def fetch_stock_holdings(self, trd_env=None) -> dict:
        """Return current LONG stock holdings as {ticker: {...}}.

        Used to target covered-call writes at names the trader already owns.
        Option positions are skipped, as is anything under 100 shares (the
        minimum to write one covered call). Empty dict if OpenD is unavailable.
        """
        if not self.is_connected:
            return {}
        trd_env = trd_env or self._default_env()
        try:
            ret, data = self._trade_ctx.position_list_query(trd_env=trd_env)
        except Exception as e:
            logger.warning(f"position_list_query failed: {e}")
            return {}
        if ret != RET_OK or data is None or data.empty:
            return {}

        holdings: dict = {}
        for _, row in data.iterrows():
            code = row.get("code", "")
            if parse_option_code(code):
                continue  # skip option positions
            market = code.split(".")[0] if "." in code else "US"
            if market != "US":
                continue  # US-options advisory: skip non-US holdings (e.g. SGX)
            qty = _f(row.get("qty"))
            if qty < 100:
                continue  # need at least 100 shares for one covered call
            ticker = code.split(".")[-1] if "." in code else code
            holdings[ticker] = {
                "shares": int(qty),
                "cost_price": _f(row.get("cost_price")) or _f(row.get("average_cost")),
                "current_price": _f(row.get("nominal_price")),
            }
        logger.info(f"Fetched {len(holdings)} stock holding(s) for covered calls.")
        return holdings

    def _enrich(self, positions: list[dict]):
        if not positions:
            return
        codes = [p["code"] for p in positions]
        unds = list({f"US.{p['underlying']}" for p in positions})
        opt_snap = self._snapshot(codes)
        und_snap = self._snapshot(unds)

        spot_map = {}
        if und_snap is not None:
            for _, r in und_snap.iterrows():
                spot_map[str(r.get("code"))] = _f(r.get("last_price"))

        oq = {}
        if opt_snap is not None:
            for _, r in opt_snap.iterrows():
                oq[str(r.get("code"))] = r

        today = datetime.now().date()
        for p in positions:
            r = oq.get(p["code"])
            if r is not None:
                bid = _f(r.get("bid_price"))
                ask = _f(r.get("ask_price"))
                last = _f(r.get("last_price"))
                p["bid"] = bid
                p["ask"] = ask
                p["last"] = last
                p["cur_price"] = last if last > 0 else (p["mark_price"] or 0)
                p["iv"] = _f(r.get("option_implied_volatility")) / 100.0
                p["delta"] = _f(r.get("option_delta"))
                p["open_interest"] = int(_f(r.get("option_open_interest")))
                p["quote_time"] = r.get("update_time")
            else:
                p["cur_price"] = p.get("mark_price") or 0
                p["iv"] = None
                p["delta"] = None
                p["quote_time"] = None
            p["spot"] = spot_map.get(f"US.{p['underlying']}")
            p["dte"] = (p["expiry_date"] - today).days
            p["is_leveraged_etf"] = p["underlying"] in LEVERAGED_ETFS

    def advise(self, trd_env=None) -> list[dict]:
        """Fetch positions and attach an assessment to each."""
        positions = self.fetch_option_positions(trd_env)
        for p in positions:
            p["assessment"] = self.assess(p)
        return positions

    def _default_env(self):
        env = str(getattr(_rcfg, "TRADING_ENV", "REAL")).upper() \
            if hasattr(_rcfg, "TRADING_ENV") else "REAL"
        # research_agents.config may not carry TRADING_ENV; default to REAL.
        return TrdEnv.SIMULATE if env == "SIMULATE" else TrdEnv.REAL

    # ------------------------------------------------------------------ #
    # The core: defensive assessment
    # ------------------------------------------------------------------ #
    @staticmethod
    def assess(p: dict) -> dict:
        """Return a defensive recommendation for one option position."""
        side = p["side"]
        otype = p["type"]
        strike = p["strike"]
        spot = p.get("spot")
        entry = p.get("entry_price") or 0.0
        cur = p.get("cur_price") or 0.0
        dte = p.get("dte", 0)
        delta = p.get("delta")
        abs_delta = abs(delta) if delta is not None else None
        contracts = p["contracts"]
        upl = p.get("unrealized_pl", 0.0)

        # Moneyness / cushion
        itm = None
        cushion_pct = None
        if spot and spot > 0:
            if otype == "PUT":
                itm = spot < strike
                cushion_pct = (spot - strike) / spot * 100.0
            else:  # CALL
                itm = spot > strike
                cushion_pct = (strike - spot) / spot * 100.0

        lev_note = (
            f" {p['underlying']} is a leveraged/inverse ETF — expect amplified "
            f"daily moves, so keep a wider safety margin."
            if p.get("is_leveraged_etf") else ""
        )
        sector = sector_catalyst_note(None, None)  # underlyings rarely map; skip

        actions: list[str] = []
        flags: list[str] = []

        if side == "SHORT":
            # Fraction of max profit captured (entry is the credit received).
            captured = ((entry - cur) / entry) if entry > 0 else None
            be = strike - entry if otype == "PUT" else strike + entry

            if itm:
                flags.append("IN-THE-MONEY — assignment risk")
            if dte is not None and dte <= 2:
                flags.append(f"{dte} DTE — high gamma / pin risk")
            if abs_delta is not None and abs_delta >= 0.45:
                flags.append(f"short-strike delta {abs_delta:.2f} (near ATM)")

            danger = bool(itm) or (cushion_pct is not None and cushion_pct < 1.5) \
                or (abs_delta is not None and abs_delta >= 0.45)

            if captured is not None and captured >= 0.50:
                verdict = "TAKE PROFIT"
                actions.append(
                    f"BUY-TO-CLOSE all {contracts} contract(s) now — you've "
                    f"captured ~{captured*100:.0f}% of max profit "
                    f"(sold ${entry:.2f}, now ${cur:.2f}). Lock it in and free "
                    f"the buying power."
                )
            elif danger:
                if dte is not None and dte <= 2:
                    verdict = "CLOSE / DEFEND NOW"
                    actions.append(
                        f"BUY-TO-CLOSE the {contracts}× ${strike:.0f}{otype[0]} "
                        f"now to cut the loss and remove expiry/assignment risk "
                        f"({'ITM' if itm else f'only {cushion_pct:.1f}% OTM'}, "
                        f"{dte} DTE)."
                    )
                    if otype == "PUT":
                        hedge_k = round(strike * 0.90)
                        actions.append(
                            f"OR cap the risk without closing: BUY {contracts}× "
                            f"${hedge_k:.0f} put (same expiry) to convert the naked "
                            f"short put into a defined-risk put spread."
                        )
                        actions.append(
                            f"OR roll: buy-to-close and SELL next-week "
                            f"${round((spot or strike)*0.92):.0f} put for a fresh "
                            f"credit, moving your strike further from price."
                        )
                    else:
                        hedge_k = round(strike * 1.10)
                        actions.append(
                            f"OR cap the risk: BUY {contracts}× ${hedge_k:.0f} call "
                            f"(same expiry) to define the upside risk."
                        )
                        actions.append(
                            f"OR roll: buy-to-close and SELL next-week "
                            f"${round((spot or strike)*1.08):.0f} call for a credit."
                        )
                else:
                    verdict = "DEFEND — ROLL / HEDGE"
                    if otype == "PUT":
                        roll_k = round((spot or strike) * 0.90)
                        hedge_k = round(strike * 0.90)
                        actions.append(
                            f"ROLL DOWN-AND-OUT: buy-to-close the ${strike:.0f} put "
                            f"and sell a later-dated ${roll_k:.0f} put — lowers delta "
                            f"and ideally collects more credit."
                        )
                        actions.append(
                            f"OR add a hedge: BUY a ${hedge_k:.0f} put to cap "
                            f"downside (turns the naked put into a spread)."
                        )
                    else:
                        roll_k = round((spot or strike) * 1.10)
                        hedge_k = round(strike * 1.10)
                        actions.append(
                            f"ROLL UP-AND-OUT: buy-to-close the ${strike:.0f} call "
                            f"and sell a later-dated ${roll_k:.0f} call."
                        )
                        actions.append(
                            f"OR add a hedge: BUY a ${hedge_k:.0f} call to cap upside."
                        )
            elif captured is not None and captured < 0:
                verdict = "HOLD & MONITOR"
                stop = entry * 2
                actions.append(
                    f"Still {cushion_pct:.1f}% OTM with {dte} DTE — you can hold, "
                    f"but set a stop: buy-to-close if the option hits ~${stop:.2f} "
                    f"(2× your credit) or if {p['underlying']} breaks "
                    f"${strike:.2f} (your short strike)."
                )
            else:
                verdict = "HOLD"
                tp = entry * 0.5
                actions.append(
                    f"Winning and low-risk ({cushion_pct:.1f}% OTM, {dte} DTE). "
                    f"Let theta work; take profit at ~${tp:.2f} (50% of credit)."
                )

            breakeven = be
        else:  # LONG
            pl_pct = p.get("pl_ratio", 0.0)
            if pl_pct < 0 and dte is not None and dte <= 3:
                verdict = "CLOSE — SALVAGE"
                actions.append(
                    f"SELL-TO-CLOSE {contracts}× ${strike:.0f}{otype[0]} to salvage "
                    f"remaining value — {dte} DTE, theta decay is accelerating and "
                    f"the position is down {pl_pct:.0f}%."
                )
            elif pl_pct >= 50:
                verdict = "TAKE PROFIT"
                actions.append(
                    f"SELL-TO-CLOSE (or roll up) to bank the +{pl_pct:.0f}% gain "
                    f"before theta/reversal erodes it."
                )
            else:
                verdict = "HOLD"
                actions.append(
                    f"Hold with {dte} DTE. Set a stop to cap the debit at risk."
                )
            breakeven = None

        return {
            "verdict": verdict,
            "actions": actions,
            "flags": flags,
            "itm": itm,
            "cushion_pct": round(cushion_pct, 2) if cushion_pct is not None else None,
            "breakeven": round(breakeven, 2) if side == "SHORT" and breakeven else None,
            "captured_pct": (
                round(((entry - cur) / entry) * 100, 1)
                if side == "SHORT" and entry > 0 else None
            ),
            "note": lev_note.strip(),
        }

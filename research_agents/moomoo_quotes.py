"""
moomoo_quotes.py — Real-time option premium confirmer via MooMoo OpenD.

The advisory runs a two-stage flow:
  Stage 1 (screen):  yfinance chains screen the whole universe for high IV
                     names and build candidate trades (strikes, expiry, legs).
  Stage 2 (confirm): for each candidate, THIS module pulls the ACTUAL
                     real-time bid/ask/last/IV/OI for every leg from MooMoo
                     OpenD and recomputes the true net credit, breakevens,
                     ATM IV and liquidity. Only trades we can price on the
                     real book move forward.

Why two-stage: MooMoo OpenD is rate-limited (~15 req / 30s); snapshotting full
chains for 100+ tickers at the open is impractical. We only ask MooMoo for the
handful of contracts we actually intend to recommend.

Read-only: this module ONLY queries market data (OpenQuoteContext). It never
touches the trade context and never places an order.

MooMoo schema notes (probed live):
  * Contract code:  US.<TICKER><YYMMDD><C|P><strike*1000 zero-padded>
  * get_option_chain → contract metadata only (code/strike/type).
  * get_market_snapshot → live quote+greeks: bid_price/ask_price/last_price,
    option_implied_volatility (IN PERCENT — divide by 100), option_open_interest,
    option_delta, update_time.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd

try:
    from moomoo import (
        OpenQuoteContext,
        RET_OK,
        OptionType,
        OptionCondType,
    )
    _MOOMOO_AVAILABLE = True
except Exception:  # pragma: no cover - moomoo not installed
    _MOOMOO_AVAILABLE = False

from research_agents import config as _rcfg

logger = logging.getLogger(__name__)

# Small pause between OpenD calls to respect the rate limit.
_API_SLEEP = getattr(_rcfg, "API_DELAY_SECONDS", 0.3)


def _mkt_code(ticker: str) -> str:
    return ticker if ticker.startswith("US.") else f"US.{ticker}"


def _f(val, default=0.0) -> float:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


class MoomooOptionQuotes:
    """Fetch real-time option quotes and confirm candidate trades."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or getattr(_rcfg, "OPEND_HOST", "127.0.0.1")
        self.port = port or getattr(_rcfg, "OPEND_PORT", 11111)
        self._quote_ctx = None

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        """Open a quote context. Returns True on success, False otherwise."""
        if not _MOOMOO_AVAILABLE:
            logger.warning("moomoo SDK not available — real-time premium disabled.")
            return False
        try:
            self._quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
            # A cheap probe so we fail fast if OpenD is up but not logged in.
            ret, _ = self._quote_ctx.get_global_state()
            if ret != RET_OK:
                logger.warning("OpenD reachable but not ready (not logged in?).")
            logger.info("Connected to MooMoo OpenD for real-time option quotes.")
            return True
        except Exception as e:
            logger.warning(
                f"Could not connect to MooMoo OpenD at {self.host}:{self.port} "
                f"({e}). Falling back to yfinance premiums."
            )
            self._quote_ctx = None
            return False

    def close(self):
        if self._quote_ctx is not None:
            try:
                self._quote_ctx.close()
            except Exception:
                pass
            self._quote_ctx = None

    @property
    def is_connected(self) -> bool:
        return self._quote_ctx is not None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ------------------------------------------------------------------ #
    # Low-level fetch
    # ------------------------------------------------------------------ #
    def _snapshot(self, codes: list[str]) -> Optional[pd.DataFrame]:
        if not self.is_connected or not codes:
            return None
        try:
            time.sleep(_API_SLEEP)
            ret, data = self._quote_ctx.get_market_snapshot(codes)
            if ret != RET_OK:
                logger.debug(f"snapshot failed for {codes}: {data}")
                return None
            return data
        except Exception as e:
            logger.debug(f"snapshot error: {e}")
            return None

    def get_spot(self, ticker: str) -> Optional[float]:
        snap = self._snapshot([_mkt_code(ticker)])
        if snap is None or snap.empty:
            return None
        px = _f(snap.iloc[0].get("last_price"))
        return px if px > 0 else None

    def _chain_codes(self, ticker: str, expiry: str) -> Optional[pd.DataFrame]:
        """Contract metadata (code/strike/type) for one expiry — no quotes."""
        if not self.is_connected:
            return None
        try:
            time.sleep(_API_SLEEP)
            ret, chain = self._quote_ctx.get_option_chain(
                code=_mkt_code(ticker),
                start=expiry, end=expiry,
                option_type=OptionType.ALL,
                option_cond_type=OptionCondType.ALL,
            )
            if ret != RET_OK or chain is None or chain.empty:
                return None
            return chain[["code", "strike_price", "option_type"]].copy()
        except Exception as e:
            logger.debug(f"chain fetch error {ticker} {expiry}: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Quote normalisation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_snapshot(snap: pd.DataFrame) -> pd.DataFrame:
        """Normalize a MooMoo option snapshot into tidy columns."""
        rows = []
        for _, r in snap.iterrows():
            bid = _f(r.get("bid_price"))
            ask = _f(r.get("ask_price"))
            last = _f(r.get("last_price"))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last
            rows.append({
                "code": r.get("code"),
                "option_type": str(r.get("option_type", "")).upper(),
                "strike": _f(r.get("option_strike_price")),
                "bid": bid,
                "ask": ask,
                "last": last,
                "mid": mid,
                # MooMoo IV is a percentage → decimal
                "iv": _f(r.get("option_implied_volatility")) / 100.0,
                "delta": _f(r.get("option_delta")),
                "oi": int(_f(r.get("option_open_interest"))),
                "volume": int(_f(r.get("volume"))),
                "update_time": r.get("update_time"),
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    # Leg extraction — maps a strategy dict to concrete option legs.
    # ------------------------------------------------------------------ #
    @staticmethod
    def extract_legs(trade: dict) -> Optional[list[dict]]:
        """Return [{type, side, strike}] for a trade, or None if unsupported."""
        s = trade.get("strategy")
        k = trade.get("strike")
        kl = trade.get("strike_long")
        kcs = trade.get("strike_call_sell")
        kcb = trade.get("strike_call_buy")

        def leg(t, side, strike):
            return {"type": t, "side": side, "strike": _f(strike)}

        if s == "CASH_SECURED_PUT":
            return [leg("PUT", "SELL", k)]
        if s == "CREDIT_PUT_SPREAD":
            if not kl:
                return None
            return [leg("PUT", "SELL", k), leg("PUT", "BUY", kl)]
        if s == "BEAR_CALL_SPREAD":
            if not kl:
                return None
            return [leg("CALL", "SELL", k), leg("CALL", "BUY", kl)]
        if s == "IRON_CONDOR":
            if not all([kl, kcs, kcb]):
                return None
            return [
                leg("PUT", "SELL", k), leg("PUT", "BUY", kl),
                leg("CALL", "SELL", kcs), leg("CALL", "BUY", kcb),
            ]
        if s == "IRON_BUTTERFLY":
            if not all([kl, kcb]):
                return None
            return [
                leg("PUT", "SELL", k), leg("CALL", "SELL", k),
                leg("PUT", "BUY", kl), leg("CALL", "BUY", kcb),
            ]
        if s == "JADE_LIZARD":
            if not all([kcs, kcb]):
                return None
            return [
                leg("PUT", "SELL", k),
                leg("CALL", "SELL", kcs), leg("CALL", "BUY", kcb),
            ]
        return None

    # ------------------------------------------------------------------ #
    # Confirm a candidate trade against the real book
    # ------------------------------------------------------------------ #
    def confirm_trade(
        self, trade: dict, ticker: str, spot: Optional[float] = None,
    ) -> Optional[dict]:
        """Price a candidate trade on MooMoo's real-time book.

        Returns a dict of confirmed economics, or None if the trade could not
        be priced (missing legs, no market, OpenD down). On None the caller
        keeps the yfinance estimate (clearly labelled) or drops the trade.
        """
        expiry = trade.get("expiry")
        legs = self.extract_legs(trade)
        if not expiry or not legs:
            return None

        chain = self._chain_codes(ticker, expiry)
        if chain is None or chain.empty:
            return None

        # Resolve each leg to a contract code by strike + type (tolerant match).
        leg_codes: list[str] = []
        for lg in legs:
            m = chain[
                (chain["option_type"].str.upper() == lg["type"])
                & ((chain["strike_price"] - lg["strike"]).abs() <= 0.011)
            ]
            if m.empty:
                logger.debug(
                    f"{ticker} {expiry}: no MooMoo contract for "
                    f"{lg['side']} {lg['strike']}{lg['type'][0]}"
                )
                return None
            lg["code"] = m.iloc[0]["code"]
            leg_codes.append(lg["code"])

        # Also grab a couple of near-ATM strikes for a real ATM-IV read.
        atm_codes: list[str] = []
        if spot and spot > 0:
            chain = chain.assign(_d=(chain["strike_price"] - spot).abs())
            atm_codes = chain.sort_values("_d")["code"].head(4).tolist()

        codes = list(dict.fromkeys(leg_codes + atm_codes + [_mkt_code(ticker)]))
        snap = self._snapshot(codes)
        if snap is None or snap.empty:
            return None
        q = self._normalize_snapshot(snap)
        qmap = {row["code"]: row for _, row in q.iterrows()}

        # ---- price the legs ----
        net_credit = 0.0
        leg_out = []
        min_oi = None
        worst_spread_pct = 0.0
        used_last_fallback = False
        as_of = None

        for lg in legs:
            row = qmap.get(lg["code"])
            if row is None:
                return None
            if as_of is None and row.get("update_time"):
                as_of = row["update_time"]
            bid, ask, last, mid = row["bid"], row["ask"], row["last"], row["mid"]
            if lg["side"] == "SELL":
                price = bid if bid > 0 else last
            else:
                price = ask if ask > 0 else last
            if price <= 0:
                return None
            if not (bid > 0 and ask > 0):
                used_last_fallback = True
            net_credit += price if lg["side"] == "SELL" else -price

            # liquidity
            oi = int(row["oi"])
            min_oi = oi if min_oi is None else min(min_oi, oi)
            if bid > 0 and ask > 0 and mid > 0:
                worst_spread_pct = max(worst_spread_pct, (ask - bid) / mid)

            leg_out.append({
                "type": lg["type"], "side": lg["side"], "strike": lg["strike"],
                "bid": round(bid, 2), "ask": round(ask, 2), "last": round(last, 2),
                "iv": round(row["iv"], 4), "delta": round(row["delta"], 4),
                "oi": oi,
            })

        if net_credit <= 0:
            return None

        # ---- real ATM IV of the underlying at this expiry ----
        atm_iv = None
        if spot and spot > 0:
            near = q[q["strike"] > 0].assign(_d=(q["strike"] - spot).abs())
            near = near[near["iv"] > 0].sort_values("_d")
            ivs = near["iv"].head(2).tolist()
            if ivs:
                atm_iv = round(sum(ivs) / len(ivs), 4)

        # ---- recompute economics from the confirmed credit ----
        econ = self._recompute_economics(trade, legs, net_credit, spot)

        return {
            "ok": True,
            "source": "moomoo_realtime",
            "as_of": as_of,
            "net_credit": round(net_credit, 2),
            "premium_per_contract": round(net_credit * 100, 2),
            "legs": leg_out,
            "atm_iv": atm_iv,
            "min_oi": min_oi if min_oi is not None else 0,
            "worst_spread_pct": round(worst_spread_pct, 3),
            "used_last_fallback": used_last_fallback,
            "spot": round(spot, 2) if spot else None,
            **econ,
        }

    @staticmethod
    def _recompute_economics(
        trade: dict, legs: list[dict], net_credit: float, spot: Optional[float],
    ) -> dict:
        """Recompute max profit/loss + breakevens from the confirmed credit."""
        s = trade.get("strategy")
        puts = [l for l in legs if l["type"] == "PUT"]
        calls = [l for l in legs if l["type"] == "CALL"]
        short_put = next((l for l in puts if l["side"] == "SELL"), None)
        long_put = next((l for l in puts if l["side"] == "BUY"), None)
        short_call = next((l for l in calls if l["side"] == "SELL"), None)
        long_call = next((l for l in calls if l["side"] == "BUY"), None)

        mp = round(net_credit * 100, 2)  # max profit (credit strategies)

        if s == "CASH_SECURED_PUT":
            k = short_put["strike"]
            return {
                "max_profit": mp,
                "max_loss": round((k - net_credit) * 100, 2),
                "breakeven": round(k - net_credit, 2),
                "breakeven_low": round(k - net_credit, 2),
                "breakeven_high": None,
            }
        if s == "CREDIT_PUT_SPREAD":
            width = abs(short_put["strike"] - long_put["strike"])
            return {
                "max_profit": mp,
                "max_loss": round((width - net_credit) * 100, 2),
                "breakeven": round(short_put["strike"] - net_credit, 2),
                "breakeven_low": round(short_put["strike"] - net_credit, 2),
                "breakeven_high": None,
                "spread_width": round(width, 2),
            }
        if s == "BEAR_CALL_SPREAD":
            width = abs(long_call["strike"] - short_call["strike"])
            be = round(short_call["strike"] + net_credit, 2)
            return {
                "max_profit": mp,
                "max_loss": round((width - net_credit) * 100, 2),
                "breakeven": be,
                "breakeven_high": be,
                "breakeven_low": None,
                "spread_width": round(width, 2),
            }
        if s in ("IRON_CONDOR", "IRON_BUTTERFLY"):
            put_w = abs(short_put["strike"] - long_put["strike"])
            call_w = abs(long_call["strike"] - short_call["strike"])
            max_w = max(put_w, call_w)
            return {
                "max_profit": mp,
                "max_loss": round((max_w - net_credit) * 100, 2),
                "breakeven_low": round(short_put["strike"] - net_credit, 2),
                "breakeven_high": round(short_call["strike"] + net_credit, 2),
            }
        if s == "JADE_LIZARD":
            call_w = abs(long_call["strike"] - short_call["strike"])
            no_upside = net_credit >= call_w
            downside_risk = round(max(call_w, short_put["strike"] * 0.03) * 100, 2)
            upside_risk = round(max(0.0, call_w - net_credit) * 100, 2)
            return {
                "max_profit": mp,
                "max_loss": max(upside_risk, downside_risk) or round(call_w * 100, 2),
                "breakeven": round(short_put["strike"] - net_credit, 2),
                "breakeven_low": round(short_put["strike"] - net_credit, 2),
                "breakeven_high": (
                    None if no_upside else round(short_call["strike"] + net_credit, 2)
                ),
                "no_upside_risk": no_upside,
            }
        # Unknown strategy — minimal economics
        return {"max_profit": mp, "max_loss": mp, "breakeven_low": None, "breakeven_high": None}

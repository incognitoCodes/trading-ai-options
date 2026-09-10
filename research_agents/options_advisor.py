"""
options_advisor.py — Options Premium Selling Advisory Agent.

Identifies high-probability premium selling opportunities on the
top ~100 US blue-chip stocks plus major indices (SPY, QQQ, IWM, DIA).

Strategy thesis:
  When implied volatility (IV) is elevated relative to realized/historical
  volatility (HV), options are overpriced — premium sellers profit as IV
  mean-reverts. Example: NVDA's IV often spikes on event fear, then
  crushes within days, rewarding put sellers with quick profits.

  1. Find stocks where IV > HV (options overpriced)
  2. Target high IV Percentile / IV Rank (elevated vs own history)
  3. Require high open interest (liquid, tight bid-ask)
  4. Recommend: cash-secured puts, credit spreads, iron condors

Data source: yfinance option chains (free, no API key).

DISCLAIMER: Research signals only — not financial advice.
Options involve risk of substantial loss.
"""

import time
import logging
from datetime import date as _date_type, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from research_agents.config import (
    API_DELAY_SECONDS,
    OPTIONS_DTE_WEEKLY,
    OPTIONS_DTE_NEAR,
    OPTIONS_DTE_MID,
    OPTIONS_DTE_FAR,
    OPTIONS_MIN_OPEN_INTEREST,
    OPTIONS_MIN_PREMIUM_SCORE,
    OPTIONS_MIN_IV_LEVEL,
    OPTIONS_MIN_POP,
    OPTIONS_MAX_BID_ASK_PCT,
    OPTIONS_USE_MOOMOO_REALTIME,
    OPTIONS_UNIVERSE_NAME,
    HV_WINDOW_SHORT,
    HV_WINDOW_STANDARD,
    HV_WINDOW_LONG,
)
from research_agents.dip_hunter import TOP_100_BLUE_CHIPS
from research_agents.watchlist import SP500, RUSSELL_1000

logger = logging.getLogger(__name__)

# Indices with highly liquid options markets
OPTIONS_INDICES = ["SPY", "QQQ", "IWM", "DIA"]

# Stock universe the advisory scans, selected by OPTIONS_UNIVERSE_NAME.
_UNIVERSE_BY_NAME = {
    "blue_chips": TOP_100_BLUE_CHIPS,
    "sp500": SP500,
    "russell1000": RUSSELL_1000,
}
_universe_base = _UNIVERSE_BY_NAME.get(OPTIONS_UNIVERSE_NAME, RUSSELL_1000)

# Combined universe (stocks + liquid index ETFs)
OPTIONS_UNIVERSE = list(dict.fromkeys(_universe_base + OPTIONS_INDICES))


def _avg_earnings_move(price_df: Optional[pd.DataFrame]) -> Optional[float]:
    """Estimate average post-earnings daily move from price history.

    Looks at the 4 largest single-day absolute % moves in the past year
    as a proxy for earnings reactions (earnings happen ~4 times/yr).
    Returns average absolute % move, or None if insufficient data.
    """
    if price_df is None or len(price_df) < 60:
        return None
    col = "Close" if "Close" in price_df.columns else "close"
    if col not in price_df.columns:
        return None
    pct = price_df[col].pct_change().dropna().abs() * 100
    if len(pct) < 60:
        return None
    # Top 4 largest single-day moves ≈ earnings reaction proxy
    top4 = pct.nlargest(4)
    return round(float(top4.mean()), 1)


class OptionsAdvisor:
    """Finds premium selling opportunities via volatility analysis."""

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def analyze_options(
        self,
        price_data: dict[str, pd.DataFrame],
        tickers: list[str] = None,
        holdings: dict = None,
    ) -> list[dict]:
        """Analyze option chains for the given tickers.

        Args:
            price_data: ticker -> DataFrame of daily OHLCV (1 year).
            tickers: list of tickers to scan. Defaults to OPTIONS_UNIVERSE.
            holdings: ticker -> holding dict (shares, cost_price). Names here
                also get a covered-call write generated on the shares held.

        Returns:
            list[dict] sorted by premium_score descending.
        """
        holdings = holdings or {}
        scan_list = tickers or OPTIONS_UNIVERSE
        results = []
        total = len(scan_list)

        for idx, ticker in enumerate(scan_list):
            if idx > 0 and idx % 10 == 0:
                logger.info(f"  Options scan: {idx}/{total} tickers...")
                time.sleep(API_DELAY_SECONDS)

            try:
                result = self._analyze_single(
                    ticker, price_data.get(ticker), holding=holdings.get(ticker),
                )
                if result:
                    results.append(result)
            except Exception as e:
                logger.debug(f"  Skipping {ticker} options: {e}")

        results.sort(key=lambda x: x["premium_score"], reverse=True)
        return results

    def get_top_opportunities(
        self, results: list[dict], n: int = 20,
    ) -> list[dict]:
        """Return top N premium selling opportunities."""
        return results[:n]

    @staticmethod
    def prefilter_by_dollar_volume(
        price_data: dict,
        tickers: list[str],
        top_n: int,
        always_keep: list[str] = None,
        window: int = 20,
    ) -> list[str]:
        """Rank `tickers` by recent average dollar volume and keep the top N.

        Dollar volume (close × share volume, averaged over the last `window`
        sessions) is a cheap proxy for option liquidity that we already have
        from the downloaded price history, so it needs no extra fetches. Names
        in `always_keep` (e.g. index ETFs) are retained regardless of rank.
        Returns the reduced scan list; if `top_n` <= 0 the full list is kept.
        """
        always_keep = list(always_keep or [])
        if not top_n or top_n <= 0:
            return list(dict.fromkeys(tickers))

        scores: dict[str, float] = {}
        for t in tickers:
            df = price_data.get(t)
            if df is None or len(df) == 0:
                continue
            cols = {c.lower(): c for c in df.columns}
            close_c = cols.get("close")
            vol_c = cols.get("volume")
            if not close_c or not vol_c:
                continue
            dv = (df[close_c] * df[vol_c]).tail(window).dropna()
            if len(dv) == 0:
                continue
            scores[t] = float(dv.mean())

        ranked = sorted(scores, key=scores.get, reverse=True)[:top_n]
        keep = [t for t in always_keep if t in set(tickers)]
        return list(dict.fromkeys(ranked + keep))

    @staticmethod
    def enrich_sentiment(results: list[dict], tickers) -> list[dict]:
        """Attach recent-news tone to the given tickers and blend trader_bias.

        News is one network call per ticker, so only the recommended shortlist
        is enriched. Options positioning and hold quality are already on each
        result from _analyze_single.
        """
        from research_agents import sentiment as _sent
        want = set(tickers or [])
        for r in results:
            if r.get("ticker") not in want:
                continue
            ns = _sent.news_sentiment(r["ticker"])
            r["news_sentiment"] = ns
            pos_label = (r.get("options_positioning") or {}).get("label", "Neutral")
            r["trader_bias"] = _sent.combined_bias(ns.get("label", "Neutral"), pos_label)
        return results

    # ------------------------------------------------------------------ #
    # Stage 2 — real-time confirmation + high-probability gate
    # ------------------------------------------------------------------ #
    def confirm_and_gate(
        self,
        results: list[dict],
        realtime=None,
        today=None,
    ) -> dict:
        """Confirm candidate trades on MooMoo real-time data and apply the
        high-probability gate.

        For every candidate trade on every name that cleared the IV screen:
          1. Pull the ACTUAL premium/greeks/OI for its legs from MooMoo.
          2. Overwrite the estimated economics with the confirmed ones and
             recompute POP on the real ATM IV.
          3. Attach the macro/sector events that land before expiry.
          4. Decide `high_prob` via `_high_prob_gate`.

        Only trades with `high_prob=True` should be recommended / put in the
        portfolio. Returns a small summary dict for the report banner.

        `realtime` is a connected MoomooOptionQuotes (or None → yfinance-only,
        in which case nothing is real-time-confirmed and the report says so).
        """
        from research_agents.macro_calendar import (
            macro_events_before, high_impact_macro_before,
        )

        rt_available = bool(realtime and getattr(realtime, "is_connected", False))
        n_candidates = 0
        n_confirmed = 0
        n_high_prob = 0
        as_of = None

        for r in results:
            iv_pass = r.get("iv_level_pass")
            trade_list = r.get("trades", []) + r.get("weekly_trades", [])
            has_cc = any(t.get("strategy") == "COVERED_CALL" for t in trade_list)
            # Names that missed the IV screen are still processed if they carry
            # a covered call (income on shares you hold), otherwise skipped.
            if not iv_pass and not has_cc:
                continue
            ticker = r["ticker"]
            spot = r.get("current_price")
            hv_20 = r.get("hv_20")
            events = r.get("upcoming_events", [])

            spot_rt = None
            if rt_available:
                try:
                    spot_rt = realtime.get_spot(ticker)
                except Exception:
                    spot_rt = None
            spot_used = spot_rt or spot

            for trade in trade_list:
                if trade.get("strategy") == "EVENT_WARNING":
                    continue
                # If the name did not clear the IV screen, only its covered
                # call is eligible, not new premium-selling trades.
                if not iv_pass and trade.get("strategy") != "COVERED_CALL":
                    continue
                n_candidates += 1

                # Macro/sector catalysts before this expiry (independent of RT)
                expiry = trade.get("expiry")
                trade["macro_before"] = macro_events_before(expiry, today)
                trade["macro_high_impact"] = high_impact_macro_before(expiry, today)
                trade["sector_note"] = r.get("sector_note", "")

                conf = None
                if rt_available:
                    try:
                        conf = realtime.confirm_trade(trade, ticker, spot=spot_used)
                    except Exception as e:
                        logger.debug(f"confirm_trade failed {ticker}: {e}")
                        conf = None

                real_iv = r.get("atm_iv")
                if conf and conf.get("ok"):
                    n_confirmed += 1
                    as_of = as_of or conf.get("as_of")
                    real_iv = conf.get("atm_iv") or real_iv
                    # Overwrite estimated economics with confirmed ones
                    trade["premium"] = conf["net_credit"]
                    trade["premium_per_contract"] = conf["premium_per_contract"]
                    for key in (
                        "max_profit", "max_loss", "breakeven",
                        "breakeven_low", "breakeven_high", "spread_width",
                        "no_upside_risk",
                    ):
                        if key in conf:
                            trade[key] = conf[key]
                    trade["min_oi"] = conf.get("min_oi")
                    trade["worst_spread_pct"] = conf.get("worst_spread_pct")
                    trade["confirmed_legs"] = conf.get("legs")
                    trade["premium_source"] = "MooMoo real-time"
                    trade["as_of"] = conf.get("as_of")
                    trade["confirmed"] = True
                    trade["real_atm_iv"] = real_iv
                    # Recompute POP on the confirmed premium + real ATM IV
                    trade["pop"] = self._recompute_pop(trade, spot_used, real_iv)
                else:
                    trade["premium_source"] = (
                        "yfinance (indicative — OpenD offline)"
                        if rt_available is False
                        else "yfinance (indicative — not confirmed)"
                    )
                    trade["confirmed"] = False
                    trade["real_atm_iv"] = real_iv

                # Apply the high-probability gate
                passed, reasons = self._high_prob_gate(
                    trade, real_iv, hv_20, events,
                )
                trade["high_prob"] = passed
                trade["gate_reasons"] = reasons
                if passed:
                    n_high_prob += 1

        return {
            "realtime_available": rt_available,
            "candidates": n_candidates,
            "confirmed": n_confirmed,
            "high_prob": n_high_prob,
            "as_of": as_of,
        }

    @staticmethod
    def _recompute_pop(trade: dict, spot: float, iv: float) -> Optional[float]:
        """POP on the confirmed premium/breakevens and real ATM IV."""
        if not spot or spot <= 0:
            return trade.get("pop")
        trade_iv = iv if iv and iv > 0 else 0.30
        dte = trade.get("dte", 30)
        strategy = trade.get("strategy", "")
        be_low = trade.get("breakeven_low") or trade.get("breakeven")
        be_high = trade.get("breakeven_high")
        pop = None
        if strategy == "COVERED_CALL":
            k = trade.get("strike")
            if k and k > 0:
                pop = OptionsAdvisor._estimate_pop(spot, 0.01, k, trade_iv, dte)
        elif strategy == "BEAR_CALL_SPREAD":
            if be_high and be_high > 0:
                pop = OptionsAdvisor._estimate_pop(spot, 0.01, be_high, trade_iv, dte)
        elif be_high is not None and be_low and be_low > 0:
            pop = OptionsAdvisor._estimate_pop(spot, be_low, be_high, trade_iv, dte)
        elif be_low and be_low > 0:
            pop = OptionsAdvisor._estimate_pop(spot, be_low, None, trade_iv, dte)
        return round(pop * 100, 1) if pop is not None else None

    @staticmethod
    def _high_prob_gate(
        trade: dict,
        real_atm_iv: Optional[float],
        hv_20: Optional[float],
        upcoming_events: list[dict],
    ) -> tuple[bool, list[str]]:
        """Decide whether a trade is a HIGH-PROBABILITY recommendation.

        A trade must clear ALL of:
          • real-premium POP ≥ OPTIONS_MIN_POP (default 50%)
          • IV richness: ATM IV > 20-day HV (options actually overpriced)
          • liquidity: worst-leg OI ≥ min, bid/ask spread ≤ max
          • no binary (earnings) event on/before expiry
        A HIGH-impact macro event before expiry does not disqualify but is
        recorded as a caution (and requires a slightly higher POP cushion).
        """
        reasons: list[str] = []
        dte = trade.get("dte", 30)
        is_covered_call = trade.get("strategy") == "COVERED_CALL"

        # Only real-premium confirmed trades can be "high probability"
        if not trade.get("confirmed"):
            return False, ["premium not confirmed on MooMoo real-time book"]

        pop = trade.get("pop")
        macro_hi = trade.get("macro_high_impact") or []
        min_pop = OPTIONS_MIN_POP + (2.0 if macro_hi else 0.0)
        if pop is None:
            return False, ["no POP"]
        if pop < min_pop:
            reasons.append(
                f"POP {pop:.0f}% < required {min_pop:.0f}%"
                + (" (raised for macro event)" if macro_hi else "")
            )

        # IV richness — required for pure premium selling, but NOT for covered
        # calls, which are income on shares you already own in any IV regime.
        if (
            not is_covered_call
            and real_atm_iv is not None and hv_20 is not None
            and real_atm_iv <= hv_20
        ):
            reasons.append(
                f"IV {real_atm_iv*100:.0f}% not above HV {hv_20*100:.0f}% "
                f"(premium not overpriced)"
            )

        # Liquidity
        min_oi = trade.get("min_oi")
        if min_oi is not None and min_oi < OPTIONS_MIN_OPEN_INTEREST:
            reasons.append(f"thin liquidity (min OI {min_oi})")
        wsp = trade.get("worst_spread_pct")
        if wsp is not None and wsp > OPTIONS_MAX_BID_ASK_PCT:
            reasons.append(f"wide bid/ask ({wsp*100:.0f}%)")

        # Binary earnings risk before expiry → disqualify
        for ev in (upcoming_events or []):
            if ev.get("event") == "Earnings Report" and ev.get("days_away", 999) <= dte:
                reasons.append(
                    f"earnings in {ev['days_away']}d (before expiry) — binary risk"
                )
                break

        return (len(reasons) == 0), reasons

    def build_weekly_portfolio(
        self,
        results: list[dict],
        target_premium: float = 5000.0,
        max_contracts: int = 30,
        max_per_ticker: int = 10,
        max_trades: int = 10,
    ) -> dict:
        """Build a curated weekly trade portfolio targeting $5K+ premium.

        Selects the best trades from analyzed results, prioritizing:
        1. High reward/risk ratio (defined-risk spreads preferred)
        2. Diversification across tickers
        3. Hitting the target within contract limit

        Args:
            results: list of analyzed ticker dicts (from analyze_options)
            target_premium: weekly premium income target in dollars
            max_contracts: maximum total contracts (margin constraint)
            max_per_ticker: max contracts allocated to one ticker

        Returns:
            dict with trades list, totals, and target metrics.
        """
        # Collect all viable trade candidates. Post-gate, the portfolio is
        # filled ONLY with high-probability trades that were confirmed on the
        # real MooMoo book (see confirm_and_gate). We consider weekly trades
        # first (DTE ≤ 9, the "$5K/week" cadence) but fall back to any gated
        # trade so the target can still be pursued on quiet weeks.
        candidates = []
        seen_keys: set = set()
        for r in results:
            if not r.get("iv_level_pass"):
                continue
            if r.get("premium_score", 0) < OPTIONS_MIN_PREMIUM_SCORE:
                continue
            weekly = r.get("weekly_trades") or []
            regular = r.get("trades") or []
            # Weekly first, then all other gated trades (any DTE). The
            # high-probability gate + dedup below are the real controls — a
            # gated mid-term credit spread is still valid weekly income and
            # must not be dropped just for sitting outside the weekly window.
            trade_list = weekly + regular
            for trade in trade_list:
                if trade.get("strategy") == "EVENT_WARNING":
                    continue
                if trade.get("strategy") == "COVERED_CALL":
                    continue  # placed first by the covered-call priority pass
                if trade.get("premium", 0) <= 0:
                    continue
                # HIGH-PROBABILITY GATE — only confirmed, gated trades qualify.
                if not trade.get("high_prob"):
                    continue
                key = (
                    r["ticker"], trade.get("strategy"),
                    trade.get("expiry"), trade.get("strike"),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                pop = trade.get("pop")

                premium_per_contract = trade["premium"] * 100
                max_profit = trade.get("max_profit", 0)
                max_loss = trade.get("max_loss", 0)

                if max_loss <= 0 or max_profit <= 0:
                    continue
                # These trades already cleared the high-probability gate
                # (POP ≥ 50%, IV>HV, liquid, no binary event). High-POP credit
                # spreads inherently risk more than they collect (a 30-delta
                # put spread is ~1:4), so we DON'T impose the old 2× R/R cap
                # here — that would reject exactly the trades the gate surfaces.
                # We only block pathological tail-risk selling (max loss > 8×
                # the credit), where a single loss wipes out many wins.
                if max_loss > max_profit * 8:
                    continue

                rr_ratio = max_profit / max_loss

                candidates.append({
                    "ticker": r["ticker"],
                    "current_price": r["current_price"],
                    "strategy": trade["strategy"],
                    "strategy_display": trade["strategy_display"],
                    "action": trade["action"],
                    "strike": trade.get("strike", 0),
                    "expiry": trade.get("expiry", ""),
                    "dte": trade.get("dte", 0),
                    "premium_per_share": trade["premium"],
                    "premium_per_contract": round(premium_per_contract, 2),
                    "max_profit_per_contract": max_profit,
                    "max_loss_per_contract": max_loss,
                    "rr_ratio": round(rr_ratio, 3),
                    "breakeven": trade.get("breakeven", 0),
                    "pop": pop,
                    "expected_move_pct": trade.get("expected_move_pct"),
                    "daily_move_pct": trade.get("daily_move_pct") or r.get("daily_move_pct"),
                    "events_before_expiry": r.get("upcoming_events", []),
                    "score": r["premium_score"],
                    "atm_iv": r.get("atm_iv"),
                    "iv_premium": r.get("iv_premium"),
                    "hold_quality": (r.get("hold_quality") or {}).get("score") or 50,
                })

        if not candidates:
            return {
                "trades": [],
                "total_premium": 0,
                "total_contracts": 0,
                "target": target_premium,
                "pct_of_target": 0,
                "max_contracts": max_contracts,
                "total_max_loss": 0,
            }

        # ---- Risk-tier diversification ----
        # Split candidates into buckets by risk profile so portfolio blends
        # aggressive premium generators with conservative defined-risk trades.
        AGGRESSIVE = {"IRON_BUTTERFLY"}
        MODERATE = {"IRON_CONDOR", "JADE_LIZARD"}
        CONSERVATIVE = {"CREDIT_PUT_SPREAD", "BEAR_CALL_SPREAD", "CASH_SECURED_PUT"}

        risk_label = {}
        for s in AGGRESSIVE:
            risk_label[s] = "aggressive"
        for s in MODERATE:
            risk_label[s] = "moderate"
        for s in CONSERVATIVE:
            risk_label[s] = "conservative"

        def _sort_key(x):
            # Reward/risk first, then hold-quality (a name you'd be glad to own
            # if assigned floats up), then premium score.
            return (x["rr_ratio"], x.get("hold_quality", 50), x["score"])

        buckets: dict[str, list] = {
            "aggressive": sorted(
                [c for c in candidates if c["strategy"] in AGGRESSIVE],
                key=_sort_key, reverse=True,
            ),
            "moderate": sorted(
                [c for c in candidates if c["strategy"] in MODERATE],
                key=_sort_key, reverse=True,
            ),
            "conservative": sorted(
                [c for c in candidates if c["strategy"] in CONSERVATIVE],
                key=_sort_key, reverse=True,
            ),
        }

        # Target allocation: ~40% aggressive, ~30% moderate, ~30% conservative
        # (by premium contribution, not by count)
        tier_targets = {
            "aggressive": 0.40,
            "moderate": 0.30,
            "conservative": 0.30,
        }

        # Greedy multi-tier allocation
        portfolio: list[dict] = []
        total_premium = 0.0
        total_contracts = 0
        total_max_loss = 0.0
        used_tickers: dict[str, int] = {}
        tier_premium: dict[str, float] = {
            "aggressive": 0.0,
            "moderate": 0.0,
            "conservative": 0.0,
        }
        # Track consumed indices per bucket
        bucket_idx: dict[str, int] = {
            "aggressive": 0,
            "moderate": 0,
            "conservative": 0,
        }

        def _pick_next_tier() -> str | None:
            """Pick the tier that is furthest below its target allocation."""
            best_tier = None
            best_gap = -999.0
            for tier, target_pct in tier_targets.items():
                if bucket_idx[tier] >= len(buckets[tier]):
                    continue  # exhausted
                current_pct = (
                    tier_premium[tier] / total_premium
                    if total_premium > 0 else 0.0
                )
                gap = target_pct - current_pct
                if gap > best_gap:
                    best_gap = gap
                    best_tier = tier
            return best_tier

        MAX_ITERS = len(candidates) * 2  # safety
        iters = 0
        while (
            total_contracts < max_contracts
            and len(portfolio) < max_trades
            and iters < MAX_ITERS
        ):
            iters += 1
            # Don't overshoot target by more than 60%
            if total_premium >= target_premium * 1.6 and len(portfolio) >= 5:
                break

            tier = _pick_next_tier()
            if tier is None:
                break  # all buckets exhausted

            # Find the next unused candidate in this tier
            cand = None
            while bucket_idx[tier] < len(buckets[tier]):
                c = buckets[tier][bucket_idx[tier]]
                bucket_idx[tier] += 1
                tk = c["ticker"]
                if used_tickers.get(tk, 0) < max_per_ticker:
                    cand = c
                    break

            if cand is None:
                # This tier is exhausted; mark it so we skip it
                bucket_idx[tier] = len(buckets[tier])
                continue

            ticker = cand["ticker"]
            ticker_used = used_tickers.get(ticker, 0)

            remaining_contracts = max_contracts - total_contracts
            remaining_premium = target_premium - total_premium

            if remaining_premium > 0:
                n_needed = max(
                    1,
                    int(remaining_premium / cand["premium_per_contract"]) + 1,
                )
            else:
                n_needed = 1

            # For conservative trades, allow more contracts to hit premium target
            n_contracts = min(
                n_needed,
                remaining_contracts,
                max_per_ticker - ticker_used,
            )
            n_contracts = max(1, n_contracts)

            trade_premium = round(n_contracts * cand["premium_per_contract"], 2)
            trade_max_loss = round(
                n_contracts * cand["max_loss_per_contract"], 2,
            )
            trade_max_profit = round(
                n_contracts * cand["max_profit_per_contract"], 2,
            )

            tier_key = risk_label.get(cand["strategy"], "conservative")
            remark = self._portfolio_remark(cand, tier_key)

            portfolio.append({
                "ticker": cand["ticker"],
                "current_price": cand["current_price"],
                "strategy": cand["strategy"],
                "strategy_display": cand["strategy_display"],
                "action": cand["action"],
                "expiry": cand["expiry"],
                "dte": cand["dte"],
                "contracts": n_contracts,
                "premium_per_contract": cand["premium_per_contract"],
                "total_premium": trade_premium,
                "max_profit_per_contract": cand["max_profit_per_contract"],
                "max_loss_per_contract": cand["max_loss_per_contract"],
                "total_max_profit": trade_max_profit,
                "total_max_loss": trade_max_loss,
                "rr_ratio": cand["rr_ratio"],
                "pop": cand.get("pop"),
                "expected_move_pct": cand.get("expected_move_pct"),
                "daily_move_pct": cand.get("daily_move_pct"),
                "events_before_expiry": [
                    e.get("event", "") for e in cand.get("events_before_expiry", [])
                    if e.get("days_away", 999) <= cand.get("dte", 9) + 1
                ],
                "score": cand["score"],
                "remark": remark,
                "risk_tier": tier_key,
            })

            total_premium += trade_premium
            total_contracts += n_contracts
            total_max_loss += trade_max_loss
            tier_premium[tier_key] += trade_premium
            used_tickers[ticker] = ticker_used + n_contracts

        # Sort portfolio by risk tier for display: conservative → moderate → aggressive
        tier_order = {"conservative": 0, "moderate": 1, "aggressive": 2}
        portfolio.sort(
            key=lambda t: (
                tier_order.get(t.get("risk_tier", ""), 1),
                -t["rr_ratio"],
            ),
        )

        return {
            "trades": portfolio,
            "total_premium": round(total_premium, 2),
            "total_contracts": total_contracts,
            "target": target_premium,
            "pct_of_target": round(
                total_premium / target_premium * 100, 1,
            ) if target_premium > 0 else 0,
            "max_contracts": max_contracts,
            "total_max_loss": round(total_max_loss, 2),
            "tier_breakdown": {
                k: round(v, 2) for k, v in tier_premium.items()
            },
        }

    # ------------------------------------------------------------------ #
    # Two-part portfolio: Part 1 (high-conviction) + Part 2 (target fillers)
    # ------------------------------------------------------------------ #
    _TIER_OF = {
        "IRON_BUTTERFLY": "aggressive",
        "IRON_CONDOR": "moderate", "JADE_LIZARD": "moderate",
        "CREDIT_PUT_SPREAD": "conservative", "BEAR_CALL_SPREAD": "conservative",
        "CASH_SECURED_PUT": "conservative", "COVERED_CALL": "conservative",
    }

    def _collect_covered_calls(
        self, results: list[dict], max_trades: int,
        max_contracts: int, max_per_ticker: int,
    ) -> list[dict]:
        """Select gated covered calls on held names, best first (top priority).

        Returns ready-to-render portfolio trade entries. Sizing is capped by
        the shares held (contracts_possible), max_per_ticker, the shared
        contract budget, and the overall trade-count cap. These are income on
        stock already owned, so their `total_max_loss` is a framework nominal
        (the premium), not new capital at risk.
        """
        cands = []
        seen = set()
        for r in results:
            for trade in (r.get("trades") or []) + (r.get("weekly_trades") or []):
                if trade.get("strategy") != "COVERED_CALL":
                    continue
                if not trade.get("high_prob"):
                    continue
                key = (r["ticker"], trade.get("expiry"), trade.get("strike"))
                if key in seen:
                    continue
                seen.add(key)
                cands.append((r, trade))

        # Best first: highest POP, then best static (premium-only) return.
        cands.sort(
            key=lambda rt: (rt[1].get("pop") or 0, rt[1].get("static_return_pct") or 0),
            reverse=True,
        )

        out: list[dict] = []
        contracts_left = max_contracts
        used_tickers: dict[str, int] = {}
        for r, trade in cands:
            if len(out) >= max_trades or contracts_left <= 0:
                break
            tk = r["ticker"]
            tused = used_tickers.get(tk, 0)
            if tused >= max_per_ticker:
                continue
            poss = int(trade.get("contracts_possible") or 1)
            n = max(1, min(poss, max_per_ticker - tused, contracts_left))
            ppc = trade.get("premium_per_contract") or round(trade.get("premium", 0) * 100, 2)
            mppc = trade.get("max_profit") or ppc
            mlpc = trade.get("max_loss") or ppc
            out.append({
                "ticker": tk, "current_price": r.get("current_price"),
                "strategy": "COVERED_CALL",
                "strategy_display": trade.get("strategy_display", "Covered Call"),
                "action": trade.get("action", ""), "expiry": trade.get("expiry", ""),
                "dte": trade.get("dte", 30), "contracts": n,
                "premium_per_contract": ppc, "total_premium": round(n * ppc, 2),
                "max_profit_per_contract": mppc, "max_loss_per_contract": mlpc,
                "total_max_profit": round(n * mppc, 2),
                "total_max_loss": round(n * mlpc, 2),
                "rr_ratio": round(mppc / mlpc, 3) if mlpc else 0,
                "pop": trade.get("pop"),
                "share_backed": True,
                "shares_held": trade.get("shares_held"),
                "if_called_return_pct": trade.get("if_called_return_pct"),
                "static_return_pct": trade.get("static_return_pct"),
                "daily_move_pct": trade.get("daily_move_pct") or r.get("daily_move_pct"),
                "events_before_expiry": [],
                "score": r.get("premium_score", 0),
                "risk_tier": "conservative", "part": "core",
                "remark": (
                    f"🟢 Covered call on {trade.get('shares_held', 0)} sh held "
                    f"— priority income"
                ),
            })
            contracts_left -= n
            used_tickers[tk] = tused + n
        return out

    def build_two_part_portfolio(
        self,
        results: list[dict],
        target: float = 4000.0,
        max_contracts: int = 30,
        max_per_ticker: int = 5,
        fill_min_pop: float = None,
        max_trades: int = 10,
    ) -> dict:
        """Build a two-part weekly portfolio toward `target` (default $4K).

        Part 1 — CORE: only trades that cleared the full high-probability gate
                 (POP ≥ 50%, IV>HV, liquid, no binary event). Real-premium.
        Part 2 — FILL: if the core falls short of the target, top it up with
                 confirmed real-premium trades that JUST missed the gate
                 (fill_min_pop ≤ POP < OPTIONS_MIN_POP, still liquid, no
                 earnings before expiry). Clearly labelled lower-conviction.

        Returns a dict with core_trades / fill_trades and combined totals. The
        `trades` key holds core+fill for any single-list consumer.
        """
        if fill_min_pop is None:
            # Fillers sit just below the core POP bar, keeping the same
            # 15-point band the gate has used historically, so Part 2 stays
            # coherent whenever the core bar moves via OPTIONS_MIN_POP.
            fill_min_pop = max(OPTIONS_MIN_POP - 15.0, 0.0)

        # ---- Priority: covered calls on held names (easy-money income) ----
        # These are written first, before any premium-selling core trade, and
        # they consume from the same contract and trade-count budgets.
        covered_trades = self._collect_covered_calls(
            results, max_trades=max_trades, max_contracts=max_contracts,
            max_per_ticker=max_per_ticker,
        )
        cc_premium = round(sum(t["total_premium"] for t in covered_trades), 2)
        cc_contracts = sum(t["contracts"] for t in covered_trades)
        cc_max_loss = round(sum(t["total_max_loss"] for t in covered_trades), 2)

        # ---- Part 1b: premium-selling core on the remaining budget ----
        core = self.build_weekly_portfolio(
            results, target_premium=max(0.0, target - cc_premium),
            max_contracts=max(0, max_contracts - cc_contracts),
            max_per_ticker=max_per_ticker,
            max_trades=max(0, max_trades - len(covered_trades)),
        )
        for t in core["trades"]:
            t["part"] = "core"

        # Covered calls lead the core list (top priority).
        core_list = covered_trades + core["trades"]

        # Combined core + fill trade count is capped at max_trades. Core (with
        # covered calls first) fills these slots; fillers only top up the rest.
        trades_left = max(0, max_trades - len(core_list))

        used_keys = {
            (t["ticker"], t["strategy"], t.get("expiry"), t.get("action"))
            for t in core_list
        }
        used_tickers: dict[str, int] = {}
        for t in core_list:
            used_tickers[t["ticker"]] = used_tickers.get(t["ticker"], 0) + t["contracts"]

        core_premium = round(core["total_premium"] + cc_premium, 2)
        core_contracts = core["total_contracts"] + cc_contracts
        core_max_loss = round(core["total_max_loss"] + cc_max_loss, 2)

        remaining = target - core_premium
        contracts_left = max_contracts - core_contracts

        # ---- collect FILL candidates (confirmed near-misses) ----
        fills: list[dict] = []
        for r in results:
            if not r.get("iv_level_pass"):
                continue
            events = r.get("upcoming_events", [])
            for trade in (r.get("weekly_trades") or []) + (r.get("trades") or []):
                if trade.get("strategy") == "EVENT_WARNING":
                    continue
                if trade.get("strategy") == "COVERED_CALL":
                    continue          # covered calls are core-only, never fillers
                if not trade.get("confirmed"):
                    continue          # fillers must still be real-premium priced
                if trade.get("high_prob"):
                    continue          # already eligible for core
                pop = trade.get("pop")
                if pop is None or pop < fill_min_pop:
                    continue
                if (trade.get("min_oi") or 0) < OPTIONS_MIN_OPEN_INTEREST:
                    continue
                if (trade.get("worst_spread_pct") or 1.0) > OPTIONS_MAX_BID_ASK_PCT:
                    continue
                dte = trade.get("dte", 30)
                if any(
                    e.get("event") == "Earnings Report"
                    and e.get("days_away", 999) <= dte
                    for e in events
                ):
                    continue          # never fill with binary earnings risk
                mp = trade.get("max_profit", 0)
                ml = trade.get("max_loss", 0)
                if mp <= 0 or ml <= 0 or ml > mp * 8:
                    continue
                key = (r["ticker"], trade["strategy"], trade.get("expiry"), trade.get("action"))
                if key in used_keys:
                    continue
                fills.append({
                    "ticker": r["ticker"], "current_price": r["current_price"],
                    "strategy": trade["strategy"],
                    "strategy_display": trade["strategy_display"],
                    "action": trade["action"], "expiry": trade.get("expiry", ""),
                    "dte": dte, "premium_per_contract": round(trade["premium"] * 100, 2),
                    "max_profit_per_contract": mp, "max_loss_per_contract": ml,
                    "rr_ratio": round(mp / ml, 3), "pop": pop,
                    "score": r["premium_score"],
                    "daily_move_pct": trade.get("daily_move_pct") or r.get("daily_move_pct"),
                    "events_before_expiry": r.get("upcoming_events", []),
                    "key": key,
                })

        # Best fillers first: highest POP, then best reward/risk
        fills.sort(key=lambda c: (c["pop"], c["rr_ratio"]), reverse=True)

        fill_trades: list[dict] = []
        fill_premium = 0.0
        fill_contracts = 0
        fill_max_loss = 0.0

        for c in fills:
            if remaining <= 0 or contracts_left <= 0 or len(fill_trades) >= trades_left:
                break
            tk = c["ticker"]
            tused = used_tickers.get(tk, 0)
            if tused >= max_per_ticker:
                continue
            n_need = max(1, int(remaining / c["premium_per_contract"]) + 1)
            n = max(1, min(n_need, contracts_left, max_per_ticker - tused))
            tprem = round(n * c["premium_per_contract"], 2)
            tml = round(n * c["max_loss_per_contract"], 2)
            tmp = round(n * c["max_profit_per_contract"], 2)
            tier = self._TIER_OF.get(c["strategy"], "moderate")
            fill_trades.append({
                "ticker": c["ticker"], "current_price": c["current_price"],
                "strategy": c["strategy"], "strategy_display": c["strategy_display"],
                "action": c["action"], "expiry": c["expiry"], "dte": c["dte"],
                "contracts": n, "premium_per_contract": c["premium_per_contract"],
                "total_premium": tprem,
                "max_profit_per_contract": c["max_profit_per_contract"],
                "max_loss_per_contract": c["max_loss_per_contract"],
                "total_max_profit": tmp, "total_max_loss": tml,
                "rr_ratio": c["rr_ratio"], "pop": c["pop"],
                "daily_move_pct": c.get("daily_move_pct"),
                "events_before_expiry": [
                    e.get("event", "") for e in c.get("events_before_expiry", [])
                    if e.get("days_away", 999) <= c["dte"] + 1
                ],
                "score": c["score"], "risk_tier": tier, "part": "fill",
                "remark": f"⚑ Target filler — POP {c['pop']:.0f}% (below {OPTIONS_MIN_POP:.0f}% bar)",
            })
            remaining -= tprem
            contracts_left -= n
            fill_premium += tprem
            fill_contracts += n
            fill_max_loss += tml
            used_tickers[tk] = tused + n
            used_keys.add(c["key"])

        combined_premium = round(core_premium + fill_premium, 2)
        return {
            "trades": core_list + fill_trades,
            "core_trades": core_list,
            "covered_call_trades": covered_trades,
            "fill_trades": fill_trades,
            "core_premium": round(core_premium, 2),
            "fill_premium": round(fill_premium, 2),
            "total_premium": combined_premium,
            "core_contracts": core_contracts,
            "fill_contracts": fill_contracts,
            "total_contracts": core_contracts + fill_contracts,
            "target": target,
            "core_pct_of_target": round(core_premium / target * 100, 1) if target > 0 else 0,
            "pct_of_target": round(combined_premium / target * 100, 1) if target > 0 else 0,
            "max_contracts": max_contracts,
            "total_max_loss": round(core_max_loss + fill_max_loss, 2),
            "tier_breakdown": core.get("tier_breakdown", {}),
            "fill_min_pop": fill_min_pop,
        }

    @staticmethod
    def _portfolio_remark(cand: dict, tier: str = "") -> str:
        """Generate a concise remark for a portfolio trade."""
        parts = []

        # Risk tier badge
        tier_labels = {
            "aggressive": "⚡ Aggressive",
            "moderate": "⚖️ Moderate",
            "conservative": "🛡️ Conservative",
        }
        if tier:
            parts.append(tier_labels.get(tier, tier.title()))

        rr = cand["rr_ratio"]
        if rr >= 0.5:
            parts.append("Strong R/R")
        elif rr >= 0.3:
            parts.append("Good R/R")
        elif rr >= 0.15:
            parts.append("Fair R/R")

        iv_prem = cand.get("iv_premium")
        if iv_prem is not None:
            if iv_prem > 0.15:
                parts.append("IV very elevated")
            elif iv_prem > 0.05:
                parts.append("IV elevated")

        score = cand.get("score", 0)
        if score >= 60:
            parts.append("High conviction")
        elif score >= 45:
            parts.append("Good setup")

        strategy = cand["strategy"]
        if strategy == "IRON_CONDOR":
            parts.append("Range-bound play")
        elif strategy == "IRON_BUTTERFLY":
            parts.append("Max theta")
        elif strategy == "JADE_LIZARD":
            parts.append("Low upside risk")
        elif strategy == "CREDIT_PUT_SPREAD":
            parts.append("Defined risk · Bullish")
        elif strategy == "BEAR_CALL_SPREAD":
            parts.append("Defined risk · Bearish")
        elif strategy == "CASH_SECURED_PUT":
            parts.append("Defined risk · Bullish")

        return " · ".join(parts) if parts else "Standard premium sell"

    def get_vix_context(self) -> dict:
        """Current VIX level and volatility regime context."""
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1y", auto_adjust=True)
            if hist.empty:
                return {}

            current = round(float(hist["Close"].iloc[-1]), 2)
            sma20 = round(float(hist["Close"].rolling(20).mean().iloc[-1]), 2)
            high_52w = round(float(hist["Close"].max()), 2)
            low_52w = round(float(hist["Close"].min()), 2)
            pctile = round(
                float((hist["Close"] < current).sum() / len(hist) * 100), 0
            )

            if current > 30:
                regime, desc = "HIGH_VOL", (
                    "High volatility — rich premiums but higher assignment "
                    "risk. Prefer defined-risk spreads over naked puts."
                )
            elif current > 20:
                regime, desc = "ELEVATED", (
                    "Elevated volatility — good premium selling environment. "
                    "Cash-secured puts and credit spreads attractive."
                )
            elif current > 15:
                regime, desc = "NORMAL", (
                    "Normal volatility — standard premium available. "
                    "Focus on stocks with individual IV spikes."
                )
            else:
                regime, desc = "LOW_VOL", (
                    "Low volatility — limited premium across the board. "
                    "Be very selective; wait for better setups."
                )

            return {
                "vix": current,
                "vix_sma_20": sma20,
                "vix_52w_high": high_52w,
                "vix_52w_low": low_52w,
                "vix_percentile": pctile,
                "regime": regime,
                "regime_desc": desc,
            }
        except Exception as e:
            logger.error(f"Error fetching VIX: {e}")
            return {}

    # ------------------------------------------------------------------ #
    # Per-ticker analysis
    # ------------------------------------------------------------------ #

    def _analyze_single(
        self, ticker: str, price_df: Optional[pd.DataFrame],
        holding: dict = None,
    ) -> Optional[dict]:
        """Full options analysis for one ticker."""
        stock = yf.Ticker(ticker)

        # 1. Get expiry dates
        try:
            expiry_dates = stock.options
        except Exception:
            return None
        if not expiry_dates:
            return None

        # 2. Select weekly / near / mid / far expiries
        today = datetime.now().date()
        weekly_exp = near_exp = mid_exp = far_exp = None
        for exp_str in expiry_dates:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if OPTIONS_DTE_WEEKLY[0] <= dte <= OPTIONS_DTE_WEEKLY[1] and not weekly_exp:
                weekly_exp = exp_str
            if OPTIONS_DTE_NEAR[0] <= dte <= OPTIONS_DTE_NEAR[1] and not near_exp:
                near_exp = exp_str
            elif OPTIONS_DTE_MID[0] < dte <= OPTIONS_DTE_MID[1] and not mid_exp:
                mid_exp = exp_str
            elif OPTIONS_DTE_FAR[0] < dte <= OPTIONS_DTE_FAR[1] and not far_exp:
                far_exp = exp_str

        # Need at least one expiry to analyze
        primary_exp = mid_exp or near_exp
        if not primary_exp:
            return None

        # 3. Fetch option chains (deduplicate by expiry date)
        chains = {}
        fetched_expiries: dict[str, dict] = {}
        for label, exp in [
            ("weekly", weekly_exp), ("near", near_exp),
            ("mid", mid_exp), ("far", far_exp),
        ]:
            if not exp:
                continue
            if exp in fetched_expiries:
                chains[label] = fetched_expiries[exp]
                continue
            try:
                chain = stock.option_chain(exp)
                if not chain.calls.empty and not chain.puts.empty:
                    chain_data = {
                        "expiry": exp,
                        "dte": (datetime.strptime(exp, "%Y-%m-%d").date() - today).days,
                        "calls": chain.calls,
                        "puts": chain.puts,
                    }
                    chains[label] = chain_data
                    fetched_expiries[exp] = chain_data
            except Exception:
                pass

        if not chains:
            return None

        # 4. Current price — use the last VALID close. Yahoo frequently returns
        # a trailing NaN bar for the most recent day (esp. weekends / just after
        # close); .iloc[-1] would grab that NaN and abort the whole analysis.
        current_price = None
        if price_df is not None and not price_df.empty:
            col = "Close" if "Close" in price_df.columns else "close"
            if col in price_df.columns:
                valid_close = price_df[col].dropna()
                if not valid_close.empty:
                    current_price = float(valid_close.iloc[-1])
        if current_price is None or pd.isna(current_price):
            try:
                info = stock.info
                current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            except Exception:
                pass
        if not current_price or current_price <= 0:
            return None

        # 5. Realized volatility from price history
        hv_20 = self._realized_vol(price_df, HV_WINDOW_STANDARD)
        hv_10 = self._realized_vol(price_df, HV_WINDOW_SHORT)
        hv_60 = self._realized_vol(price_df, HV_WINDOW_LONG)

        # 5b. Price range (high/low variation) for 1W, 2W, 1M
        price_ranges = self._price_ranges(price_df, current_price)

        # 5c. Average True Range (daily movement)
        atr_14 = self._compute_atr(price_df, 14)

        # 6. ATM IV from primary chain
        primary = chains.get("mid") or chains.get("near")
        atm = self._get_atm_iv(primary["calls"], primary["puts"], current_price)
        atm_iv = atm.get("atm_iv")
        if atm_iv is None:
            return None

        # Near / far IV for term structure
        near_iv = None
        far_iv = None
        if "near" in chains:
            n = self._get_atm_iv(chains["near"]["calls"], chains["near"]["puts"], current_price)
            near_iv = n.get("atm_iv")
        if "far" in chains:
            f = self._get_atm_iv(chains["far"]["calls"], chains["far"]["puts"], current_price)
            far_iv = f.get("atm_iv")

        # 7. Compute metrics
        iv_premium = (atm_iv - hv_20) if hv_20 else None
        iv_hv_ratio = (atm_iv / hv_20) if hv_20 and hv_20 > 0 else None

        # Term structure: positive = contango (normal), negative = backwardation (fear)
        term_structure = None
        if near_iv and atm_iv and near_iv != atm_iv:
            term_structure = atm_iv - near_iv  # mid − near
        elif far_iv and atm_iv:
            term_structure = far_iv - atm_iv  # far − mid

        # IV Percentile & IV Rank (approximated via HV distribution)
        iv_percentile = None
        iv_rank = None
        if price_df is not None and len(price_df) > 60:
            col = "Close" if "Close" in price_df.columns else "close"
            log_ret = np.log(price_df[col] / price_df[col].shift(1)).dropna()
            hv_series = log_ret.rolling(window=HV_WINDOW_STANDARD).std() * np.sqrt(252)
            hv_vals = hv_series.tail(252).dropna()
            if len(hv_vals) > 20:
                iv_percentile = float((hv_vals < atm_iv).sum() / len(hv_vals) * 100)
                hv_hi = float(hv_vals.max())
                hv_lo = float(hv_vals.min())
                if hv_hi > hv_lo:
                    iv_rank = float((atm_iv - hv_lo) / (hv_hi - hv_lo) * 100)

        # 8. Open interest analysis
        oi = self._analyze_oi(primary["calls"], primary["puts"], current_price)

        # Implied move
        implied_move = self._implied_move(
            atm.get("call_mid"), atm.get("put_mid"), current_price,
        )

        # 8b. Upcoming events
        upcoming_events = self._upcoming_events(stock, ticker, price_df, current_price)

        # 9. Score
        metrics = {
            "iv_premium": iv_premium,
            "iv_percentile": iv_percentile,
            "iv_rank": iv_rank,
            "total_call_oi": oi.get("total_call_oi", 0),
            "total_put_oi": oi.get("total_put_oi", 0),
            "term_structure": term_structure,
            "bid_ask_spread_pct": atm.get("bid_ask_spread_pct"),
        }
        score, insights = self._score(metrics)

        # 10. Strategy suggestion (ALWAYS generated for every stock)
        strategy_suggestion = self._strategy_suggestion(
            ticker, current_price, atm_iv, hv_20, iv_premium,
            iv_percentile, iv_rank, term_structure,
            upcoming_events, price_df,
        )

        # 10b. IV LEVEL SCREEN — per spec, only consider names whose ATM IV
        # LEVEL clears the bar (absolute annualized IV, e.g. > 60%). Below the
        # bar the premium simply is not rich enough; we still return the row
        # for context/logging but generate NO tradeable recommendations.
        iv_level_pass = atm_iv is not None and atm_iv >= OPTIONS_MIN_IV_LEVEL

        # 11. Trade recommendations (event-aware, movement-aware)
        trades = []
        if iv_level_pass and score >= OPTIONS_MIN_PREMIUM_SCORE:
            trades = self._recommend_trades(
                ticker, current_price, score, iv_percentile or 50, chains,
                upcoming_events, atm_iv=atm_iv, atr=atr_14,
                price_ranges=price_ranges,
            )

        # 12. Weekly trades for portfolio (advanced strategies, DTE ≤ 9)
        weekly_trades = []
        wk_chain = chains.get("weekly")
        if iv_level_pass and wk_chain:
            weekly_trades = self._generate_weekly_trades(
                ticker, current_price, score, iv_percentile or 50,
                atm_iv, hv_20 or 0, wk_chain, upcoming_events,
                atr=atr_14, price_ranges=price_ranges,
            )

        # 12b. Covered call on shares already held (income overlay). Generated
        # regardless of the IV-level screen — it is income on stock you own —
        # but still subject to liquidity, no-earnings, POP and confirmation
        # downstream. Prioritized in the portfolio as the "easy money" play.
        if holding and int(holding.get("shares", 0)) >= 100:
            cc_chain = chains.get("mid") or chains.get("near")
            if cc_chain and cc_chain.get("calls") is not None:
                cc = self._covered_call_trade(
                    ticker, current_price, cc_chain["expiry"], cc_chain["dte"],
                    cc_chain["calls"], int(holding["shares"]),
                    cost_basis=holding.get("cost_price"),
                )
                if cc:
                    # Do not write calls through a binary earnings event.
                    e_days = next(
                        (ev["days_away"] for ev in upcoming_events
                         if ev.get("event") == "Earnings Report"), None,
                    )
                    if not (e_days is not None and e_days <= cc["dte"]):
                        trades.append(cc)

        # 13. Compute Probability of Profit (POP) for all trades
        trade_iv = atm_iv if atm_iv and atm_iv > 0 else 0.30  # fallback
        for trade in trades + weekly_trades:
            if trade.get("strategy") == "EVENT_WARNING":
                continue
            dte_val = trade.get("dte", 30)
            strategy = trade.get("strategy", "")
            be_low = trade.get("breakeven_low") or trade.get("breakeven")
            be_high = trade.get("breakeven_high")

            pop = None
            if strategy == "COVERED_CALL":
                # Keep premium + shares when price stays below the strike.
                k = trade.get("strike")
                if k and k > 0:
                    pop = self._estimate_pop(
                        current_price, 0.01, k, trade_iv, dte_val,
                    )
            elif strategy == "BEAR_CALL_SPREAD":
                # Profit when price < breakeven_high (single-sided upper)
                if be_high and be_high > 0:
                    pop = self._estimate_pop(
                        current_price, 0.01, be_high, trade_iv, dte_val,
                    )
            elif be_high is not None and be_low and be_low > 0:
                # Two-sided: profit when breakeven_low < price < breakeven_high
                pop = self._estimate_pop(
                    current_price, be_low, be_high, trade_iv, dte_val,
                )
            elif be_low and be_low > 0:
                # Single-sided: profit when price > breakeven_low (CSP, put spread, jade lizard no upside risk)
                pop = self._estimate_pop(
                    current_price, be_low, None, trade_iv, dte_val,
                )

            trade["pop"] = round(pop * 100, 1) if pop is not None else None

        # Get company name + sector (for segment/sector event context)
        name = ticker
        sector = None
        industry = None
        try:
            info = stock.info
            name = info.get("shortName") or info.get("longName") or ticker
            sector = info.get("sector")
            industry = info.get("industry")
        except Exception:
            pass

        from research_agents.macro_calendar import sector_catalyst_note
        sector_note = sector_catalyst_note(sector, industry)

        # Trader-sentiment signals (cheap — from data already in hand). News
        # tone is added later, only for the recommended shortlist.
        from research_agents import sentiment as _sent
        options_positioning = _sent.options_positioning(
            primary["calls"], primary["puts"], current_price,
        )
        hold = _sent.hold_quality(price_df)

        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "industry": industry,
            "sector_note": sector_note,
            "current_price": round(current_price, 2),
            "premium_score": score,
            # Trader sentiment
            "options_positioning": options_positioning,
            "hold_quality": hold,
            "news_sentiment": None,   # filled in for recommended names only
            "trader_bias": options_positioning.get("label", "Neutral"),
            # Volatility
            "iv_level_pass": iv_level_pass,
            "atm_iv": round(atm_iv, 4),
            "hv_20": round(hv_20, 4) if hv_20 else None,
            "hv_10": round(hv_10, 4) if hv_10 else None,
            # Volatility
            "iv_level_pass": iv_level_pass,
            "atm_iv": round(atm_iv, 4),
            "hv_20": round(hv_20, 4) if hv_20 else None,
            "hv_10": round(hv_10, 4) if hv_10 else None,
            "iv_premium": round(iv_premium, 4) if iv_premium is not None else None,
            "iv_hv_ratio": round(iv_hv_ratio, 2) if iv_hv_ratio is not None else None,
            "iv_percentile": round(iv_percentile, 1) if iv_percentile is not None else None,
            "iv_rank": round(iv_rank, 1) if iv_rank is not None else None,
            "term_structure": round(term_structure, 4) if term_structure is not None else None,
            "near_iv": round(near_iv, 4) if near_iv else None,
            # Open interest
            "total_call_oi": oi.get("total_call_oi", 0),
            "total_put_oi": oi.get("total_put_oi", 0),
            "pc_oi_ratio": oi.get("pc_oi_ratio"),
            "max_pain_strike": oi.get("max_pain_strike"),
            "implied_move_pct": implied_move,
            # Price ranges (high/low variation)
            "price_ranges": price_ranges,
            # Movement data
            "atr_14": atr_14,
            "daily_move_pct": round(atr_14 / current_price * 100, 2) if atr_14 else None,
            # Strategy & trades
            "strategy_suggestion": strategy_suggestion,
            "trades": trades,
            "weekly_trades": weekly_trades,
            "insights": insights,
            "upcoming_events": upcoming_events,
            "expiry_used": primary["expiry"],
            "dte": primary["dte"],
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _realized_vol(
        price_df: Optional[pd.DataFrame], window: int,
    ) -> Optional[float]:
        """Annualized realized volatility."""
        if price_df is None or len(price_df) < window + 5:
            return None
        col = "Close" if "Close" in price_df.columns else "close"
        if col not in price_df.columns:
            return None
        log_ret = np.log(price_df[col] / price_df[col].shift(1)).dropna()
        if len(log_ret) < window:
            return None
        return float(log_ret.tail(window).std() * np.sqrt(252))

    @staticmethod
    def _price_ranges(
        price_df: Optional[pd.DataFrame], current_price: float,
    ) -> dict:
        """Compute price range (high-low) over 1W, 2W, and 1M windows.

        Returns dict with keys like:
            range_1w: {high, low, spread, spread_pct}
            range_2w: ...
            range_1m: ...
        """
        result: dict = {}
        if price_df is None or price_df.empty:
            return result

        hi_col = "High" if "High" in price_df.columns else "high"
        lo_col = "Low" if "Low" in price_df.columns else "low"
        if hi_col not in price_df.columns or lo_col not in price_df.columns:
            return result

        windows = [("1w", 5), ("2w", 10), ("1m", 21)]
        for label, days in windows:
            if len(price_df) < days:
                continue
            window_df = price_df.tail(days)
            high = float(window_df[hi_col].max())
            low = float(window_df[lo_col].min())
            spread = high - low
            spread_pct = (spread / current_price * 100) if current_price > 0 else 0
            result[f"range_{label}"] = {
                "high": round(high, 2),
                "low": round(low, 2),
                "spread": round(spread, 2),
                "spread_pct": round(spread_pct, 1),
            }
        return result

    @staticmethod
    def _compute_atr(
        price_df: Optional[pd.DataFrame], window: int = 14,
    ) -> Optional[float]:
        """Compute Average True Range (ATR) — average daily move in dollars."""
        if price_df is None or len(price_df) < window + 2:
            return None
        hi = "High" if "High" in price_df.columns else "high"
        lo = "Low" if "Low" in price_df.columns else "low"
        cl = "Close" if "Close" in price_df.columns else "close"
        if not all(c in price_df.columns for c in [hi, lo, cl]):
            return None

        df = price_df.tail(window + 1).copy()
        prev_close = df[cl].shift(1)
        tr = pd.concat([
            df[hi] - df[lo],
            (df[hi] - prev_close).abs(),
            (df[lo] - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.dropna().tail(window).mean())
        return round(atr, 2)

    @staticmethod
    def _expected_move(
        price: float,
        atm_iv: float,
        dte: int,
        atr: Optional[float] = None,
        upcoming_events: list[dict] = None,
    ) -> dict:
        """Compute expected move for a given DTE window.

        Blends IV-implied move with realized ATR and adjusts for
        known catalysts (earnings gap, FOMC, ex-div).

        Returns:
            dict with keys:
              daily_move:    avg daily move in dollars (ATR)
              daily_move_pct: avg daily move as %
              period_move:   expected move for the DTE window in dollars
              period_move_pct: expected move as %
              event_adjusted_move: period move after adding event gap risk
              event_adjusted_pct:  event adjusted as %
              events_in_window: list of event names within DTE
              min_safe_otm_pct: minimum OTM% for strikes to be safe
        """
        if price <= 0 or dte <= 0:
            return {}

        # --- Daily move from ATR ---
        daily_atr = atr if atr and atr > 0 else price * atm_iv / np.sqrt(252)
        daily_pct = daily_atr / price * 100

        # --- IV-implied period move (1 std dev) ---
        iv_move = price * atm_iv * np.sqrt(dte / 365.0)
        iv_move_pct = iv_move / price * 100

        # --- ATR-projected period move ---
        atr_projected = daily_atr * np.sqrt(dte)  # scale by √time
        atr_projected_pct = atr_projected / price * 100

        # Blend: weight IV more (market's forward view) but anchor with ATR
        period_move = 0.6 * iv_move + 0.4 * atr_projected
        period_move_pct = period_move / price * 100

        # --- Event gap risk adjustment ---
        event_gap_pct = 0.0
        events_in_window = []
        for ev in (upcoming_events or []):
            days_away = ev.get("days_away", 999)
            if days_away > dte + 1:
                continue  # event is after expiry

            evt_name = ev.get("event", "")
            events_in_window.append(evt_name)

            if evt_name == "Earnings Report":
                # Add historical average earnings gap
                est_move = ev.get("est_move")
                if est_move and est_move > 0:
                    event_gap_pct += est_move  # e.g. +8% for earnings
                else:
                    event_gap_pct += 5.0  # conservative default
            elif evt_name == "FOMC Decision":
                event_gap_pct += 1.5  # typical FOMC reaction
            elif evt_name == "Ex-Dividend":
                est_move = ev.get("est_move")
                if est_move and est_move > 0:
                    event_gap_pct += est_move * 0.5  # ex-div usually mild

        event_gap_dollars = price * event_gap_pct / 100
        event_adjusted_move = period_move + event_gap_dollars
        event_adjusted_pct = event_adjusted_move / price * 100

        # --- Minimum safe OTM % ---
        # Place strikes at least 1.0× event-adjusted expected move away
        # This gives ~84% POP (1 std dev) as baseline
        min_safe_otm_pct = event_adjusted_pct / 100  # as decimal, e.g. 0.05

        return {
            "daily_move": round(daily_atr, 2),
            "daily_move_pct": round(daily_pct, 2),
            "period_move": round(period_move, 2),
            "period_move_pct": round(period_move_pct, 2),
            "event_adjusted_move": round(event_adjusted_move, 2),
            "event_adjusted_pct": round(event_adjusted_pct, 2),
            "event_gap_pct": round(event_gap_pct, 2),
            "events_in_window": events_in_window,
            "min_safe_otm_pct": round(min_safe_otm_pct, 4),
            "iv_move": round(iv_move, 2),
            "iv_move_pct": round(iv_move_pct, 2),
        }

    @staticmethod
    def _upcoming_events(
        stock: "yf.Ticker", ticker: str, price_df: Optional[pd.DataFrame],
        current_price: float,
    ) -> list[dict]:
        """Detect upcoming events that may impact stock price.

        Checks: earnings date, ex-dividend date.
        Estimates price impact using historical earnings moves and
        current IV / implied move.
        """
        events: list[dict] = []
        today = datetime.now().date()
        week_out = today + timedelta(days=7)

        try:
            cal = stock.calendar
        except Exception:
            cal = {}

        # ── Earnings date ───────────────────────────────────────────
        earn_date = None
        try:
            # yfinance .calendar may return dict or DataFrame
            if isinstance(cal, dict):
                raw = cal.get("Earnings Date") or cal.get("earningsDate")
            elif hasattr(cal, "loc"):
                raw = cal.loc["Earnings Date"] if "Earnings Date" in cal.index else None
            else:
                raw = None

            if raw is not None:
                if isinstance(raw, (list, pd.Series)):
                    for d in raw:
                        if isinstance(d, _date_type):
                            earn_date = d
                        elif hasattr(d, "date") and callable(d.date):
                            earn_date = d.date()
                        elif isinstance(d, str):
                            earn_date = datetime.strptime(d[:10], "%Y-%m-%d").date()
                        if earn_date:
                            break
                elif isinstance(raw, _date_type):
                    earn_date = raw
                elif hasattr(raw, "date") and callable(raw.date):
                    earn_date = raw.date()
                elif isinstance(raw, str):
                    earn_date = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except Exception:
            earn_date = None

        if earn_date and today <= earn_date <= today + timedelta(days=30):
            days_away = (earn_date - today).days
            # Estimate earnings move from recent earnings history
            avg_move = _avg_earnings_move(price_df)
            move_str = f"~{avg_move:.1f}%" if avg_move else "significant"
            impact = "HIGH" if (avg_move and avg_move >= 5) or days_away <= 3 else "MEDIUM"
            events.append({
                "event": "Earnings Report",
                "date": earn_date.strftime("%Y-%m-%d"),
                "days_away": days_away,
                "impact": impact,
                "est_move": avg_move,
                "note": (
                    f"Earnings in {days_away}d — avg post-earnings move {move_str}. "
                    f"{'IV likely elevated pre-earnings; expect crush after.' if days_away <= 7 else 'Watch for IV ramp-up.'}"
                ),
            })

        # ── Ex-Dividend date ────────────────────────────────────────
        ex_div = None
        try:
            if isinstance(cal, dict):
                raw_ex = cal.get("Ex-Dividend Date") or cal.get("exDividendDate")
            elif hasattr(cal, "loc"):
                raw_ex = cal.loc["Ex-Dividend Date"] if "Ex-Dividend Date" in cal.index else None
            else:
                raw_ex = None

            if raw_ex is not None:
                if isinstance(raw_ex, _date_type):
                    ex_div = raw_ex
                elif hasattr(raw_ex, "date") and callable(raw_ex.date):
                    ex_div = raw_ex.date()
                elif isinstance(raw_ex, str):
                    ex_div = datetime.strptime(raw_ex[:10], "%Y-%m-%d").date()
        except Exception:
            ex_div = None

        if ex_div and today <= ex_div <= today + timedelta(days=30):
            days_away = (ex_div - today).days
            # Dividend impact: fetch yield
            div_rate = None
            try:
                info = stock.info
                div_rate = info.get("dividendRate")
            except Exception:
                pass
            div_pct = (div_rate / current_price * 100) if div_rate and current_price > 0 else None
            events.append({
                "event": "Ex-Dividend",
                "date": ex_div.strftime("%Y-%m-%d"),
                "days_away": days_away,
                "impact": "LOW",
                "est_move": round(div_pct, 2) if div_pct else None,
                "note": (
                    f"Ex-dividend in {days_away}d"
                    + (f" — ~{div_pct:.2f}% drop expected at open" if div_pct else "")
                    + ". Put sellers: factor in assignment risk near ex-date."
                ),
            })

        # ── FOMC / macro (applies to indices only) ──────────────────
        # Hard-coded near-term FOMC dates for 2026
        fomc_dates = [
            datetime(2026, 3, 17).date(),
            datetime(2026, 3, 18).date(),
            datetime(2026, 5, 5).date(),
            datetime(2026, 5, 6).date(),
            datetime(2026, 6, 16).date(),
            datetime(2026, 6, 17).date(),
        ]
        if ticker in ("SPY", "QQQ", "IWM", "DIA"):
            for fdate in fomc_dates:
                if today <= fdate <= today + timedelta(days=14):
                    days_away = (fdate - today).days
                    events.append({
                        "event": "FOMC Decision",
                        "date": fdate.strftime("%Y-%m-%d"),
                        "days_away": days_away,
                        "impact": "HIGH",
                        "est_move": None,
                        "note": (
                            f"FOMC rate decision in {days_away}d — "
                            f"expect elevated index volatility. "
                            f"IV likely to crush post-announcement."
                        ),
                    })
                    break  # only show the nearest

        return events

    @staticmethod
    def _get_atm_iv(
        calls: pd.DataFrame, puts: pd.DataFrame, current_price: float,
    ) -> dict:
        """Extract ATM implied volatility and pricing from chains."""
        if calls.empty or puts.empty:
            return {}

        # Find strike closest to current price
        strike_col = "strike"
        atm_idx = (calls[strike_col] - current_price).abs().idxmin()
        atm_strike = float(calls.loc[atm_idx, strike_col])

        call_row = calls[calls[strike_col] == atm_strike]
        put_row = puts[puts[strike_col] == atm_strike]

        call_iv = put_iv = None
        call_bid = call_ask = put_bid = put_ask = None

        if not call_row.empty:
            r = call_row.iloc[0]
            call_iv = float(r["impliedVolatility"]) if r["impliedVolatility"] > 0 else None
            call_bid = float(r["bid"])
            call_ask = float(r["ask"])

        if not put_row.empty:
            r = put_row.iloc[0]
            put_iv = float(r["impliedVolatility"]) if r["impliedVolatility"] > 0 else None
            put_bid = float(r["bid"])
            put_ask = float(r["ask"])

        atm_iv = None
        if call_iv and put_iv:
            atm_iv = (call_iv + put_iv) / 2
        elif call_iv:
            atm_iv = call_iv
        elif put_iv:
            atm_iv = put_iv

        # Mid prices for implied move
        call_mid = ((call_bid or 0) + (call_ask or 0)) / 2 if call_bid and call_ask else None
        put_mid = ((put_bid or 0) + (put_ask or 0)) / 2 if put_bid and put_ask else None

        # Bid-ask spread quality (% of mid)
        spread_pct = None
        if call_bid and call_ask and call_mid and call_mid > 0:
            spread_pct = (call_ask - call_bid) / call_mid

        return {
            "atm_strike": atm_strike,
            "atm_iv": atm_iv,
            "call_iv": call_iv,
            "put_iv": put_iv,
            "call_bid": call_bid,
            "call_ask": call_ask,
            "put_bid": put_bid,
            "put_ask": put_ask,
            "call_mid": call_mid,
            "put_mid": put_mid,
            "bid_ask_spread_pct": spread_pct,
        }

    @staticmethod
    def _analyze_oi(
        calls: pd.DataFrame, puts: pd.DataFrame, current_price: float,
    ) -> dict:
        """Open interest totals, P/C ratio, max pain."""
        total_call = int(calls["openInterest"].fillna(0).sum())
        total_put = int(puts["openInterest"].fillna(0).sum())
        pc_ratio = round(total_put / total_call, 2) if total_call > 0 else None

        # Max pain: strike with highest combined OI
        all_strikes = sorted(
            set(calls["strike"].tolist() + puts["strike"].tolist())
        )
        max_pain_strike = None
        max_oi = 0
        for s in all_strikes:
            c_oi = int(calls.loc[calls["strike"] == s, "openInterest"].fillna(0).sum())
            p_oi = int(puts.loc[puts["strike"] == s, "openInterest"].fillna(0).sum())
            if c_oi + p_oi > max_oi:
                max_oi = c_oi + p_oi
                max_pain_strike = s

        return {
            "total_call_oi": total_call,
            "total_put_oi": total_put,
            "pc_oi_ratio": pc_ratio,
            "max_pain_strike": max_pain_strike,
        }

    @staticmethod
    def _implied_move(
        call_mid: Optional[float], put_mid: Optional[float], price: float,
    ) -> Optional[float]:
        """Expected % move by expiry from ATM straddle."""
        if call_mid is None or put_mid is None or price <= 0:
            return None
        return round((call_mid + put_mid) / price * 100, 2)

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #

    @staticmethod
    def _score(metrics: dict) -> tuple[int, list[str]]:
        """Score premium selling opportunity (0-100). Higher = better."""
        score = 0
        insights: list[str] = []

        # --- IV Premium (IV > HV): 0-30 pts ---
        iv_prem = metrics.get("iv_premium")
        if iv_prem is not None:
            if iv_prem > 0.20:
                score += 30
                insights.append(
                    f"IV {iv_prem*100:.0f}pp above realized vol — options "
                    f"significantly overpriced, strong premium selling setup"
                )
            elif iv_prem > 0.10:
                score += 22
                insights.append(
                    f"IV {iv_prem*100:.0f}pp above realized vol — options overpriced"
                )
            elif iv_prem > 0.05:
                score += 15
                insights.append(
                    f"IV {iv_prem*100:.0f}pp above realized vol — mild premium edge"
                )
            elif iv_prem > 0:
                score += 8
            elif iv_prem < -0.05:
                score -= 10
                insights.append(
                    "IV below realized vol — options underpriced, avoid selling"
                )

        # --- IV Percentile: 0-25 pts ---
        pctile = metrics.get("iv_percentile")
        if pctile is not None:
            if pctile > 80:
                score += 25
                insights.append(
                    f"IV Percentile {pctile:.0f}% — at the high end, "
                    f"likely to mean-revert lower (vol crush expected)"
                )
            elif pctile > 60:
                score += 18
                insights.append(
                    f"IV Percentile {pctile:.0f}% — above average, "
                    f"decent premium available"
                )
            elif pctile > 40:
                score += 10
            elif pctile < 20:
                score -= 5
                insights.append(
                    f"IV Percentile only {pctile:.0f}% — IV already low, "
                    f"limited premium to sell"
                )

        # --- Open Interest (liquidity): 0-15 pts ---
        total_oi = (
            (metrics.get("total_call_oi") or 0)
            + (metrics.get("total_put_oi") or 0)
        )
        if total_oi > 50000:
            score += 15
            insights.append(f"Excellent liquidity: {total_oi:,} total open interest")
        elif total_oi > 10000:
            score += 10
        elif total_oi > 2000:
            score += 5
        else:
            score -= 5
            insights.append("Low open interest — may have wide bid/ask spreads")

        # --- IV Rank: 0-15 pts ---
        iv_rank = metrics.get("iv_rank")
        if iv_rank is not None:
            if iv_rank > 70:
                score += 15
                insights.append(
                    f"IV Rank {iv_rank:.0f}% — IV elevated vs its 1-year range"
                )
            elif iv_rank > 50:
                score += 10
            elif iv_rank > 30:
                score += 5

        # --- Term structure: 0-10 pts ---
        ts = metrics.get("term_structure")
        if ts is not None:
            if ts < -0.05:
                score += 10
                insights.append(
                    "IV backwardation — near-term fear elevated, "
                    "sell near-dated premium for maximum crush"
                )
            elif ts < 0:
                score += 5

        # --- Bid-ask quality: 0-5 pts ---
        spread = metrics.get("bid_ask_spread_pct")
        if spread is not None:
            if spread < 0.03:
                score += 5
            elif spread < 0.05:
                score += 3

        return max(0, min(100, score)), insights

    # ------------------------------------------------------------------ #
    # Trade recommendations
    # ------------------------------------------------------------------ #

    @staticmethod
    def _strategy_suggestion(
        ticker: str,
        price: float,
        atm_iv: Optional[float],
        hv_20: Optional[float],
        iv_premium: Optional[float],
        iv_percentile: Optional[float],
        iv_rank: Optional[float],
        term_structure: Optional[float],
        upcoming_events: list[dict],
        price_df: Optional[pd.DataFrame],
    ) -> dict:
        """Always produce a strategy recommendation for every stock.

        Returns dict with:
            primary: str — headline strategy name
            secondary: str — alternative strategy
            direction: str — SELL_PREMIUM / BUY_PREMIUM / NEUTRAL
            strategies: list[dict] — each has name, description, risk_level
            rationale: str — 1-2 sentence explanation
            event_note: str — event-specific caveat (or empty)
        """
        # ── Detect trend from price data ─────────────────────────────
        trend = "NEUTRAL"
        if price_df is not None and len(price_df) >= 20:
            col = "Close" if "Close" in price_df.columns else "close"
            if col in price_df.columns:
                sma20 = float(price_df[col].tail(20).mean())
                sma5 = float(price_df[col].tail(5).mean())
                if sma5 > sma20 * 1.01:
                    trend = "BULLISH"
                elif sma5 < sma20 * 0.99:
                    trend = "BEARISH"

        # ── Detect upcoming earnings/FOMC ────────────────────────────
        earnings_near = False
        earnings_days = None
        fomc_near = False
        for ev in (upcoming_events or []):
            if ev["event"] == "Earnings Report" and ev["days_away"] <= 7:
                earnings_near = True
                earnings_days = ev["days_away"]
            if ev["event"] == "FOMC Decision" and ev["days_away"] <= 7:
                fomc_near = True

        iv_pctile = iv_percentile or 50
        iv_prem = (iv_premium or 0) * 100  # convert to percentage points

        strategies: list[dict] = []
        event_note = ""

        # ── SCENARIO 1: Earnings ≤ 3 days → defer all selling ───────
        if earnings_near and earnings_days is not None and earnings_days <= 3:
            event_note = (
                f"Earnings in {earnings_days}d — DO NOT sell premium now. "
                f"Wait for post-earnings IV crush, then enter."
            )
            strategies = [
                {
                    "name": "Post-Earnings Vertical Put Spread",
                    "description": (
                        "After earnings, sell a bull put credit spread to capture "
                        "IV crush. Pick strikes below the post-earnings price."
                    ),
                    "risk_level": "MODERATE",
                },
                {
                    "name": "Post-Earnings Cash-Secured Put",
                    "description": (
                        "After earnings, sell an OTM put to buy the dip at a "
                        "discount if the stock drops, or keep the premium."
                    ),
                    "risk_level": "MODERATE",
                },
                {
                    "name": "Pre-Earnings Straddle / Strangle (Buy)",
                    "description": (
                        "If you expect a large move but are unsure of direction, "
                        "BUY a straddle/strangle before earnings. Profits from "
                        "a gap exceeding implied move."
                    ),
                    "risk_level": "HIGH",
                },
            ]
            return {
                "primary": "Post-Earnings Vertical Put Spread",
                "secondary": "Post-Earnings Cash-Secured Put",
                "direction": "WAIT",
                "strategies": strategies,
                "rationale": (
                    f"Earnings imminent — IV is elevated FOR A REASON. "
                    f"Selling premium now risks a large gap move. "
                    f"Best to wait and sell into the post-earnings IV crush."
                ),
                "event_note": event_note,
            }

        # ── SCENARIO 2: Earnings 4-7 days → cautious selling ────────
        if earnings_near:
            event_note = (
                f"Earnings in {earnings_days}d — elevated gap risk. "
                f"Prefer defined-risk spreads over naked positions."
            )
            strategies = [
                {
                    "name": "Vertical Put Spread (Bull Put Credit)",
                    "description": (
                        "Sell an OTM put spread with wider strikes (8-10% OTM). "
                        "Defined risk caps your downside if earnings disappoint."
                    ),
                    "risk_level": "MODERATE",
                },
                {
                    "name": "Calendar Put Spread",
                    "description": (
                        "Sell near-expiry put (pre-earnings IV inflated), "
                        "buy longer-dated put. Profits from near-term IV crush "
                        "while maintaining protection."
                    ),
                    "risk_level": "MODERATE",
                },
            ]
            if iv_prem > 10:
                strategies.append({
                    "name": "Vertical Call Spread (Bear Call Credit)",
                    "description": (
                        "If bearish bias, sell an OTM call spread above resistance. "
                        "Benefits from IV crush even if stock rises modestly."
                    ),
                    "risk_level": "MODERATE",
                })
            return {
                "primary": "Vertical Put Spread (Bull Put Credit)",
                "secondary": "Calendar Put Spread",
                "direction": "SELL_PREMIUM",
                "strategies": strategies,
                "rationale": (
                    f"IV elevated pre-earnings — spreads capture premium while "
                    f"capping risk. Avoid iron condors (gap risk). "
                    f"Use wider OTM strikes than normal."
                ),
                "event_note": event_note,
            }

        # ── SCENARIO 3: FOMC near (indices) ─────────────────────────
        if fomc_near:
            event_note = "FOMC decision imminent — expect volatility spike then crush."
            strategies = [
                {
                    "name": "Vertical Put Spread (Bull Put Credit)",
                    "description": (
                        "Sell OTM put spread on index. After FOMC, IV typically "
                        "collapses regardless of outcome."
                    ),
                    "risk_level": "MODERATE",
                },
                {
                    "name": "Calendar Spread",
                    "description": (
                        "Sell pre-FOMC expiry, buy post-FOMC expiry. "
                        "Captures near-term IV premium decay."
                    ),
                    "risk_level": "MODERATE",
                },
            ]
            return {
                "primary": "Vertical Put Spread (Bull Put Credit)",
                "secondary": "Calendar Spread",
                "direction": "SELL_PREMIUM",
                "strategies": strategies,
                "rationale": (
                    "FOMC-driven IV typically collapses post-announcement. "
                    "Sell defined-risk spreads to profit from the crush."
                ),
                "event_note": event_note,
            }

        # ── SCENARIO 4: IV high, premium-rich → sell premium ────────
        if iv_prem > 5 and iv_pctile > 60:
            strategies = [
                {
                    "name": "Vertical Put Spread (Bull Put Credit)",
                    "description": (
                        "Sell OTM put / buy further OTM put. Defined risk, "
                        "profits if stock stays above short strike. "
                        "Best when IV is elevated and expected to decline."
                    ),
                    "risk_level": "MODERATE",
                },
                {
                    "name": "Cash-Secured Put",
                    "description": (
                        f"Sell ~5% OTM put to collect premium. If assigned, "
                        f"you buy {ticker} at a discount. "
                        f"Best for stocks you'd want to own."
                    ),
                    "risk_level": "MODERATE",
                },
            ]
            if iv_pctile > 75:
                strategies.append({
                    "name": "Iron Condor",
                    "description": (
                        "Sell OTM put spread + OTM call spread. "
                        "Profits if stock stays range-bound. Best when IV is "
                        "very high and expected to revert."
                    ),
                    "risk_level": "HIGH",
                })
            if trend == "BEARISH":
                strategies.append({
                    "name": "Vertical Call Spread (Bear Call Credit)",
                    "description": (
                        "Sell OTM call spread above resistance. "
                        "Profits from downward pressure + IV decline."
                    ),
                    "risk_level": "MODERATE",
                })
            secondary = "Iron Condor" if iv_pctile > 75 else "Cash-Secured Put"
            return {
                "primary": "Vertical Put Spread (Bull Put Credit)",
                "secondary": secondary,
                "direction": "SELL_PREMIUM",
                "strategies": strategies,
                "rationale": (
                    f"IV is {iv_prem:.0f}pp above realized vol — options overpriced. "
                    f"Sell premium via vertical spreads to capture the decay. "
                    f"{'Trend is bearish — consider bear call spreads too.' if trend == 'BEARISH' else ''}"
                ),
                "event_note": event_note,
            }

        # ── SCENARIO 5: IV low → buy premium / debit spreads ────────
        if iv_prem < -5 or iv_pctile < 30:
            strategies = [
                {
                    "name": "Vertical Call Spread (Bull Call Debit)",
                    "description": (
                        "Buy OTM call / sell further OTM call. Cheap entry when "
                        "IV is low. Profits from upside move."
                    ),
                    "risk_level": "MODERATE",
                },
                {
                    "name": "Vertical Put Spread (Bear Put Debit)",
                    "description": (
                        "Buy ATM put / sell further OTM put. "
                        "Profits from downside move at low IV cost."
                    ),
                    "risk_level": "MODERATE",
                },
                {
                    "name": "Long Straddle / Strangle",
                    "description": (
                        "Buy ATM call + put (straddle) or OTM call + put (strangle). "
                        "Profits from a large move in either direction. "
                        "Best when IV is historically low and due to expand."
                    ),
                    "risk_level": "HIGH",
                },
            ]
            primary = (
                "Vertical Call Spread (Bull Call Debit)"
                if trend != "BEARISH"
                else "Vertical Put Spread (Bear Put Debit)"
            )
            return {
                "primary": primary,
                "secondary": "Long Straddle / Strangle",
                "direction": "BUY_PREMIUM",
                "strategies": strategies,
                "rationale": (
                    f"IV is low ({iv_pctile:.0f}th percentile) — options are cheap. "
                    f"Premium selling yields little here. Instead, buy debit spreads "
                    f"or straddles to benefit from a potential IV expansion."
                ),
                "event_note": event_note,
            }

        # ── SCENARIO 6: Neutral IV → directional spreads ────────────
        strategies = [
            {
                "name": "Vertical Put Spread (Bull Put Credit)",
                "description": (
                    "Sell OTM put spread for credit. Moderate premium available. "
                    "Select strikes based on support levels."
                ),
                "risk_level": "MODERATE",
            },
            {
                "name": "Vertical Call Spread (Bull Call Debit)",
                "description": (
                    "Buy a call spread if bullish. "
                    "Lower cost than outright calls with defined risk."
                ),
                "risk_level": "MODERATE",
            },
            {
                "name": "Calendar Spread",
                "description": (
                    "Sell near-term, buy longer-term at same strike. "
                    "Profits from time decay differential."
                ),
                "risk_level": "LOW",
            },
        ]
        if trend == "BULLISH":
            primary = "Vertical Put Spread (Bull Put Credit)"
            secondary = "Vertical Call Spread (Bull Call Debit)"
        elif trend == "BEARISH":
            primary = "Vertical Call Spread (Bear Call Credit)"
            secondary = "Vertical Put Spread (Bear Put Debit)"
            strategies.insert(0, {
                "name": "Vertical Call Spread (Bear Call Credit)",
                "description": (
                    "Sell OTM call spread for credit. "
                    "Profits from continued downtrend and time decay."
                ),
                "risk_level": "MODERATE",
            })
        else:
            primary = "Calendar Spread"
            secondary = "Vertical Put Spread (Bull Put Credit)"

        return {
            "primary": primary,
            "secondary": secondary,
            "direction": "NEUTRAL",
            "strategies": strategies,
            "rationale": (
                f"IV is in normal range — no strong premium selling or buying edge. "
                f"Use directional spreads based on your bias "
                f"({'bullish' if trend == 'BULLISH' else 'bearish' if trend == 'BEARISH' else 'neutral'} "
                f"trend detected). Calendar spreads work well in range-bound markets."
            ),
            "event_note": event_note,
        }

    def _recommend_trades(
        self,
        ticker: str,
        price: float,
        score: int,
        iv_percentile: float,
        chains: dict,
        upcoming_events: list[dict] = None,
        atm_iv: float = 0.30,
        atr: Optional[float] = None,
        price_ranges: dict = None,
    ) -> list[dict]:
        """Generate specific trade ideas, adjusted for upcoming events
        and daily/weekly movement ranges.

        Movement-aware logic:
          - Compute expected move for the DTE window using IV + ATR
          - Add event gap risk (earnings, FOMC, ex-div)
          - Set OTM strikes OUTSIDE the event-adjusted expected move
          - Ensures strikes have room to absorb both normal movement
            AND event-driven gaps

        Event risk logic:
          - Earnings ≤3 days: SKIP all pre-expiry trades; suggest post-earnings
            entry on a later expiry.
          - Earnings 4-7 days: Block iron condors (gap risk), widen OTM buffer
            on puts/spreads, or shift to post-earnings expiry.
          - Earnings 8-14 days: Warn but allow, prefer defined-risk spreads.
          - FOMC ≤7 days (indices): Block condors, warn on spreads.
          - Ex-dividend ≤7 days: Warn about early assignment risk on puts.
        """
        trades = []
        upcoming_events = upcoming_events or []
        price_ranges = price_ranges or {}

        # ── Classify event risk ──────────────────────────────────────
        earnings_days = None      # days until nearest earnings
        fomc_days = None          # days until FOMC (indices only)
        exdiv_days = None         # days until ex-dividend
        earnings_move = None      # estimated earnings move %

        for ev in upcoming_events:
            if ev["event"] == "Earnings Report":
                earnings_days = ev["days_away"]
                earnings_move = ev.get("est_move")
            elif ev["event"] == "FOMC Decision":
                fomc_days = ev["days_away"]
            elif ev["event"] == "Ex-Dividend":
                exdiv_days = ev["days_away"]

        # ── Pick chains: prefer post-event expiry when event is near ─
        chain = chains.get("mid") or chains.get("near")
        if not chain:
            return trades

        expiry = chain["expiry"]
        dte = chain["dte"]
        puts = chain["puts"]
        calls = chain["calls"]

        # ── Compute expected move for this DTE window ─────────────
        exp_move = self._expected_move(
            price, atm_iv, dte, atr=atr,
            upcoming_events=upcoming_events,
        )
        min_safe_otm = exp_move.get("min_safe_otm_pct", 0.05) if exp_move else 0.05
        # Ensure floor of 3% and cap at 15%
        min_safe_otm = max(0.03, min(0.15, min_safe_otm))

        # If earnings ≤7d and we have a far-dated chain, use that
        # so the trade expires AFTER the event dust settles
        post_event_chain = None
        if earnings_days is not None and earnings_days <= 7:
            if "far" in chains:
                post_event_chain = chains["far"]
            elif "mid" in chains and chain is chains.get("near"):
                post_event_chain = chains["mid"]

        # ── EARNINGS ≤ 3 DAYS: Too risky pre-earnings ───────────────
        if earnings_days is not None and earnings_days <= 3:
            move_str = f"±{earnings_move:.0f}%" if earnings_move else "significant"
            warning = (
                f"⚠️ EARNINGS IN {earnings_days}d — stock could gap {move_str}. "
                f"Selling premium before earnings is HIGH RISK."
            )

            # Suggest post-earnings entry if we have a later expiry
            if post_event_chain:
                pe_expiry = post_event_chain["expiry"]
                pe_dte = post_event_chain["dte"]
                pe_puts = post_event_chain["puts"]
                pe_calls = post_event_chain["calls"]

                # Post-earnings CSP (wider OTM: 10% instead of 5%)
                if score >= 35:
                    trade = self._csp_trade(
                        ticker, price, pe_expiry, pe_dte, pe_puts,
                        otm_pct=0.10,
                    )
                    if trade:
                        trade["strategy_display"] = "Post-Earnings Cash-Secured Put"
                        trade["rationale"] = (
                            f"{warning} WAIT until after earnings, then sell the "
                            f"${trade['strike']:.0f} put ({trade['otm_pct']:.1f}% OTM) "
                            f"for ${trade['premium']:.2f}/share on the {pe_expiry} expiry. "
                            f"IV will likely crush post-report, locking in profit quickly. "
                            f"{pe_dte} DTE."
                        )
                        trades.append(trade)

                # Post-earnings spread (wider: 10%/15%)
                if score >= 30:
                    trade = self._put_spread_trade(
                        ticker, price, pe_expiry, pe_dte, pe_puts,
                        sell_otm=0.10, buy_otm=0.15,
                    )
                    if trade:
                        trade["strategy_display"] = "Post-Earnings Bull Put Spread"
                        trade["rationale"] = (
                            f"{warning} WAIT until after earnings, then sell "
                            f"${trade['strike']:.0f}/${trade['strike_long']:.0f} put spread "
                            f"for ${trade['premium']:.2f} credit on {pe_expiry}. "
                            f"Post-earnings IV crush boosts profitability. {pe_dte} DTE."
                        )
                        trades.append(trade)
            else:
                # No post-event chain — just add a warning-only "trade"
                trades.append({
                    "strategy": "EVENT_WARNING",
                    "strategy_display": "⚠️ Earnings Warning",
                    "action": f"WAIT — earnings on {upcoming_events[0]['date']}",
                    "strike": 0,
                    "expiry": expiry,
                    "dte": dte,
                    "premium": 0,
                    "max_profit": 0,
                    "max_loss": 0,
                    "breakeven": 0,
                    "rationale": (
                        f"{warning} Consider selling premium AFTER the report "
                        f"when IV crushes — the overpriced volatility will "
                        f"deflate rapidly post-announcement."
                    ),
                })

            return trades  # Don't add normal trades

        # ── EARNINGS 4-7 DAYS: Elevated risk ────────────────────────
        event_warning = ""
        widen_otm = False
        block_condor = False

        if earnings_days is not None and earnings_days <= 7:
            move_str = f"±{earnings_move:.0f}%" if earnings_move else "significant"
            event_warning = (
                f" ⚠️ Earnings in {earnings_days}d (est. {move_str} move) — "
                f"gap risk elevated."
            )
            widen_otm = True        # Push strikes further OTM
            block_condor = True     # Condors can't handle gaps

        elif fomc_days is not None and fomc_days <= 7:
            event_warning = (
                f" ⚠️ FOMC in {fomc_days}d — index volatility may spike."
            )
            block_condor = True

        exdiv_warning = ""
        if exdiv_days is not None and exdiv_days <= 7:
            exdiv_warning = (
                " Note: ex-dividend in ≤7d — early assignment risk on ITM puts."
            )

        # ── Strategy selection: movement-aware + event-adjusted ──────
        # Dynamic OTM: use expected move as baseline, widen for events
        # min_safe_otm already includes event gap risk from _expected_move()
        csp_otm = max(min_safe_otm, 0.08 if widen_otm else 0.05)
        spread_sell = max(min_safe_otm, 0.08 if widen_otm else 0.05)
        spread_buy = spread_sell + 0.05  # wing 5% wider than short strike

        # Add movement context to warnings
        if exp_move:
            daily_mv = exp_move.get("daily_move_pct", 0)
            period_mv = exp_move.get("event_adjusted_pct", 0)
            move_ctx = (
                f" Daily ATR: {daily_mv:.1f}%."
                f" Expected {dte}d move (event-adjusted): ±{period_mv:.1f}%."
                f" Strikes placed ≥{min_safe_otm*100:.1f}% OTM."
            )
            event_warning += move_ctx

        # --- Cash-Secured Put ---
        if score >= 35:
            trade = self._csp_trade(
                ticker, price, expiry, dte, puts, otm_pct=csp_otm,
            )
            if trade:
                trade["rationale"] += event_warning + exdiv_warning
                trades.append(trade)

        # --- Bull Put Spread (credit) ---
        if score >= 30:
            trade = self._put_spread_trade(
                ticker, price, expiry, dte, puts,
                sell_otm=spread_sell, buy_otm=spread_buy,
            )
            if trade:
                trade["rationale"] += event_warning + exdiv_warning
                trades.append(trade)

        # --- Iron Condor: BLOCKED if earnings/FOMC within 7 days ---
        if score >= 55 and iv_percentile > 65 and not block_condor:
            trade = self._condor_trade(ticker, price, expiry, dte, puts, calls)
            if trade:
                trade["rationale"] += exdiv_warning
                trades.append(trade)
        elif block_condor and score >= 55:
            # Explain why condor is blocked
            trades.append({
                "strategy": "EVENT_WARNING",
                "strategy_display": "Iron Condor — BLOCKED",
                "action": f"SKIP condor — event risk too high",
                "strike": 0,
                "expiry": expiry,
                "dte": dte,
                "premium": 0,
                "max_profit": 0,
                "max_loss": 0,
                "breakeven": 0,
                "rationale": (
                    f"Iron condor NOT recommended.{event_warning} "
                    f"A large gap move would blow through both wings. "
                    f"Prefer directional spreads or wait until after the event."
                ),
            })

        # ── EARNINGS 8-14 DAYS: Mild warning only ───────────────────
        if earnings_days is not None and 8 <= earnings_days <= 14:
            for trade in trades:
                if trade.get("strategy") != "EVENT_WARNING":
                    trade["rationale"] += (
                        f" Note: earnings in {earnings_days}d — "
                        f"consider closing before the report."
                    )

        return trades

    def _csp_trade(
        self, ticker: str, price: float, expiry: str, dte: int,
        puts: pd.DataFrame, otm_pct: float = 0.05,
    ) -> Optional[dict]:
        """Cash-secured put recommendation."""
        target = price * (1 - otm_pct)
        otm = puts[
            (puts["strike"] <= target)
            & (puts["strike"] >= price * (1 - otm_pct - 0.10))
            & (puts["openInterest"].fillna(0) >= OPTIONS_MIN_OPEN_INTEREST)
        ].sort_values("strike", ascending=False)

        if otm.empty:
            return None

        row = otm.iloc[0]
        strike = float(row["strike"])
        bid = float(row["bid"]) if row["bid"] > 0 else float(row["lastPrice"]) * 0.9
        if bid <= 0:
            return None
        oi = int(row["openInterest"]) if pd.notna(row["openInterest"]) else 0
        iv = float(row["impliedVolatility"])
        otm_pct = (price - strike) / price * 100

        return {
            "strategy": "CASH_SECURED_PUT",
            "strategy_display": "Cash-Secured Put",
            "action": f"Cash-Secured Put {expiry}: SELL ${strike:.0f}P",
            "strike": strike,
            "expiry": expiry,
            "dte": dte,
            "premium": round(bid, 2),
            "max_profit": round(bid * 100, 2),
            "max_loss": round((strike - bid) * 100, 2),
            "breakeven": round(strike - bid, 2),
            "otm_pct": round(otm_pct, 1),
            "open_interest": oi,
            "iv": round(iv * 100, 1),
            "rationale": (
                f"Sell the ${strike:.0f} put ({otm_pct:.1f}% OTM) for "
                f"${bid:.2f}/share. If assigned, buy {ticker} at "
                f"${strike - bid:.2f} effective cost ({otm_pct + bid/price*100:.1f}% "
                f"below current). {dte} DTE."
            ),
        }

    def _covered_call_trade(
        self, ticker: str, price: float, expiry: str, dte: int,
        calls: pd.DataFrame, shares: int,
        min_otm: float = 0.05, cost_basis: Optional[float] = None,
    ) -> Optional[dict]:
        """Covered-call write on shares already held.

        Sells an out-of-the-money call about `min_otm` above spot on stock the
        trader already owns. This is income on an existing position, so its
        real downside is the shares themselves, not new capital. `max_loss` is
        set to the premium as a framework nominal, and the trade is flagged
        `share_backed` so the portfolio does not treat it as defined risk.
        """
        if calls is None or calls.empty or shares < 100 or price <= 0:
            return None
        target = price * (1 + min_otm)
        otm = calls[
            (calls["strike"] >= target)
            & (calls["strike"] <= price * (1 + min_otm + 0.15))
            & (calls["openInterest"].fillna(0) >= OPTIONS_MIN_OPEN_INTEREST)
        ].sort_values("strike")
        if otm.empty:
            return None

        row = otm.iloc[0]
        strike = float(row["strike"])
        bid = float(row["bid"]) if row["bid"] > 0 else float(row["lastPrice"]) * 0.9
        if bid <= 0:
            return None
        oi = int(row["openInterest"]) if pd.notna(row["openInterest"]) else 0
        iv = float(row["impliedVolatility"])
        contracts_possible = int(shares // 100)
        otm_pct = (strike - price) / price * 100
        ref = cost_basis if (cost_basis and cost_basis > 0) else price
        if_called = (bid + max(0.0, strike - price)) * 100  # gain/contract if called
        static = bid * 100                                   # premium kept if not called

        return {
            "strategy": "COVERED_CALL",
            "strategy_display": "Covered Call",
            "action": (
                f"Covered Call {expiry}: SELL {contracts_possible}x "
                f"${strike:.0f}C on {contracts_possible * 100} sh"
            ),
            "strike": strike,
            "expiry": expiry,
            "dte": dte,
            "premium": round(bid, 2),
            "premium_per_contract": round(bid * 100, 2),
            "max_profit": round(if_called, 2),
            "max_loss": round(bid * 100, 2),   # nominal; true risk is the held shares
            "breakeven": round(price - bid, 2),
            "breakeven_low": round(price - bid, 2),
            "breakeven_high": None,
            "otm_pct": round(otm_pct, 1),
            "open_interest": oi,
            "iv": round(iv * 100, 1),
            "share_backed": True,
            "shares_held": int(shares),
            "contracts_possible": contracts_possible,
            "if_called_return_pct": round(if_called / (ref * 100) * 100, 2),
            "static_return_pct": round(static / (ref * 100) * 100, 2),
            "cost_basis": round(ref, 2),
            "rationale": (
                f"You hold {int(shares)} {ticker}. Sell {contracts_possible}x the "
                f"${strike:.0f} call ({otm_pct:.1f}% OTM) for ${bid:.2f}/share. Keep "
                f"the premium if {ticker} stays below ${strike:.0f}; if called away "
                f"you sell at ${strike:.0f} for a "
                f"{round(if_called / (ref * 100) * 100, 1)}% gain. {dte} DTE."
            ),
        }

    def _put_spread_trade(
        self, ticker: str, price: float, expiry: str, dte: int,
        puts: pd.DataFrame,
        sell_otm: float = 0.05, buy_otm: float = 0.10,
    ) -> Optional[dict]:
        """Bull put credit spread recommendation."""
        sell_target = price * (1 - sell_otm)
        buy_target = price * (1 - buy_otm)

        # Directional enforcement: sell put must be AT or BELOW target
        # to ensure it's beyond the expected downward move distance
        sell_puts = puts[
            (puts["strike"] <= sell_target)
            & (puts["strike"] >= sell_target - price * 0.05)
            & (puts["openInterest"].fillna(0) >= OPTIONS_MIN_OPEN_INTEREST)
        ].sort_values("strike", ascending=False)

        # Buy put must also be below its target (further OTM protection)
        buy_puts = puts[
            (puts["strike"] <= buy_target)
            & (puts["strike"] >= buy_target - price * 0.05)
        ].sort_values("strike", ascending=False)

        if sell_puts.empty or buy_puts.empty:
            return None

        sell_row = sell_puts.iloc[0]
        buy_row = buy_puts.iloc[0]
        sell_strike = float(sell_row["strike"])
        buy_strike = float(buy_row["strike"])

        if sell_strike <= buy_strike:
            return None

        sell_bid = float(sell_row["bid"]) if sell_row["bid"] > 0 else float(sell_row["lastPrice"]) * 0.9
        buy_ask = float(buy_row["ask"]) if buy_row["ask"] > 0 else float(buy_row["lastPrice"]) * 1.1
        net_credit = sell_bid - buy_ask

        if net_credit <= 0:
            return None

        width = sell_strike - buy_strike
        max_profit = net_credit * 100
        max_loss = (width - net_credit) * 100

        return {
            "strategy": "CREDIT_PUT_SPREAD",
            "strategy_display": "Bull Put Spread",
            "action": f"Bull Put Spread {expiry}: SELL ${sell_strike:.0f}P / BUY ${buy_strike:.0f}P",
            "strike": sell_strike,
            "strike_long": buy_strike,
            "expiry": expiry,
            "dte": dte,
            "premium": round(net_credit, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven": round(sell_strike - net_credit, 2),
            "spread_width": round(width, 2),
            "risk_reward": f"1:{max_loss/max_profit:.1f}" if max_profit > 0 else "N/A",
            "rationale": (
                f"Sell ${sell_strike:.0f}/${buy_strike:.0f} put spread for "
                f"${net_credit:.2f} credit. Max risk ${max_loss:.0f}/contract. "
                f"Profitable if {ticker} stays above ${sell_strike - net_credit:.2f} "
                f"by {expiry}. {dte} DTE."
            ),
        }

    def _condor_trade(
        self, ticker: str, price: float, expiry: str, dte: int,
        puts: pd.DataFrame, calls: pd.DataFrame,
        sell_otm_pct: float = 0.05, wing_width_pct: float = 0.05,
    ) -> Optional[dict]:
        """Iron condor recommendation (high IV, range-bound)."""
        sp_target = price * (1 - sell_otm_pct)
        bp_target = price * (1 - sell_otm_pct - wing_width_pct)
        sc_target = price * (1 + sell_otm_pct)
        bc_target = price * (1 + sell_otm_pct + wing_width_pct)

        # Directional enforcement: sell put BELOW target, sell call ABOVE target
        sell_put = self._closest_liquid_below(puts, sp_target, price)
        buy_put = self._closest_below(puts, bp_target, price)
        sell_call = self._closest_liquid_above(calls, sc_target, price)
        buy_call = self._closest_above(calls, bc_target, price)

        if any(x is None for x in [sell_put, buy_put, sell_call, buy_call]):
            return None

        sp_strike = float(sell_put["strike"])
        bp_strike = float(buy_put["strike"])
        sc_strike = float(sell_call["strike"])
        bc_strike = float(buy_call["strike"])

        if sp_strike <= bp_strike or bc_strike <= sc_strike:
            return None

        sp_bid = float(sell_put["bid"]) if sell_put["bid"] > 0 else 0
        bp_ask = float(buy_put["ask"]) if buy_put["ask"] > 0 else 0
        sc_bid = float(sell_call["bid"]) if sell_call["bid"] > 0 else 0
        bc_ask = float(buy_call["ask"]) if buy_call["ask"] > 0 else 0

        net_credit = (sp_bid - bp_ask) + (sc_bid - bc_ask)
        if net_credit <= 0:
            return None

        put_width = sp_strike - bp_strike
        call_width = bc_strike - sc_strike
        max_width = max(put_width, call_width)
        max_loss = (max_width - net_credit) * 100
        max_profit = net_credit * 100

        return {
            "strategy": "IRON_CONDOR",
            "strategy_display": "Iron Condor",
            "action": (
                f"Iron Condor {expiry}: "
                f"BUY ${bp_strike:.0f}P / SELL ${sp_strike:.0f}P · "
                f"SELL ${sc_strike:.0f}C / BUY ${bc_strike:.0f}C"
            ),
            "strike": sp_strike,
            "strike_long": bp_strike,
            "strike_call_sell": sc_strike,
            "strike_call_buy": bc_strike,
            "expiry": expiry,
            "dte": dte,
            "premium": round(net_credit, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven_low": round(sp_strike - net_credit, 2),
            "breakeven_high": round(sc_strike + net_credit, 2),
            "risk_reward": f"1:{max_loss/max_profit:.1f}" if max_profit > 0 else "N/A",
            "rationale": (
                f"Iron condor collecting ${net_credit:.2f} total credit. "
                f"Profitable if {ticker} stays between "
                f"${sp_strike - net_credit:.2f}–${sc_strike + net_credit:.2f} "
                f"by {expiry}. Max risk ${max_loss:.0f}/contract. {dte} DTE."
            ),
        }

    # ------------------------------------------------------------------ #
    # Advanced strategies for weekly portfolio
    # ------------------------------------------------------------------ #

    def _generate_weekly_trades(
        self,
        ticker: str,
        price: float,
        score: int,
        iv_percentile: float,
        atm_iv: float,
        hv_20: float,
        chain: dict,
        upcoming_events: list[dict],
        atr: Optional[float] = None,
        price_ranges: dict = None,
    ) -> list[dict]:
        """Generate expert-level weekly option trades (DTE ≤ 9).

        Movement-aware strike selection:
          - Computes expected move for the weekly DTE window
          - Adds event gap risk (earnings, FOMC, ex-div)
          - Sets OTM strikes OUTSIDE the expected move range
          - Uses recent weekly price range as floor for OTM distance

        Advanced strategies included:
          - Iron Condor (tight wings for weeklies)
          - Iron Butterfly (ATM, highest theta)
          - Bull Put Spread
          - Bear Call Spread
          - Jade Lizard (sell put + call spread, zero upside risk)
          - Cash-Secured Put

        Skips all trades if earnings fall within the expiry window.
        """
        trades: list[dict] = []
        expiry = chain["expiry"]
        dte = chain["dte"]
        puts = chain["puts"]
        calls = chain["calls"]
        price_ranges = price_ranges or {}

        # Skip if earnings during this expiry window
        for ev in (upcoming_events or []):
            if ev["event"] == "Earnings Report" and ev["days_away"] <= dte + 1:
                return []  # Don't sell premium into earnings

        # ── Compute movement-aware OTM targets ────────────────────
        # Expected move for this weekly window (includes event risk)
        exp_move = self._expected_move(
            price, atm_iv, dte, atr=atr,
            upcoming_events=upcoming_events,
        )
        em_otm = exp_move.get("min_safe_otm_pct", 0.03) if exp_move else 0.03

        # Also consider recent weekly price range as floor
        wk_range = price_ranges.get("range_1w", {})
        wk_range_pct = wk_range.get("spread_pct", 0) / 100 / 2
        # Use the larger of: expected move OR recent weekly range
        wk_otm = max(0.03, em_otm, wk_range_pct)
        wk_otm = min(wk_otm, 0.12)  # cap at 12% OTM

        # ── Wing widths: NARROW to achieve max_loss ≤ 2× max_profit
        # For ML ≤ 2×MP → width ≤ 3× credit. Keep wings tight.
        # Spread wing: use 2% of price (narrow) for better R/R
        spread_wing = 0.02
        # Condor short-strike OTM stays movement-aware, but wings narrow
        condor_wing = 0.025

        # 1. Iron Condor — tight wings for favorable R/R
        if score >= 40 and iv_percentile > 50:
            trade = self._condor_trade(
                ticker, price, expiry, dte, puts, calls,
                sell_otm_pct=wk_otm, wing_width_pct=condor_wing,
            )
            if trade:
                trades.append(trade)

        # 2. Iron Butterfly — ATM with tight wings for best R/R
        # Butterfly naturally has best R/R: credit is ATM straddle
        # Tight wings = higher credit relative to risk
        bf_wing = 0.04  # 4% wings — tight enough for favorable R/R
        if score >= 40 and iv_percentile > 55:
            trade = self._iron_butterfly_trade(
                ticker, price, expiry, dte, puts, calls,
                wing_width_pct=bf_wing,
            )
            if trade:
                trades.append(trade)

        # 3. Bull Put Spread — narrow wing for low max_loss
        if score >= 25:
            trade = self._put_spread_trade(
                ticker, price, expiry, dte, puts,
                sell_otm=wk_otm, buy_otm=wk_otm + spread_wing,
            )
            if trade:
                trades.append(trade)

        # 4. Bear Call Spread — narrow wing for low max_loss
        if score >= 25:
            trade = self._bear_call_spread_trade(
                ticker, price, expiry, dte, calls,
                sell_otm=wk_otm, buy_otm=wk_otm + spread_wing,
            )
            if trade:
                trades.append(trade)

        # 5. Jade Lizard — narrow call spread wing
        if score >= 35 and iv_percentile > 45:
            trade = self._jade_lizard_trade(
                ticker, price, expiry, dte, puts, calls,
                put_otm=wk_otm, call_sell_otm=wk_otm,
                call_buy_otm=wk_otm + spread_wing,
            )
            if trade:
                trades.append(trade)

        # 6. Cash-Secured Put — movement-adjusted OTM
        if score >= 30:
            trade = self._csp_trade(
                ticker, price, expiry, dte, puts, otm_pct=wk_otm,
            )
            if trade:
                trades.append(trade)

        # Append movement context to all trades
        if exp_move and trades:
            daily_mv = exp_move.get("daily_move_pct", 0)
            period_mv = exp_move.get("event_adjusted_pct", 0)
            events_in = exp_move.get("events_in_window", [])
            event_str = f" Events before expiry: {', '.join(events_in)}." if events_in else ""
            move_note = (
                f" [Movement: ATR ${exp_move.get('daily_move', 0):.1f}/day "
                f"({daily_mv:.1f}%), "
                f"expected {dte}d move ±{period_mv:.1f}%.{event_str} "
                f"Strikes set ≥{wk_otm*100:.1f}% OTM.]"
            )
            for t in trades:
                t["rationale"] += move_note
                t["expected_move_pct"] = round(period_mv, 2)
                t["daily_move_pct"] = round(daily_mv, 2)

        return trades

    def _iron_butterfly_trade(
        self, ticker: str, price: float, expiry: str, dte: int,
        puts: pd.DataFrame, calls: pd.DataFrame,
        wing_width_pct: float = 0.05,
    ) -> Optional[dict]:
        """Iron butterfly: sell ATM straddle, buy OTM wings.

        Highest premium of any spread strategy. Max profit when stock
        pins at ATM strike. Best for high IV + low expected move.
        """
        # ATM strike
        atm_idx = (calls["strike"] - price).abs().idxmin()
        atm_strike = float(calls.loc[atm_idx, "strike"])

        # Wing targets
        wing_width = price * wing_width_pct
        put_wing_target = atm_strike - wing_width
        call_wing_target = atm_strike + wing_width

        # ATM legs
        atm_call = calls[calls["strike"] == atm_strike]
        atm_put = puts[puts["strike"] == atm_strike]
        if atm_call.empty or atm_put.empty:
            return None

        # Wing legs — enforce put wing BELOW target, call wing ABOVE target
        buy_put = self._closest_below(puts, put_wing_target, price, max_range_pct=0.08)
        buy_call = self._closest_above(calls, call_wing_target, price, max_range_pct=0.08)
        if buy_put is None or buy_call is None:
            return None

        bp_strike = float(buy_put["strike"])
        bc_strike = float(buy_call["strike"])
        if bp_strike >= atm_strike or bc_strike <= atm_strike:
            return None

        # Premiums
        ac_bid = float(atm_call.iloc[0]["bid"]) if atm_call.iloc[0]["bid"] > 0 else 0
        ap_bid = float(atm_put.iloc[0]["bid"]) if atm_put.iloc[0]["bid"] > 0 else 0
        bp_ask = float(buy_put["ask"]) if buy_put["ask"] > 0 else 0
        bc_ask = float(buy_call["ask"]) if buy_call["ask"] > 0 else 0

        net_credit = ac_bid + ap_bid - bp_ask - bc_ask
        if net_credit <= 0:
            return None

        put_width = atm_strike - bp_strike
        call_width = bc_strike - atm_strike
        max_width = max(put_width, call_width)
        max_profit = net_credit * 100
        max_loss = (max_width - net_credit) * 100
        if max_loss <= 0:
            return None

        return {
            "strategy": "IRON_BUTTERFLY",
            "strategy_display": "Iron Butterfly",
            "action": (
                f"Iron Butterfly {expiry}: "
                f"BUY ${bp_strike:.0f}P / SELL ${atm_strike:.0f}P+C / "
                f"BUY ${bc_strike:.0f}C"
            ),
            "strike": atm_strike,
            "strike_long": bp_strike,
            "strike_call_buy": bc_strike,
            "expiry": expiry,
            "dte": dte,
            "premium": round(net_credit, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven_low": round(atm_strike - net_credit, 2),
            "breakeven_high": round(atm_strike + net_credit, 2),
            "risk_reward": (
                f"1:{max_loss / max_profit:.1f}" if max_profit > 0 else "N/A"
            ),
            "rationale": (
                f"Iron butterfly at ${atm_strike:.0f} collecting "
                f"${net_credit:.2f} credit. Max profit if {ticker} "
                f"pins at ${atm_strike:.0f} by {expiry}. Profitable "
                f"between ${atm_strike - net_credit:.2f}–"
                f"${atm_strike + net_credit:.2f}. "
                f"Max risk ${max_loss:.0f}/ct. {dte} DTE. "
                f"Highest theta — ideal for weekly decay."
            ),
        }

    def _bear_call_spread_trade(
        self, ticker: str, price: float, expiry: str, dte: int,
        calls: pd.DataFrame,
        sell_otm: float = 0.03, buy_otm: float = 0.07,
    ) -> Optional[dict]:
        """Bear call credit spread: sell OTM call, buy further OTM call.

        Bearish / neutral bias. Profits from IV crush + time decay
        as long as stock stays below short strike.
        """
        sell_target = price * (1 + sell_otm)
        buy_target = price * (1 + buy_otm)

        # Directional enforcement: sell call must be AT or ABOVE target
        # to ensure it's beyond the expected move distance
        sell_calls = calls[
            (calls["strike"] >= sell_target)
            & (calls["strike"] <= sell_target + price * 0.05)
            & (calls["openInterest"].fillna(0) >= OPTIONS_MIN_OPEN_INTEREST)
        ].sort_values("strike", ascending=True)

        # Buy call must also be above its target
        buy_calls = calls[
            (calls["strike"] >= buy_target)
            & (calls["strike"] <= buy_target + price * 0.05)
        ].sort_values("strike", ascending=True)

        if sell_calls.empty or buy_calls.empty:
            return None

        sell_row = sell_calls.iloc[0]
        buy_row = buy_calls.iloc[0]
        sell_strike = float(sell_row["strike"])
        buy_strike = float(buy_row["strike"])

        if buy_strike <= sell_strike:
            return None

        sell_bid = (
            float(sell_row["bid"])
            if sell_row["bid"] > 0
            else float(sell_row["lastPrice"]) * 0.9
        )
        buy_ask = (
            float(buy_row["ask"])
            if buy_row["ask"] > 0
            else float(buy_row["lastPrice"]) * 1.1
        )
        net_credit = sell_bid - buy_ask
        if net_credit <= 0:
            return None

        width = buy_strike - sell_strike
        max_profit = net_credit * 100
        max_loss = (width - net_credit) * 100

        return {
            "strategy": "BEAR_CALL_SPREAD",
            "strategy_display": "Bear Call Spread",
            "action": (
                f"Bear Call Spread {expiry}: "
                f"SELL ${sell_strike:.0f}C / BUY ${buy_strike:.0f}C"
            ),
            "strike": sell_strike,
            "strike_long": buy_strike,
            "expiry": expiry,
            "dte": dte,
            "premium": round(net_credit, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven": round(sell_strike + net_credit, 2),
            "breakeven_high": round(sell_strike + net_credit, 2),
            "spread_width": round(width, 2),
            "risk_reward": (
                f"1:{max_loss / max_profit:.1f}" if max_profit > 0 else "N/A"
            ),
            "rationale": (
                f"Sell ${sell_strike:.0f}/${buy_strike:.0f} call spread "
                f"for ${net_credit:.2f} credit. Profitable if {ticker} "
                f"stays below ${sell_strike + net_credit:.2f} by {expiry}. "
                f"Max risk ${max_loss:.0f}/ct. {dte} DTE. "
                f"Bearish/neutral play benefiting from time decay."
            ),
        }

    def _jade_lizard_trade(
        self, ticker: str, price: float, expiry: str, dte: int,
        puts: pd.DataFrame, calls: pd.DataFrame,
        put_otm: float = 0.03, call_sell_otm: float = 0.03,
        call_buy_otm: float = 0.07,
    ) -> Optional[dict]:
        """Jade Lizard: sell OTM put + sell OTM call spread.

        Advanced strategy combining naked put with a bear call spread.
        If total credit ≥ call spread width → ZERO upside risk.
        Only downside risk on the put side. Expert-level trade.
        """
        # Put leg — sell put BELOW target (further OTM downward)
        put_target = price * (1 - put_otm)
        sell_put = self._closest_liquid_below(puts, put_target, price)
        if sell_put is None:
            return None

        # Call spread legs — sell call ABOVE target (further OTM upward)
        cs_target = price * (1 + call_sell_otm)
        cb_target = price * (1 + call_buy_otm)
        sell_call = self._closest_liquid_above(calls, cs_target, price)
        buy_call = self._closest_above(calls, cb_target, price)
        if sell_call is None or buy_call is None:
            return None

        put_strike = float(sell_put["strike"])
        sc_strike = float(sell_call["strike"])
        bc_strike = float(buy_call["strike"])
        if bc_strike <= sc_strike or put_strike >= price:
            return None

        # Premiums
        put_bid = float(sell_put["bid"]) if sell_put["bid"] > 0 else 0
        sc_bid = float(sell_call["bid"]) if sell_call["bid"] > 0 else 0
        bc_ask = float(buy_call["ask"]) if buy_call["ask"] > 0 else 0

        call_spread_credit = sc_bid - bc_ask
        total_credit = put_bid + max(0, call_spread_credit)
        if total_credit <= 0.10:
            return None

        call_width = bc_strike - sc_strike
        no_upside_risk = total_credit >= call_width

        # Risk calculation:
        # Upside: max(0, call_width - credit)
        # Downside: put goes ITM — use spread-equivalent risk
        upside_risk = max(0, (call_width - total_credit)) * 100
        # For downside, use a risk equivalent to a similar-width spread
        downside_risk = (call_width * 100) if not no_upside_risk else (
            max(call_width, price * put_otm) * 100
        )
        max_profit = total_credit * 100
        max_loss = max(upside_risk, downside_risk)
        if max_loss <= 0:
            max_loss = call_width * 100

        upside_note = (
            "ZERO upside risk (credit ≥ call spread width). "
            if no_upside_risk
            else ""
        )

        return {
            "strategy": "JADE_LIZARD",
            "strategy_display": "Jade Lizard",
            "action": (
                f"Jade Lizard {expiry}: "
                f"SELL ${put_strike:.0f}P + "
                f"SELL ${sc_strike:.0f}C / BUY ${bc_strike:.0f}C"
            ),
            "strike": put_strike,
            "strike_call_sell": sc_strike,
            "strike_call_buy": bc_strike,
            "expiry": expiry,
            "dte": dte,
            "premium": round(total_credit, 2),
            "max_profit": round(max_profit, 2),
            "max_loss": round(max_loss, 2),
            "breakeven": round(put_strike - total_credit, 2),
            "breakeven_low": round(put_strike - total_credit, 2),
            "breakeven_high": round(sc_strike + total_credit, 2) if not no_upside_risk else None,
            "no_upside_risk": no_upside_risk,
            "risk_reward": (
                f"1:{max_loss / max_profit:.1f}" if max_profit > 0 else "N/A"
            ),
            "rationale": (
                f"Jade lizard: sell ${put_strike:.0f} put + "
                f"${sc_strike:.0f}/${bc_strike:.0f} call spread for "
                f"${total_credit:.2f} total credit. {upside_note}"
                f"Profitable if {ticker} stays above "
                f"${put_strike - total_credit:.2f} by {expiry}. "
                f"Max risk ${max_loss:.0f}/ct. {dte} DTE. "
                f"Advanced 3-leg premium collection strategy."
            ),
        }

    @staticmethod
    def _closest_liquid(df: pd.DataFrame, target: float, price: float):
        """Find closest liquid strike (min OI)."""
        liquid = df[df["openInterest"].fillna(0) >= OPTIONS_MIN_OPEN_INTEREST]
        if liquid.empty:
            liquid = df[df["openInterest"].fillna(0) > 0]
        if liquid.empty:
            return None
        idx = (liquid["strike"] - target).abs().idxmin()
        return liquid.loc[idx]

    @staticmethod
    def _closest(df: pd.DataFrame, target: float, price: float):
        """Find closest strike."""
        if df.empty:
            return None
        idx = (df["strike"] - target).abs().idxmin()
        return df.loc[idx]

    # ── Directional strike helpers ──────────────────────────────
    # These enforce that short strikes are placed BEYOND the
    # expected-move distance (not just closest to ATM).

    @staticmethod
    def _closest_liquid_above(
        df: pd.DataFrame, target: float, price: float,
        max_range_pct: float = 0.05,
    ):
        """Find closest liquid strike AT or ABOVE target.

        Used for sell-call legs: ensures short call is beyond
        the expected upward move.
        """
        liquid = df[df["openInterest"].fillna(0) >= OPTIONS_MIN_OPEN_INTEREST]
        if liquid.empty:
            liquid = df[df["openInterest"].fillna(0) > 0]
        if liquid.empty:
            return None
        above = liquid[
            (liquid["strike"] >= target)
            & (liquid["strike"] <= target + price * max_range_pct)
        ]
        if above.empty:
            return None
        idx = (above["strike"] - target).abs().idxmin()
        return above.loc[idx]

    @staticmethod
    def _closest_liquid_below(
        df: pd.DataFrame, target: float, price: float,
        max_range_pct: float = 0.05,
    ):
        """Find closest liquid strike AT or BELOW target.

        Used for sell-put legs: ensures short put is beyond
        the expected downward move.
        """
        liquid = df[df["openInterest"].fillna(0) >= OPTIONS_MIN_OPEN_INTEREST]
        if liquid.empty:
            liquid = df[df["openInterest"].fillna(0) > 0]
        if liquid.empty:
            return None
        below = liquid[
            (liquid["strike"] <= target)
            & (liquid["strike"] >= target - price * max_range_pct)
        ]
        if below.empty:
            return None
        idx = (below["strike"] - target).abs().idxmin()
        return below.loc[idx]

    @staticmethod
    def _closest_above(
        df: pd.DataFrame, target: float, price: float,
        max_range_pct: float = 0.05,
    ):
        """Find closest strike AT or ABOVE target (any OI)."""
        if df.empty:
            return None
        above = df[
            (df["strike"] >= target)
            & (df["strike"] <= target + price * max_range_pct)
        ]
        if above.empty:
            return None
        idx = (above["strike"] - target).abs().idxmin()
        return above.loc[idx]

    @staticmethod
    def _closest_below(
        df: pd.DataFrame, target: float, price: float,
        max_range_pct: float = 0.05,
    ):
        """Find closest strike AT or BELOW target (any OI)."""
        if df.empty:
            return None
        below = df[
            (df["strike"] <= target)
            & (df["strike"] >= target - price * max_range_pct)
        ]
        if below.empty:
            return None
        idx = (below["strike"] - target).abs().idxmin()
        return below.loc[idx]

    @staticmethod
    def _estimate_pop(
        price: float,
        breakeven_low: float,
        breakeven_high: float | None,
        iv: float,
        dte: int,
    ) -> float:
        """Estimate Probability of Profit using log-normal model.

        Uses the Black-Scholes assumption that stock returns are
        normally distributed in log-space.

        Args:
            price: current stock price
            breakeven_low: lower breakeven price (or only breakeven for single-sided)
            breakeven_high: upper breakeven (None for single-sided spreads)
            iv: annualized implied volatility as decimal (e.g. 0.30 for 30%)
            dte: days to expiry

        Returns:
            Probability of profit as a float between 0 and 1.
        """
        from scipy.stats import norm  # type: ignore

        if iv <= 0 or dte <= 0 or price <= 0:
            return 0.5  # fallback

        # Annualized vol → DTE vol
        sigma = iv * np.sqrt(dte / 365.0)

        if breakeven_high is None:
            # Single-sided: profit when price > breakeven_low (e.g. CSP, put spread)
            d = np.log(breakeven_low / price) / sigma
            return float(1 - norm.cdf(d))  # P(price > breakeven_low)
        else:
            # Two-sided: profit when breakeven_low < price < breakeven_high
            d_low = np.log(breakeven_low / price) / sigma
            d_high = np.log(breakeven_high / price) / sigma
            return float(norm.cdf(d_high) - norm.cdf(d_low))

"""
dip_hunter.py — "Buy the Dip" Agent for Blue-Chip Stocks.

Identifies top-100 US stocks (NASDAQ-100 caliber) that have dropped
due to MACRO/EXTERNAL events (Trump tariffs, geopolitical tensions,
Fed fears, broad selloffs) rather than fundamental deterioration.

Logic:
  1. Focus on the ~100 largest, most fundamentally solid US stocks
  2. Detect recent price drops (1-week, 1-month, from 52W high)
  3. Verify fundamentals are still STRONG (high revenue growth, margins, ROE)
  4. Check if the drop is MACRO-DRIVEN (correlates with market/sector drop)
     vs COMPANY-SPECIFIC (earnings miss, scandal, etc.)
  5. Score: bigger drop + stronger fundamentals + macro-driven = best buy

The thesis: when AMZN, GOOGL, NVDA etc. drop 10-20% because of a Trump
tariff tweet or Middle East tensions, the business hasn't changed — it's
a gift to buy world-class companies at a discount.

DISCLAIMER: Research signals only — not financial advice.
"""

import logging
from typing import Optional

import numpy as np

from research_agents.watchlist import NASDAQ_100_PLUS

logger = logging.getLogger(__name__)

# Use the centralized NASDAQ-100+ list as the blue-chip universe
TOP_100_BLUE_CHIPS = list(dict.fromkeys(NASDAQ_100_PLUS))


class DipHunter:
    """Finds blue-chip 'buy the dip' opportunities."""

    def find_dip_buys(
        self,
        technical_results: list[dict],
        fundamental_results: list[dict],
        market_summary: dict = None,
    ) -> list[dict]:
        """Identify blue-chip stocks that dropped on macro events,
        not fundamental deterioration.

        Returns a list of dip-buy opportunities sorted by score.
        """
        # Build lookups
        tech_lookup = {t["ticker"]: t for t in technical_results if t}
        fund_lookup = {f["ticker"]: f for f in fundamental_results if f}

        # Get broad market recent performance for correlation check
        spy_ret_1w = None
        spy_ret_1m = None
        spy_tech = tech_lookup.get("SPY") or {}
        spy_ret_1w = spy_tech.get("return_1w")
        spy_ret_1m = spy_tech.get("return_1m")

        dip_buys = []

        for ticker in TOP_100_BLUE_CHIPS:
            tech = tech_lookup.get(ticker)
            fund = fund_lookup.get(ticker)
            if not tech or not fund:
                continue

            # --- Step 1: Is there a meaningful dip? ---
            ret_1w = tech.get("return_1w", 0) or 0
            ret_1m = tech.get("return_1m", 0) or 0
            ret_3m = tech.get("return_3m", 0) or 0
            pct_from_high = tech.get("pct_from_52w_high", 0) or 0
            rsi = tech.get("rsi", 50) or 50

            # Need at least SOME drop to qualify
            has_dip = (
                ret_1w < -3          # Dropped 3%+ in a week
                or ret_1m < -5       # Dropped 5%+ in a month
                or pct_from_high < -10  # 10%+ off 52-week high
                or rsi < 35          # RSI deeply oversold
            )
            if not has_dip:
                continue

            # --- Step 2: Are fundamentals still STRONG? ---
            fund_score = fund.get("total_score", 0)
            fund_quality = fund.get("quality", "POOR")
            rev_growth = fund.get("revenue_growth")
            earn_growth = fund.get("earnings_growth")
            profit_margin = fund.get("profit_margin")
            roe = fund.get("roe")
            market_cap = fund.get("market_cap", 0)

            # Must be at least FAIR fundamentals (score >= 40)
            if fund_score < 35:
                continue

            # --- Step 3: Is the drop MACRO-driven or COMPANY-specific? ---
            macro_score = 0  # Higher = more likely macro-driven
            insights = []

            # If broad market also dropped, it's likely macro
            if spy_ret_1w is not None and spy_ret_1w < -1:
                if ret_1w < 0:  # Stock dropped along with market
                    macro_score += 20
                    insights.append(
                        f"Market-wide selloff: SPY {spy_ret_1w:+.1f}% this week — "
                        f"this stock's {ret_1w:+.1f}% drop likely macro-driven, not company-specific"
                    )

            if spy_ret_1m is not None and spy_ret_1m < -2:
                if ret_1m < 0:
                    macro_score += 15
                    insights.append(
                        f"Broader market correction: SPY {spy_ret_1m:+.1f}% this month"
                    )

            # If stock dropped MORE than the market, it might be overdone
            if spy_ret_1w is not None and ret_1w < spy_ret_1w - 2:
                macro_score += 10
                insights.append(
                    f"Dropped {abs(ret_1w - (spy_ret_1w or 0)):.1f}% more than SPY — "
                    f"potential overreaction"
                )

            # RSI oversold on a fundamentally strong stock = classic dip buy
            if rsi < 30 and fund_score >= 50:
                macro_score += 15
                insights.append(
                    f"RSI at {rsi:.0f} (deeply oversold) on a fundamentally "
                    f"{fund_quality} stock — classic buy-the-dip setup"
                )
            elif rsi < 40 and fund_score >= 50:
                macro_score += 8
                insights.append(
                    f"RSI at {rsi:.0f} (approaching oversold) with {fund_quality} fundamentals"
                )

            # Distance from 52W high
            if pct_from_high < -20 and fund_score >= 50:
                macro_score += 15
                insights.append(
                    f"Trading {abs(pct_from_high):.0f}% below 52-week high — "
                    f"significant discount on a quality business"
                )
            elif pct_from_high < -10 and fund_score >= 50:
                macro_score += 8
                insights.append(
                    f"Trading {abs(pct_from_high):.0f}% below 52-week high"
                )

            # --- Step 4: Fundamental strength reinforcement ---
            strength_reasons = []
            if rev_growth is not None and rev_growth > 0.10:
                macro_score += 10
                strength_reasons.append(f"revenue growing {rev_growth*100:.0f}%")
            if earn_growth is not None and earn_growth > 0.15:
                macro_score += 8
                strength_reasons.append(f"earnings growing {earn_growth*100:.0f}%")
            if profit_margin is not None and profit_margin > 0.20:
                macro_score += 5
                strength_reasons.append(f"{profit_margin*100:.0f}% profit margins")
            if roe is not None and roe > 0.20:
                macro_score += 5
                strength_reasons.append(f"{roe*100:.0f}% ROE")

            if strength_reasons:
                insights.append(
                    f"Business remains strong: {', '.join(strength_reasons)}"
                )

            # Analyst target upside
            target = fund.get("target_mean")
            current_price = tech.get("current_price")
            if target and current_price and current_price > 0:
                upside = ((target - current_price) / current_price) * 100
                if upside > 15:
                    macro_score += 10
                    insights.append(
                        f"Analyst consensus target ${target:.0f} implies "
                        f"{upside:.0f}% upside from current ${current_price:.2f}"
                    )

            # Long-term trend still intact?
            trend = tech.get("trend", "")
            if "UPTREND" in trend:
                macro_score += 5
                insights.append("Long-term uptrend still intact despite short-term pullback")
            elif "DOWNTREND" in trend:
                insights.append(
                    "Caution: now below 200-day SMA — wait for stabilization "
                    "or buy in tranches"
                )

            # What NOT to buy: if fundamentals are deteriorating, skip
            risk_factors = []
            if rev_growth is not None and rev_growth < 0:
                risk_factors.append(
                    f"Revenue declining {rev_growth*100:.0f}% — drop may be "
                    f"fundamental, not just macro"
                )
                macro_score -= 15
            if earn_growth is not None and earn_growth < -0.20:
                risk_factors.append(
                    f"Earnings dropping {earn_growth*100:.0f}% — "
                    f"verify this is temporary before buying"
                )
                macro_score -= 10

            # Only include if macro_score is meaningful
            if macro_score < 15:
                continue

            dip_buys.append({
                "ticker": ticker,
                "name": fund.get("name", ticker),
                "current_price": current_price,
                "dip_score": min(100, max(0, macro_score)),
                "return_1w": ret_1w,
                "return_1m": ret_1m,
                "return_3m": ret_3m,
                "pct_from_52w_high": pct_from_high,
                "rsi": rsi,
                "trend": trend,
                "fund_quality": fund_quality,
                "fund_score": fund_score,
                "revenue_growth": rev_growth,
                "earnings_growth": earn_growth,
                "profit_margin": profit_margin,
                "market_cap": market_cap,
                "analyst_target": target,
                "analyst_rating": fund.get("analyst_rating"),
                "insights": insights,
                "risk_factors": risk_factors,
                "tech_signal": tech.get("signal", "HOLD"),
                "tech_composite": tech.get("composite_score", 0),
            })

        # Sort by dip score descending
        dip_buys.sort(key=lambda x: x["dip_score"], reverse=True)
        return dip_buys

    def find_sell_signals(
        self,
        technical_results: list[dict],
        fundamental_results: list[dict],
    ) -> list[dict]:
        """Identify blue-chip stocks that are fundamentally deteriorating
        (not just a macro dip) — these are the ones to SELL or AVOID.

        Criteria: stock is dropping AND fundamentals are weakening.
        """
        tech_lookup = {t["ticker"]: t for t in technical_results if t}
        fund_lookup = {f["ticker"]: f for f in fundamental_results if f}

        sell_signals = []

        for ticker in TOP_100_BLUE_CHIPS:
            tech = tech_lookup.get(ticker)
            fund = fund_lookup.get(ticker)
            if not tech or not fund:
                continue

            ret_1m = tech.get("return_1m", 0) or 0
            ret_3m = tech.get("return_3m", 0) or 0
            pct_from_high = tech.get("pct_from_52w_high", 0) or 0
            rsi = tech.get("rsi", 50) or 50
            trend = tech.get("trend", "")

            rev_growth = fund.get("revenue_growth")
            earn_growth = fund.get("earnings_growth")
            fund_quality = fund.get("quality", "")
            fund_score = fund.get("total_score", 0)

            sell_score = 0
            insights = []
            has_fundamental_weakness = False  # MUST have at least one

            # Price dropping (technical context, but NOT enough alone)
            if ret_1m < -5:
                sell_score += 10
            if ret_3m < -15:
                sell_score += 10
            if pct_from_high < -20:
                sell_score += 10

            # Fundamentals MUST be weakening — this is what separates
            # a real sell from a macro dip on a strong business
            if rev_growth is not None and rev_growth < 0:
                sell_score += 20
                has_fundamental_weakness = True
                insights.append(
                    f"Revenue DECLINING {rev_growth*100:.0f}% — business is shrinking, "
                    f"not just a macro dip"
                )
            if earn_growth is not None and earn_growth < -0.15:
                sell_score += 15
                has_fundamental_weakness = True
                insights.append(
                    f"Earnings falling {earn_growth*100:.0f}% — profitability under pressure"
                )
            if fund_quality in ("POOR",):
                sell_score += 10
                has_fundamental_weakness = True
                insights.append(f"Fundamental quality rated POOR (score {fund_score}/100)")

            # Technical breakdown (adds context, but never sufficient alone)
            if "STRONG_DOWNTREND" in trend:
                sell_score += 10
                insights.append("In strong downtrend — below 200 SMA by 5%+")
            if rsi > 70 and ret_3m > 30:
                sell_score += 10
                insights.append(
                    f"Overbought (RSI {rsi:.0f}) after {ret_3m:+.0f}% run — "
                    f"profit-taking risk"
                )

            # REQUIRE fundamental weakness — price drop alone is a dip buy,
            # not a sell. A stock only goes on the sell list if the BUSINESS
            # is deteriorating, not just the stock price.
            if sell_score >= 25 and insights and has_fundamental_weakness:
                sell_signals.append({
                    "ticker": ticker,
                    "name": fund.get("name", ticker),
                    "current_price": tech.get("current_price"),
                    "sell_score": min(100, sell_score),
                    "return_1m": ret_1m,
                    "return_3m": ret_3m,
                    "pct_from_52w_high": pct_from_high,
                    "rsi": rsi,
                    "trend": trend,
                    "fund_quality": fund_quality,
                    "revenue_growth": rev_growth,
                    "earnings_growth": earn_growth,
                    "insights": insights,
                    "tech_signal": tech.get("signal", "HOLD"),
                })

        sell_signals.sort(key=lambda x: x["sell_score"], reverse=True)
        return sell_signals

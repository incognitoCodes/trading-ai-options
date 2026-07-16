"""
fundamental_screener.py — Fundamental Analysis & Screening Agent.

Scores stocks on fundamental quality metrics and ranks them.
Computes a composite fundamental score (0-100) based on:
  - Valuation (P/E, PEG, Price/Sales, Price/Book)
  - Growth (Revenue, Earnings)
  - Profitability (ROE, Margins)
  - Financial Health (Debt/Equity, Current Ratio, FCF)
  - Analyst Sentiment (Ratings, Price Targets)
"""

import logging
from typing import Optional

from research_agents.config import FUND_EXCELLENT, FUND_GOOD, FUND_FAIR

logger = logging.getLogger(__name__)


class FundamentalScreener:
    """Scores and ranks stocks based on fundamental metrics."""

    def score(self, fundamentals: dict) -> Optional[dict]:
        """Score a single stock on fundamental quality (0-100)."""
        if not fundamentals:
            return None

        ticker = fundamentals.get("ticker", "?")
        scores = {}

        # --- Valuation Score (0-25) ---
        val_score = 0
        pe = fundamentals.get("pe_forward") or fundamentals.get("pe_trailing")
        if pe is not None and pe > 0:
            if pe < 15:
                val_score += 8
            elif pe < 25:
                val_score += 6
            elif pe < 35:
                val_score += 4
            elif pe < 50:
                val_score += 2

        peg = fundamentals.get("peg_ratio")
        if peg is not None and peg > 0:
            if peg < 1.0:
                val_score += 7   # Undervalued relative to growth
            elif peg < 1.5:
                val_score += 5
            elif peg < 2.0:
                val_score += 3
            else:
                val_score += 1

        ps = fundamentals.get("price_to_sales")
        if ps is not None and ps > 0:
            if ps < 3:
                val_score += 5
            elif ps < 8:
                val_score += 3
            elif ps < 15:
                val_score += 1

        pb = fundamentals.get("price_to_book")
        if pb is not None and pb > 0:
            if pb < 3:
                val_score += 5
            elif pb < 6:
                val_score += 3
            elif pb < 10:
                val_score += 1

        scores["valuation"] = min(25, val_score)

        # --- Growth Score (0-25) ---
        growth_score = 0
        rev_growth = fundamentals.get("revenue_growth")
        if rev_growth is not None:
            if rev_growth > 0.30:
                growth_score += 12
            elif rev_growth > 0.15:
                growth_score += 9
            elif rev_growth > 0.05:
                growth_score += 6
            elif rev_growth > 0:
                growth_score += 3

        earn_growth = fundamentals.get("earnings_growth")
        if earn_growth is not None:
            if earn_growth > 0.30:
                growth_score += 13
            elif earn_growth > 0.15:
                growth_score += 10
            elif earn_growth > 0.05:
                growth_score += 7
            elif earn_growth > 0:
                growth_score += 4

        scores["growth"] = min(25, growth_score)

        # --- Profitability Score (0-25) ---
        prof_score = 0
        roe = fundamentals.get("roe")
        if roe is not None:
            if roe > 0.25:
                prof_score += 10
            elif roe > 0.15:
                prof_score += 7
            elif roe > 0.10:
                prof_score += 4
            elif roe > 0:
                prof_score += 2

        profit_margin = fundamentals.get("profit_margin")
        if profit_margin is not None:
            if profit_margin > 0.25:
                prof_score += 8
            elif profit_margin > 0.15:
                prof_score += 6
            elif profit_margin > 0.05:
                prof_score += 4
            elif profit_margin > 0:
                prof_score += 2

        op_margin = fundamentals.get("operating_margin")
        if op_margin is not None:
            if op_margin > 0.25:
                prof_score += 7
            elif op_margin > 0.15:
                prof_score += 5
            elif op_margin > 0.05:
                prof_score += 3
            elif op_margin > 0:
                prof_score += 1

        scores["profitability"] = min(25, prof_score)

        # --- Financial Health Score (0-15) ---
        health_score = 0
        de = fundamentals.get("debt_to_equity")
        if de is not None:
            if de < 30:
                health_score += 5
            elif de < 80:
                health_score += 3
            elif de < 150:
                health_score += 1

        cr = fundamentals.get("current_ratio")
        if cr is not None:
            if cr > 2.0:
                health_score += 5
            elif cr > 1.5:
                health_score += 4
            elif cr > 1.0:
                health_score += 2

        fcf = fundamentals.get("free_cash_flow")
        if fcf is not None and fcf > 0:
            health_score += 5

        scores["financial_health"] = min(15, health_score)

        # --- Analyst Sentiment (0-10) ---
        analyst_score = 0
        rating = fundamentals.get("analyst_rating")
        if rating:
            rating_map = {
                "strongBuy": 10, "strong_buy": 10,
                "buy": 8,
                "overweight": 7,
                "outperform": 7,
                "hold": 5,
                "neutral": 5,
                "underperform": 3,
                "underweight": 3,
                "sell": 1,
                "strongSell": 0, "strong_sell": 0,
            }
            analyst_score = rating_map.get(rating, 5)

        # Bonus for upside to analyst target
        price = fundamentals.get("current_price")
        target = fundamentals.get("target_mean")
        if price and target and price > 0:
            upside = ((target - price) / price) * 100
            if upside > 20:
                analyst_score = min(10, analyst_score + 2)
            elif upside < -10:
                analyst_score = max(0, analyst_score - 2)

        scores["analyst_sentiment"] = min(10, analyst_score)

        # --- Composite ---
        total = sum(scores.values())

        # Quality label
        if total >= FUND_EXCELLENT:
            quality = "EXCELLENT"
        elif total >= FUND_GOOD:
            quality = "GOOD"
        elif total >= FUND_FAIR:
            quality = "FAIR"
        else:
            quality = "POOR"

        return {
            "ticker": ticker,
            "name": fundamentals.get("name", ticker),
            "sector": fundamentals.get("sector", "N/A"),
            "market_cap": fundamentals.get("market_cap", 0),
            "current_price": fundamentals.get("current_price"),
            "scores": scores,
            "total_score": total,
            "quality": quality,
            "pe_trailing": fundamentals.get("pe_trailing"),
            "pe_forward": fundamentals.get("pe_forward"),
            "revenue_growth": fundamentals.get("revenue_growth"),
            "earnings_growth": fundamentals.get("earnings_growth"),
            "roe": fundamentals.get("roe"),
            "profit_margin": fundamentals.get("profit_margin"),
            "debt_to_equity": fundamentals.get("debt_to_equity"),
            "dividend_yield": fundamentals.get("dividend_yield"),
            "beta": fundamentals.get("beta"),
            "analyst_rating": fundamentals.get("analyst_rating"),
            "target_mean": fundamentals.get("target_mean"),
            "num_analysts": fundamentals.get("num_analysts"),
        }

    def rank_stocks(self, scored_list: list[dict]) -> list[dict]:
        """Sort scored stocks by total fundamental score descending."""
        valid = [s for s in scored_list if s is not None]
        return sorted(valid, key=lambda x: x["total_score"], reverse=True)

    def get_top_fundamentals(self, scored_list: list[dict], n: int = 10) -> list[dict]:
        """Return top N stocks by fundamental score."""
        ranked = self.rank_stocks(scored_list)
        return ranked[:n]

    @staticmethod
    def format_market_cap(mc: float) -> str:
        if mc >= 1e12:
            return f"${mc/1e12:.1f}T"
        if mc >= 1e9:
            return f"${mc/1e9:.1f}B"
        if mc >= 1e6:
            return f"${mc/1e6:.0f}M"
        return f"${mc:,.0f}"

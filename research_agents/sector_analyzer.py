"""
sector_analyzer.py — Sector Rotation & Performance Agent.

Analyzes sector ETF performance to identify:
  - Which sectors are leading / lagging
  - Sector rotation signals (money flow)
  - Relative strength across timeframes
  - Sector momentum trends
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from research_agents.config import API_DELAY_SECONDS
from research_agents.watchlist import SECTOR_ETFS

logger = logging.getLogger(__name__)

SECTOR_NAMES = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLV": "Healthcare",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}


class SectorAnalyzer:
    """Analyzes sector performance and rotation patterns."""

    def analyze_sectors(self) -> list[dict]:
        """Compute performance metrics for all sector ETFs."""
        results = []
        for etf in SECTOR_ETFS:
            try:
                data = yf.Ticker(etf).history(period="1y", auto_adjust=True)
                if data.empty:
                    continue

                close = data["Close"]
                volume = data["Volume"]
                sector_name = SECTOR_NAMES.get(etf, etf)

                # Performance across timeframes
                perf = {}
                if len(close) >= 5:
                    perf["1w"] = round(((close.iloc[-1] / close.iloc[-5]) - 1) * 100, 2)
                if len(close) >= 21:
                    perf["1m"] = round(((close.iloc[-1] / close.iloc[-21]) - 1) * 100, 2)
                if len(close) >= 63:
                    perf["3m"] = round(((close.iloc[-1] / close.iloc[-63]) - 1) * 100, 2)
                if len(close) >= 126:
                    perf["6m"] = round(((close.iloc[-1] / close.iloc[-126]) - 1) * 100, 2)
                if len(close) >= 252:
                    perf["1y"] = round(((close.iloc[-1] / close.iloc[-252]) - 1) * 100, 2)

                # Relative Strength (vs SPY)
                spy_data = yf.Ticker("SPY").history(period="3mo", auto_adjust=True)
                rs_ratio = None
                if not spy_data.empty and len(spy_data) >= 21 and len(close) >= 21:
                    sector_3m = (close.iloc[-1] / close.iloc[-min(63, len(close))]) - 1
                    spy_3m = (spy_data["Close"].iloc[-1] / spy_data["Close"].iloc[-min(63, len(spy_data))]) - 1
                    rs_ratio = round((sector_3m - spy_3m) * 100, 2)

                # Momentum: SMA 20 vs SMA 50
                sma20 = close.rolling(20).mean().iloc[-1]
                sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else np.nan
                momentum = "BULLISH" if sma20 > sma50 else "BEARISH" if not np.isnan(sma50) else "N/A"

                # Volume trend
                vol_avg_20 = volume.rolling(20).mean().iloc[-1]
                vol_current = volume.iloc[-1]
                vol_trend = "ABOVE_AVG" if vol_current > vol_avg_20 * 1.2 else "BELOW_AVG" if vol_current < vol_avg_20 * 0.8 else "NORMAL"

                results.append({
                    "etf": etf,
                    "sector": sector_name,
                    "price": round(close.iloc[-1], 2),
                    "performance": perf,
                    "relative_strength_vs_spy": rs_ratio,
                    "momentum": momentum,
                    "volume_trend": vol_trend,
                    "sma_20": round(sma20, 2),
                    "sma_50": round(sma50, 2) if not np.isnan(sma50) else None,
                })

            except Exception as e:
                logger.error(f"Error analyzing sector {etf}: {e}")

        return results

    def get_sector_rankings(self, timeframe: str = "1m") -> list[dict]:
        """Rank sectors by performance in a given timeframe."""
        sectors = self.analyze_sectors()
        ranked = sorted(
            sectors,
            key=lambda x: x["performance"].get(timeframe, 0),
            reverse=True,
        )
        for i, s in enumerate(ranked, 1):
            s["rank"] = i
        return ranked

    def get_rotation_signals(self) -> dict:
        """Identify sector rotation patterns.

        Compares short-term (1w) vs medium-term (1m) performance
        to detect money flow shifts.
        """
        sectors = self.analyze_sectors()
        rotating_in = []   # Short-term > medium-term = new money flowing in
        rotating_out = []  # Short-term < medium-term = money flowing out

        for s in sectors:
            perf = s["performance"]
            w1 = perf.get("1w", 0)
            m1 = perf.get("1m", 0)
            if w1 and m1:
                # Annualize weekly to compare
                weekly_ann = w1 * 4  # rough monthly equivalent
                if weekly_ann > m1 + 2:  # accelerating
                    rotating_in.append({
                        "sector": s["sector"],
                        "etf": s["etf"],
                        "1w_return": w1,
                        "1m_return": m1,
                        "acceleration": round(weekly_ann - m1, 2),
                    })
                elif weekly_ann < m1 - 2:  # decelerating
                    rotating_out.append({
                        "sector": s["sector"],
                        "etf": s["etf"],
                        "1w_return": w1,
                        "1m_return": m1,
                        "deceleration": round(m1 - weekly_ann, 2),
                    })

        return {
            "rotating_in": sorted(rotating_in, key=lambda x: x["acceleration"], reverse=True),
            "rotating_out": sorted(rotating_out, key=lambda x: x["deceleration"], reverse=True),
        }

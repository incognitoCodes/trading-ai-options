"""
data_collector.py — Market Data Collection Agent.

Fetches price history, volume, and fundamental data using yfinance.
Provides batch processing with rate limiting to avoid API throttling.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf
import pandas as pd

from research_agents.config import (
    PRICE_HISTORY_PERIOD,
    API_DELAY_SECONDS,
    BATCH_SIZE,
)

logger = logging.getLogger(__name__)


class DataCollector:
    """Collects market data for stocks and ETFs."""

    def __init__(self):
        self._cache = {}
        self._fundamentals_cache = {}

    def get_price_data(
        self, ticker: str, period: str = PRICE_HISTORY_PERIOD
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV price history for a single ticker."""
        cache_key = f"{ticker}_{period}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, auto_adjust=True)
            if df.empty:
                logger.debug(f"No price data for {ticker}")
                return None
            # Standardize column names
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            self._cache[cache_key] = df
            return df
        except Exception as e:
            logger.error(f"Error fetching price data for {ticker}: {e}")
            return None

    def get_fundamentals(self, ticker: str) -> Optional[dict]:
        """Fetch fundamental data (P/E, margins, growth, etc.) for a ticker."""
        if ticker in self._fundamentals_cache:
            return self._fundamentals_cache[ticker]

        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if not info or "symbol" not in info:
                logger.warning(f"No fundamental data for {ticker}")
                return None

            fundamentals = {
                "ticker": ticker,
                "name": info.get("shortName", ticker),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "market_cap": info.get("marketCap", 0),
                "pe_trailing": info.get("trailingPE"),
                "pe_forward": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "price_to_book": info.get("priceToBook"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "revenue": info.get("totalRevenue", 0),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "free_cash_flow": info.get("freeCashflow", 0),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "50d_avg": info.get("fiftyDayAverage"),
                "200d_avg": info.get("twoHundredDayAverage"),
                "avg_volume": info.get("averageVolume", 0),
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "target_mean": info.get("targetMeanPrice"),
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "analyst_rating": info.get("recommendationKey"),
                "num_analysts": info.get("numberOfAnalystOpinions", 0),
            }
            self._fundamentals_cache[ticker] = fundamentals
            return fundamentals
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ticker}: {e}")
            return None

    def get_batch_data(
        self, tickers: list[str], period: str = PRICE_HISTORY_PERIOD
    ) -> dict[str, Optional[pd.DataFrame]]:
        """Fetch price data for multiple tickers with rate limiting."""
        results = {}
        for i, ticker in enumerate(tickers):
            results[ticker] = self.get_price_data(ticker, period)
            if (i + 1) % BATCH_SIZE == 0:
                time.sleep(API_DELAY_SECONDS)
        return results

    def get_batch_fundamentals(self, tickers: list[str]) -> dict[str, Optional[dict]]:
        """Fetch fundamentals for multiple tickers with rate limiting."""
        results = {}
        for i, ticker in enumerate(tickers):
            results[ticker] = self.get_fundamentals(ticker)
            if (i + 1) % BATCH_SIZE == 0:
                time.sleep(API_DELAY_SECONDS)
        return results

    def get_market_summary(self) -> dict:
        """Get a snapshot of major market indices and indicators."""
        indices = {
            "^GSPC": "S&P 500",
            "^IXIC": "NASDAQ",
            "^DJI": "Dow Jones",
            "^RUT": "Russell 2000",
            "^VIX": "VIX (Fear Index)",
            "^TNX": "10-Year Treasury Yield",
            "GC=F": "Gold Futures",
            "CL=F": "Crude Oil (WTI)",
            "BTC-USD": "Bitcoin",
            "DX-Y.NYB": "US Dollar Index",
        }
        summary = {}
        for symbol, name in indices.items():
            try:
                data = yf.Ticker(symbol).history(period="5d", auto_adjust=True)
                if not data.empty:
                    current = data["Close"].iloc[-1]
                    prev = data["Close"].iloc[-2] if len(data) > 1 else current
                    change_pct = ((current - prev) / prev) * 100
                    summary[name] = {
                        "symbol": symbol,
                        "price": round(current, 2),
                        "change_pct": round(change_pct, 2),
                    }
            except Exception as e:
                logger.error(f"Error fetching {name}: {e}")
            time.sleep(API_DELAY_SECONDS)
        return summary

    def clear_cache(self):
        """Clear all cached data for fresh fetches."""
        self._cache.clear()
        self._fundamentals_cache.clear()

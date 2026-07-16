"""
technical_analyzer.py — Technical Analysis Agent.

Computes a comprehensive set of technical indicators and generates
composite buy/sell/hold signals for each ticker.

Indicators computed:
  - RSI (14-day)
  - MACD (12, 26, 9) with histogram
  - SMA 20 / 50 / 200 crossovers
  - EMA 9 / 21
  - Bollinger Bands (20, 2)
  - ATR (14-day)
  - Stochastic Oscillator (14-day)
  - Volume vs 20-day average
  - 52-week high/low proximity
  - Support and resistance levels
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from research_agents.config import (
    RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    BB_PERIOD, BB_STD,
    SMA_SHORT, SMA_MEDIUM, SMA_LONG,
    EMA_FAST, EMA_SLOW,
    ATR_PERIOD, STOCH_PERIOD, VOLUME_AVG_PERIOD,
    STRONG_BUY_THRESHOLD, BUY_THRESHOLD,
    HOLD_UPPER, HOLD_LOWER,
    SELL_THRESHOLD, STRONG_SELL_THRESHOLD,
)

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """Performs technical analysis on price data and generates signals."""

    def analyze(self, ticker: str, df: pd.DataFrame) -> Optional[dict]:
        """Run full technical analysis on a ticker's price data.

        Returns a dict with all indicators, signals, and composite score.
        """
        if df is None or len(df) < SMA_LONG:
            logger.warning(
                f"{ticker}: Not enough data for full analysis "
                f"(need {SMA_LONG} bars, got {len(df) if df is not None else 0})"
            )
            if df is None or len(df) < SMA_SHORT:
                return None
            # Proceed with partial analysis

        try:
            close = df["close"]
            high = df["high"]
            low = df["low"]
            volume = df["volume"]

            analysis = {"ticker": ticker}

            # --- Price info ---
            analysis["current_price"] = round(close.iloc[-1], 2)
            analysis["prev_close"] = round(close.iloc[-2], 2) if len(close) > 1 else analysis["current_price"]
            analysis["daily_change_pct"] = round(
                ((analysis["current_price"] - analysis["prev_close"]) / analysis["prev_close"]) * 100, 2
            )

            # --- RSI ---
            rsi = self._compute_rsi(close, RSI_PERIOD)
            analysis["rsi"] = round(rsi, 2) if not np.isnan(rsi) else None
            analysis["rsi_signal"] = self._rsi_signal(rsi)

            # --- MACD ---
            macd_line, signal_line, histogram = self._compute_macd(close)
            analysis["macd"] = round(macd_line, 4) if not np.isnan(macd_line) else None
            analysis["macd_signal_line"] = round(signal_line, 4) if not np.isnan(signal_line) else None
            analysis["macd_histogram"] = round(histogram, 4) if not np.isnan(histogram) else None
            analysis["macd_signal"] = self._macd_signal(macd_line, signal_line, histogram, close)

            # --- Moving Averages ---
            sma20 = close.rolling(SMA_SHORT).mean().iloc[-1]
            sma50 = close.rolling(SMA_MEDIUM).mean().iloc[-1] if len(close) >= SMA_MEDIUM else np.nan
            sma200 = close.rolling(SMA_LONG).mean().iloc[-1] if len(close) >= SMA_LONG else np.nan
            ema9 = close.ewm(span=EMA_FAST, adjust=False).mean().iloc[-1]
            ema21 = close.ewm(span=EMA_SLOW, adjust=False).mean().iloc[-1]

            analysis["sma_20"] = round(sma20, 2) if not np.isnan(sma20) else None
            analysis["sma_50"] = round(sma50, 2) if not np.isnan(sma50) else None
            analysis["sma_200"] = round(sma200, 2) if not np.isnan(sma200) else None
            analysis["ema_9"] = round(ema9, 2)
            analysis["ema_21"] = round(ema21, 2)
            analysis["ma_signal"] = self._ma_signal(close.iloc[-1], sma20, sma50, sma200, ema9, ema21)

            # --- Golden / Death Cross ---
            if len(close) >= SMA_LONG:
                sma50_series = close.rolling(SMA_MEDIUM).mean()
                sma200_series = close.rolling(SMA_LONG).mean()
                analysis["golden_cross"] = bool(
                    sma50_series.iloc[-1] > sma200_series.iloc[-1]
                    and sma50_series.iloc[-2] <= sma200_series.iloc[-2]
                ) if len(sma50_series.dropna()) > 1 else False
                analysis["death_cross"] = bool(
                    sma50_series.iloc[-1] < sma200_series.iloc[-1]
                    and sma50_series.iloc[-2] >= sma200_series.iloc[-2]
                ) if len(sma50_series.dropna()) > 1 else False
            else:
                analysis["golden_cross"] = False
                analysis["death_cross"] = False

            # --- Bollinger Bands ---
            bb_mid = close.rolling(BB_PERIOD).mean()
            bb_std = close.rolling(BB_PERIOD).std()
            bb_upper = bb_mid + BB_STD * bb_std
            bb_lower = bb_mid - BB_STD * bb_std
            analysis["bb_upper"] = round(bb_upper.iloc[-1], 2)
            analysis["bb_lower"] = round(bb_lower.iloc[-1], 2)
            analysis["bb_mid"] = round(bb_mid.iloc[-1], 2)
            bb_width = (bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_mid.iloc[-1]
            analysis["bb_width"] = round(bb_width, 4)
            analysis["bb_signal"] = self._bb_signal(close.iloc[-1], bb_upper.iloc[-1], bb_lower.iloc[-1], bb_mid.iloc[-1])

            # --- ATR (Average True Range) ---
            atr = self._compute_atr(high, low, close, ATR_PERIOD)
            analysis["atr"] = round(atr, 2)
            analysis["atr_pct"] = round((atr / close.iloc[-1]) * 100, 2)

            # --- Stochastic Oscillator ---
            stoch_k, stoch_d = self._compute_stochastic(high, low, close, STOCH_PERIOD)
            analysis["stoch_k"] = round(stoch_k, 2)
            analysis["stoch_d"] = round(stoch_d, 2)
            analysis["stoch_signal"] = self._stoch_signal(stoch_k, stoch_d)

            # --- Volume Analysis ---
            vol_avg = volume.rolling(VOLUME_AVG_PERIOD).mean().iloc[-1]
            vol_current = volume.iloc[-1]
            analysis["volume"] = int(vol_current)
            analysis["volume_avg"] = int(vol_avg)
            analysis["volume_ratio"] = round(vol_current / vol_avg, 2) if vol_avg > 0 else 0
            analysis["volume_signal"] = self._volume_signal(vol_current, vol_avg, close)

            # --- 52-Week High/Low ---
            if len(close) >= 252:
                high_52w = high.tail(252).max()
                low_52w = low.tail(252).min()
            else:
                high_52w = high.max()
                low_52w = low.min()
            analysis["high_52w"] = round(high_52w, 2)
            analysis["low_52w"] = round(low_52w, 2)
            analysis["pct_from_52w_high"] = round(
                ((close.iloc[-1] - high_52w) / high_52w) * 100, 2
            )
            analysis["pct_from_52w_low"] = round(
                ((close.iloc[-1] - low_52w) / low_52w) * 100, 2
            )

            # --- Trend (price vs 200 SMA) ---
            if not np.isnan(sma200):
                if close.iloc[-1] > sma200 * 1.05:
                    analysis["trend"] = "STRONG_UPTREND"
                elif close.iloc[-1] > sma200:
                    analysis["trend"] = "UPTREND"
                elif close.iloc[-1] < sma200 * 0.95:
                    analysis["trend"] = "STRONG_DOWNTREND"
                else:
                    analysis["trend"] = "DOWNTREND"
            else:
                analysis["trend"] = "UNKNOWN"

            # --- Performance ---
            if len(close) >= 5:
                analysis["return_1w"] = round(((close.iloc[-1] / close.iloc[-5]) - 1) * 100, 2)
            if len(close) >= 21:
                analysis["return_1m"] = round(((close.iloc[-1] / close.iloc[-21]) - 1) * 100, 2)
            if len(close) >= 63:
                analysis["return_3m"] = round(((close.iloc[-1] / close.iloc[-63]) - 1) * 100, 2)
            if len(close) >= 126:
                analysis["return_6m"] = round(((close.iloc[-1] / close.iloc[-126]) - 1) * 100, 2)
            if len(close) >= 252:
                analysis["return_1y"] = round(((close.iloc[-1] / close.iloc[-252]) - 1) * 100, 2)

            # --- Composite Score ---
            score = self._composite_score(analysis)
            analysis["composite_score"] = score
            analysis["signal"] = self._score_to_signal(score)

            # --- Key Insights (human-readable reasons for the signal) ---
            analysis["insights"] = self._generate_insights(analysis)

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}")
            return None

    # -----------------------------------------------------------------------
    # Indicator Computations
    # -----------------------------------------------------------------------

    @staticmethod
    def _compute_rsi(close: pd.Series, period: int) -> float:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi.iloc[-1]

    @staticmethod
    def _compute_macd(close: pd.Series) -> tuple[float, float, float]:
        ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
        ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]

    @staticmethod
    def _compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> float:
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    @staticmethod
    def _compute_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> tuple[float, float]:
        lowest_low = low.rolling(period).min()
        highest_high = high.rolling(period).max()
        stoch_k = ((close - lowest_low) / (highest_high - lowest_low)) * 100
        stoch_d = stoch_k.rolling(3).mean()
        return stoch_k.iloc[-1], stoch_d.iloc[-1]

    # -----------------------------------------------------------------------
    # Signal Generation (-2 to +2 for each indicator)
    # -----------------------------------------------------------------------

    @staticmethod
    def _rsi_signal(rsi: float) -> int:
        if np.isnan(rsi):
            return 0
        if rsi < 25:
            return 2   # Deeply oversold — strong buy signal
        if rsi < 30:
            return 1   # Oversold — buy signal
        if rsi > 80:
            return -2  # Deeply overbought — strong sell
        if rsi > 70:
            return -1  # Overbought — sell signal
        return 0

    @staticmethod
    def _macd_signal(macd: float, signal: float, histogram: float, close: pd.Series) -> int:
        if np.isnan(macd) or np.isnan(signal):
            return 0
        score = 0
        # MACD above signal line = bullish
        if macd > signal:
            score += 1
        else:
            score -= 1
        # Histogram increasing = momentum building
        if histogram > 0:
            score += 1
        elif histogram < 0:
            score -= 1
        return max(-2, min(2, score))

    @staticmethod
    def _ma_signal(price: float, sma20: float, sma50: float, sma200: float,
                   ema9: float, ema21: float) -> int:
        score = 0
        # Price above key MAs = bullish
        if not np.isnan(sma20) and price > sma20:
            score += 0.5
        elif not np.isnan(sma20):
            score -= 0.5
        if not np.isnan(sma50) and price > sma50:
            score += 0.5
        elif not np.isnan(sma50):
            score -= 0.5
        if not np.isnan(sma200) and price > sma200:
            score += 0.5
        elif not np.isnan(sma200):
            score -= 0.5
        # EMA crossover
        if ema9 > ema21:
            score += 0.5
        else:
            score -= 0.5
        return max(-2, min(2, int(round(score))))

    @staticmethod
    def _bb_signal(price: float, upper: float, lower: float, mid: float) -> int:
        if price <= lower:
            return 1   # At/below lower band — potential bounce
        if price >= upper:
            return -1  # At/above upper band — potential pullback
        return 0

    @staticmethod
    def _stoch_signal(k: float, d: float) -> int:
        if np.isnan(k) or np.isnan(d):
            return 0
        if k < 20 and d < 20:
            return 1   # Oversold
        if k > 80 and d > 80:
            return -1  # Overbought
        return 0

    @staticmethod
    def _volume_signal(current_vol: float, avg_vol: float, close: pd.Series) -> int:
        if avg_vol == 0:
            return 0
        ratio = current_vol / avg_vol
        price_up = close.iloc[-1] > close.iloc[-2] if len(close) > 1 else True
        if ratio > 1.5 and price_up:
            return 1   # High volume on up day — bullish
        if ratio > 1.5 and not price_up:
            return -1  # High volume on down day — bearish
        return 0

    # -----------------------------------------------------------------------
    # Composite Score
    # -----------------------------------------------------------------------

    @staticmethod
    def _composite_score(analysis: dict) -> int:
        """Combine all individual signals into a composite score.

        Range: -8 to +8
        """
        score = 0
        score += analysis.get("rsi_signal", 0)
        score += analysis.get("macd_signal", 0)
        score += analysis.get("ma_signal", 0)
        score += analysis.get("bb_signal", 0)
        score += analysis.get("stoch_signal", 0)
        score += analysis.get("volume_signal", 0)
        return score

    @staticmethod
    def _score_to_signal(score: int) -> str:
        if score >= STRONG_BUY_THRESHOLD:
            return "STRONG_BUY"
        if score >= BUY_THRESHOLD:
            return "BUY"
        if score <= STRONG_SELL_THRESHOLD:
            return "STRONG_SELL"
        if score <= SELL_THRESHOLD:
            return "SELL"
        return "HOLD"

    # -----------------------------------------------------------------------
    # Insight Generation — human-readable reasons for each signal
    # -----------------------------------------------------------------------

    @staticmethod
    def _generate_insights(a: dict) -> list[str]:
        """Generate plain-English insights explaining WHY the signal fired."""
        insights = []
        ticker = a.get("ticker", "")
        rsi = a.get("rsi")
        signal = a.get("signal", "HOLD")

        # --- RSI insight ---
        if rsi is not None:
            if rsi < 25:
                insights.append(f"RSI deeply oversold at {rsi} — historically a strong bounce zone")
            elif rsi < 30:
                insights.append(f"RSI oversold at {rsi} — selling pressure may be exhausted")
            elif rsi > 80:
                insights.append(f"RSI deeply overbought at {rsi} — high risk of pullback")
            elif rsi > 70:
                insights.append(f"RSI overbought at {rsi} — momentum may be overextended")
            elif 45 <= rsi <= 55:
                insights.append(f"RSI neutral at {rsi} — no strong momentum either way")

        # --- MACD insight ---
        macd_sig = a.get("macd_signal", 0)
        macd_h = a.get("macd_histogram")
        if macd_sig >= 2:
            insights.append("MACD bullish crossover with rising momentum histogram")
        elif macd_sig == 1:
            insights.append("MACD above signal line — positive momentum building")
        elif macd_sig <= -2:
            insights.append("MACD bearish crossover with falling momentum histogram")
        elif macd_sig == -1:
            insights.append("MACD below signal line — negative momentum")

        # --- Moving Average insight ---
        ma_sig = a.get("ma_signal", 0)
        trend = a.get("trend", "")
        price = a.get("current_price", 0)
        sma50 = a.get("sma_50")
        sma200 = a.get("sma_200")
        if a.get("golden_cross"):
            insights.append("GOLDEN CROSS just formed (50 SMA crossed above 200 SMA) — major bullish signal")
        elif a.get("death_cross"):
            insights.append("DEATH CROSS just formed (50 SMA crossed below 200 SMA) — major bearish signal")

        if trend == "STRONG_UPTREND":
            insights.append(f"Price ${price:.2f} trading well above 200 SMA — strong uptrend intact")
        elif trend == "STRONG_DOWNTREND":
            pct_below = a.get("pct_from_52w_high", 0)
            insights.append(f"Price ${price:.2f} trading well below 200 SMA — strong downtrend ({pct_below:.1f}% from 52W high)")

        if ma_sig >= 2:
            insights.append("Price above all major moving averages (20/50/200 SMA) with bullish EMA crossover")
        elif ma_sig <= -2:
            insights.append("Price below all major moving averages — bearish structure across timeframes")

        # --- Bollinger Bands insight ---
        bb_sig = a.get("bb_signal", 0)
        bb_width = a.get("bb_width", 0)
        if bb_sig == 1:
            insights.append(f"Price touching lower Bollinger Band — potential bounce / mean-reversion setup")
        elif bb_sig == -1:
            insights.append(f"Price touching upper Bollinger Band — may be overextended short-term")
        if bb_width and bb_width < 0.04:
            insights.append(f"Bollinger Band squeeze (width {bb_width:.3f}) — volatility breakout likely soon")

        # --- Stochastic insight ---
        stoch_sig = a.get("stoch_signal", 0)
        stoch_k = a.get("stoch_k")
        if stoch_sig == 1 and stoch_k is not None:
            insights.append(f"Stochastic oversold at {stoch_k:.0f} — confirms buy setup")
        elif stoch_sig == -1 and stoch_k is not None:
            insights.append(f"Stochastic overbought at {stoch_k:.0f} — confirms sell pressure")

        # --- Volume insight ---
        vol_sig = a.get("volume_signal", 0)
        vol_ratio = a.get("volume_ratio", 0)
        if vol_sig == 1:
            insights.append(f"Heavy buying volume ({vol_ratio:.1f}x average) — institutional accumulation likely")
        elif vol_sig == -1:
            insights.append(f"Heavy selling volume ({vol_ratio:.1f}x average) — institutional distribution likely")

        # --- 52-week context ---
        pct_high = a.get("pct_from_52w_high")
        pct_low = a.get("pct_from_52w_low")
        if pct_high is not None and pct_high > -2:
            insights.append(f"Trading near 52-week high ({pct_high:+.1f}%) — breakout territory")
        elif pct_high is not None and pct_high < -30:
            insights.append(f"Down {abs(pct_high):.0f}% from 52-week high — deep value territory if fundamentals intact")
        if pct_low is not None and pct_low < 5:
            insights.append(f"Near 52-week low ({pct_low:+.1f}% above) — capitulation risk or value opportunity")

        # --- Performance context ---
        ret_1m = a.get("return_1m")
        ret_3m = a.get("return_3m")
        ret_1y = a.get("return_1y")
        if ret_1m is not None and ret_1m > 10:
            insights.append(f"Strong recent momentum: +{ret_1m:.1f}% in past month")
        elif ret_1m is not None and ret_1m < -10:
            insights.append(f"Sharp decline: {ret_1m:.1f}% in past month — watch for reversal or further weakness")
        if ret_1y is not None and ret_1y > 50:
            insights.append(f"Exceptional 1-year performance: +{ret_1y:.0f}% — trend follower's pick but watch for mean reversion")
        elif ret_1y is not None and ret_1y < -20:
            insights.append(f"Underperforming over 1 year: {ret_1y:.0f}% — contrarian opportunity if catalysts emerge")

        # Ensure at least one insight
        if not insights:
            insights.append("Mixed signals — no strong directional conviction from technicals")

        return insights

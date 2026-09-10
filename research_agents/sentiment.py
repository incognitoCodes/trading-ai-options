"""sentiment.py — lightweight, dependency-free trader-sentiment signals.

Three read-outs a disciplined options seller cares about, all from data the
advisory already has (no paid API, no new key):

  1. news_sentiment(ticker)          — tone of recent headlines via a finance
                                       keyword lexicon (bullish vs bearish).
  2. options_positioning(calls,puts) — put/call volume & OI ratios plus IV
                                       skew, i.e. how option traders are
                                       actually positioned (greedy vs fearful).
  3. hold_quality(price_df)          — is this a name you'd be glad to own if a
                                       short put is assigned (trend, drawdown,
                                       distance from highs)?

Every function degrades gracefully to a neutral / unknown read on missing or
malformed data, and never raises.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 1. News sentiment (finance headline lexicon)
# --------------------------------------------------------------------------- #
# Deliberately finance-specific. General NLP models miss market phrasing, and a
# small curated lexicon is transparent and fast. Multi-word phrases are checked
# as substrings; single tokens are matched on word boundaries.
_BULLISH = {
    "beat", "beats", "tops", "topped", "surge", "surges", "surged", "soar",
    "soars", "soared", "rally", "rallies", "rallied", "record", "records",
    "upgrade", "upgraded", "upgrades", "outperform", "outperforms", "raises",
    "raised", "hikes", "hiked", "buyback", "buybacks", "jumps", "jumped",
    "gains", "gained", "higher", "strong", "stronger", "growth", "wins", "win",
    "won", "approval", "approved", "breakthrough", "bullish", "upside", "boost",
    "boosts", "boosted", "expands", "expansion", "accelerates", "momentum",
    "beat-and-raise", "guidance raise", "price target raised", "initiated buy",
    "all-time high", "blowout", "profit jump", "market-beating",
}
_BEARISH = {
    "miss", "misses", "missed", "plunge", "plunges", "plunged", "slump",
    "slumps", "slumped", "sinks", "sank", "sink", "downgrade", "downgraded",
    "downgrades", "underperform", "cuts", "cut", "lowers", "lowered", "warns",
    "warning", "lawsuit", "probe", "investigation", "recall", "recalls",
    "layoffs", "bankruptcy", "fraud", "halts", "halted", "drops", "dropped",
    "falls", "fell", "weak", "weaker", "decline", "declines", "declined",
    "slashes", "slashed", "bearish", "downside", "concern", "concerns",
    "fears", "selloff", "sell-off", "tumble", "tumbles", "tumbled", "slide",
    "slides", "guidance cut", "price target cut", "profit warning", "delist",
    "delisted", "subpoena", "SEC probe", "short seller", "misses estimates",
    "disappointing", "slowdown", "glut", "default",
}


def score_headlines(titles: list[str]) -> dict:
    """Score a list of headline strings. Pure and deterministic.

    Returns {label, score, bull, bear, n} where score is (bull - bear)
    normalized to roughly [-1, 1] by the number of headlines.
    """
    bull = bear = 0
    for title in titles or []:
        if not title:
            continue
        t = " " + str(title).lower() + " "
        for phrase in _BULLISH:
            if (" " + phrase + " ") in t if " " in phrase else _word_in(phrase, t):
                bull += 1
        for phrase in _BEARISH:
            if (" " + phrase + " ") in t if " " in phrase else _word_in(phrase, t):
                bear += 1

    n = len([x for x in (titles or []) if x])
    net = bull - bear
    denom = max(1, bull + bear)
    score = round(net / denom, 2)  # -1 .. 1
    if net >= 2 or (net >= 1 and score >= 0.5):
        label = "Bullish"
    elif net <= -2 or (net <= -1 and score <= -0.5):
        label = "Bearish"
    else:
        label = "Neutral"
    return {"label": label, "score": score, "bull": bull, "bear": bear, "n": n}


def _word_in(word: str, padded_lower_text: str) -> bool:
    return (" " + word + " ") in padded_lower_text


def _extract_titles(raw_news: list) -> list[dict]:
    """Normalize yfinance .news items (old and new shapes) to {title, age_days}."""
    import time as _time
    out = []
    now = _time.time()
    for item in raw_news or []:
        title = None
        ts = None
        if isinstance(item, dict):
            if item.get("title"):                       # older yfinance shape
                title = item.get("title")
                ts = item.get("providerPublishTime")
            elif isinstance(item.get("content"), dict):  # newer yfinance shape
                c = item["content"]
                title = c.get("title")
                pub = c.get("pubDate") or c.get("displayTime")
                if isinstance(pub, str):
                    try:
                        from datetime import datetime
                        ts = datetime.fromisoformat(
                            pub.replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:
                        ts = None
        if not title:
            continue
        age_days = round((now - ts) / 86400.0, 1) if ts else None
        out.append({"title": title, "age_days": age_days})
    return out


def news_sentiment(ticker: str, within_days: int = 14, max_items: int = 12) -> dict:
    """Recent-headline tone for a ticker via yfinance news + the finance lexicon.

    Makes one network call, so call it only for the shortlist you actually
    recommend, not the whole universe. Returns a neutral read on any failure.
    """
    empty = {"label": "Neutral", "score": 0.0, "bull": 0, "bear": 0,
             "n": 0, "headlines": []}
    try:
        import yfinance as yf
        raw = yf.Ticker(ticker).news or []
    except Exception as e:
        logger.debug(f"news fetch failed {ticker}: {e}")
        return empty

    items = _extract_titles(raw)
    if within_days:
        items = [
            it for it in items
            if it["age_days"] is None or it["age_days"] <= within_days
        ]
    items = items[:max_items]
    if not items:
        return empty

    res = score_headlines([it["title"] for it in items])
    res["headlines"] = items[:5]
    return res


# --------------------------------------------------------------------------- #
# 2. Options-trader positioning (put/call ratios + IV skew)
# --------------------------------------------------------------------------- #
def _col(df, name):
    for c in df.columns:
        if c.lower() == name:
            return c
    return None


def options_positioning(calls, puts, spot: Optional[float]) -> dict:
    """How option traders are positioned, from the chain itself.

    - Put/Call volume & OI ratios: >1 leans bearish/hedged, <1 leans bullish.
    - IV skew: OTM put IV minus OTM call IV; a steep positive skew is downside
      fear (hedging demand), a flat/negative skew is complacency/greed.
    """
    out = {"pc_vol_ratio": None, "pc_oi_ratio": None, "iv_skew": None,
           "label": "Neutral", "note": ""}
    try:
        if calls is None or puts is None or calls.empty or puts.empty:
            return out
        cvol_c, pvol_c = _col(calls, "volume"), _col(puts, "volume")
        coi_c, poi_c = _col(calls, "openinterest"), _col(puts, "openinterest")
        civ_c, piv_c = _col(calls, "impliedvolatility"), _col(puts, "impliedvolatility")
        cstk, pstk = _col(calls, "strike"), _col(puts, "strike")

        pc_vol = pc_oi = skew = None
        if cvol_c and pvol_c:
            cv = float(calls[cvol_c].fillna(0).sum())
            pv = float(puts[pvol_c].fillna(0).sum())
            pc_vol = round(pv / cv, 2) if cv > 0 else None
        if coi_c and poi_c:
            co = float(calls[coi_c].fillna(0).sum())
            po = float(puts[poi_c].fillna(0).sum())
            pc_oi = round(po / co, 2) if co > 0 else None

        if spot and spot > 0 and civ_c and piv_c and cstk and pstk:
            put_row = puts.assign(_d=(puts[pstk] - spot * 0.95).abs()).sort_values("_d")
            call_row = calls.assign(_d=(calls[cstk] - spot * 1.05).abs()).sort_values("_d")
            if not put_row.empty and not call_row.empty:
                piv = float(put_row.iloc[0][piv_c])
                civ = float(call_row.iloc[0][civ_c])
                if piv > 0 and civ > 0:
                    skew = round(piv - civ, 4)

        out.update(pc_vol_ratio=pc_vol, pc_oi_ratio=pc_oi, iv_skew=skew)

        # Interpret. Blend the ratios and skew into a single lean.
        bear = bull = 0
        if pc_vol is not None:
            bear += pc_vol > 1.3
            bull += pc_vol < 0.7
        if pc_oi is not None:
            bear += pc_oi > 1.3
            bull += pc_oi < 0.7
        if skew is not None:
            bear += skew > 0.06     # steep put skew = downside fear
            bull += skew < 0.01     # flat/inverted = complacent/greedy
        if bear > bull:
            out["label"] = "Bearish"
        elif bull > bear:
            out["label"] = "Bullish"
        parts = []
        if pc_vol is not None:
            parts.append(f"P/C vol {pc_vol:.2f}")
        if pc_oi is not None:
            parts.append(f"P/C OI {pc_oi:.2f}")
        if skew is not None:
            parts.append(f"skew {skew*100:+.1f}pp")
        out["note"] = ", ".join(parts)
    except Exception as e:
        logger.debug(f"options_positioning failed: {e}")
    return out


# --------------------------------------------------------------------------- #
# 3. Hold-quality — would you be glad to own this if a put is assigned?
# --------------------------------------------------------------------------- #
def _rsi(series, period: int = 14) -> Optional[float]:
    try:
        import numpy as np
        vals = series.astype(float).values
        if len(vals) < period + 1:
            return None
        delta = np.diff(vals)
        gain = np.clip(delta, 0, None)
        loss = -np.clip(delta, None, 0)
        ag = gain[-period:].mean()
        al = loss[-period:].mean()
        if al == 0:
            return 100.0
        rs = ag / al
        return round(100 - 100 / (1 + rs), 1)
    except Exception:
        return None


def hold_quality(price_df) -> dict:
    """Score how appropriate a name is to be assigned and hold short term.

    Rewards a healthy uptrend and penalizes falling knives and deep drawdowns.
    Returns {score 0-100, label, trend, reasons, rsi, ret_1m_pct}.
    """
    out = {"score": None, "label": "Unknown", "trend": "unknown",
           "reasons": [], "rsi": None, "ret_1m_pct": None}
    try:
        if price_df is None or len(price_df) < 30:
            return out
        close_c = _col(price_df, "close")
        if not close_c:
            return out
        close = price_df[close_c].astype(float)
        last = float(close.iloc[-1])
        if last <= 0:
            return out

        sma50 = float(close.tail(50).mean())
        sma200 = float(close.tail(min(200, len(close))).mean())
        ret_1m = last / float(close.iloc[-21]) - 1 if len(close) >= 21 else 0.0
        ret_3m = last / float(close.iloc[-63]) - 1 if len(close) >= 63 else 0.0
        high_52w = float(close.tail(min(252, len(close))).max())
        dist_high = last / high_52w - 1 if high_52w > 0 else 0.0
        rsi = _rsi(close)

        score = 50
        reasons = []
        if last > sma200:
            score += 20
        else:
            score -= 15
            reasons.append("below 200-day")
        if sma50 > sma200:
            score += 10
        else:
            score -= 5
        if ret_1m > -0.08:
            score += 10
        else:
            score -= 15
            reasons.append(f"1M {ret_1m*100:.0f}% (falling)")
        score += 5 if ret_3m > 0 else -5
        if dist_high > -0.15:
            score += 5
        elif dist_high < -0.30:
            score -= 10
            reasons.append(f"{dist_high*100:.0f}% off 52w high")
        if rsi is not None:
            if 40 <= rsi <= 70:
                score += 5
            elif rsi < 25:
                score -= 10
                reasons.append(f"RSI {rsi:.0f} (oversold, knife risk)")
            elif rsi > 80:
                score -= 5

        score = max(0, min(100, score))
        trend = "uptrend" if (last > sma200 and sma50 >= sma200) else (
            "downtrend" if last < sma200 else "mixed")
        label = "Strong" if score >= 70 else ("OK" if score >= 45 else "Weak")
        if not reasons:
            reasons.append(trend)
        out.update(score=score, label=label, trend=trend, reasons=reasons,
                   rsi=rsi, ret_1m_pct=round(ret_1m * 100, 1))
    except Exception as e:
        logger.debug(f"hold_quality failed: {e}")
    return out


# --------------------------------------------------------------------------- #
# Combined read
# --------------------------------------------------------------------------- #
def combined_bias(news_label: str, positioning_label: str) -> str:
    """Blend news tone and options positioning into one lean."""
    order = {"Bearish": -1, "Neutral": 0, "Bullish": 1}
    s = order.get(news_label, 0) + order.get(positioning_label, 0)
    if s >= 2:
        return "Bullish"
    if s <= -2:
        return "Bearish"
    if s == 1:
        return "Lean Bullish"
    if s == -1:
        return "Lean Bearish"
    return "Neutral"

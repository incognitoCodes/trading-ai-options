"""
options_backtester.py — Backtests the premium-selling strategy the
options advisor recommends: short put credit spreads on index ETFs.

Methodology (and its limits — read this before trusting any number):
  - Free historical option chains don't exist, so spreads are priced with
    Black-Scholes at entry using the REAL implied volatility index for the
    underlying (^VIX for SPY, ^VXN for QQQ) — not a proxy — with a +10%
    skew adjustment for the below-ATM short strike.
  - P&L at expiry is intrinsic value against the actual underlying price.
    Optional daily management (profit-take / stop-loss) reprices the
    spread with Black-Scholes at each day's IV.
  - Entry credit is haircut by SLIPPAGE_PCT to approximate crossing the
    bid/ask spread.
  - One spread per week, risking RISK_FRACTION of current equity.

This makes results directionally honest but approximate. It cannot see
weekend gaps in IV, early assignment, or real skew dynamics.

Validated defaults (SPY, 2019-2026, in/out-of-sample split): entry
filters (IV percentile, SMA200 trend) consistently REDUCED returns and
were rejected as defaults. Hold-to-expiry earns the most; 50%-profit /
3x-credit-stop management roughly halves max drawdown at the cost of
about half the CAGR. The default output shows both so the risk/return
trade-off is visible.

Usage:
  python -m research_agents.options_backtester                 # SPY: raw + managed
  python -m research_agents.options_backtester --underlying QQQ
  python -m research_agents.options_backtester --compare       # full filter grid
"""

import argparse
import logging
import math

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# --- Strategy parameters ---------------------------------------------------
SHORT_DELTA = 0.30        # short put delta target
WIDTH_PCT = 0.05          # spread width as fraction of spot
DTE_TRADING_DAYS = 30     # ~45 calendar days
RISK_FRACTION = 0.05      # fraction of equity risked per spread
SLIPPAGE_PCT = 0.10       # haircut on entry credit (bid/ask + fees)
SKEW_MULT = 1.10          # OTM put IV premium over the ATM index level
RISK_FREE = 0.03          # flat risk-free rate for BS pricing

IV_INDEX = {"SPY": "^VIX", "QQQ": "^VXN"}


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(spot, strike, t_years, iv, r=RISK_FREE):
    """Black-Scholes European put price."""
    if t_years <= 0 or iv <= 0:
        return max(strike - spot, 0.0)
    d1 = (math.log(spot / strike) + (r + iv * iv / 2) * t_years) / (iv * math.sqrt(t_years))
    d2 = d1 - iv * math.sqrt(t_years)
    return strike * math.exp(-r * t_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def strike_for_put_delta(spot, t_years, iv, target_delta, r=RISK_FREE):
    """Solve for the strike whose put delta magnitude equals target_delta."""
    # put delta = N(d1) - 1  ->  d1 = ppf(1 - target_delta)
    # invert d1 for strike
    from statistics import NormalDist
    d1 = NormalDist().inv_cdf(1.0 - target_delta)
    return spot * math.exp(-(d1 * iv * math.sqrt(t_years) - (r + iv * iv / 2) * t_years))


class OptionsBacktester:
    """Backtests weekly short put credit spreads on an index ETF."""

    def __init__(self, underlying: str = "SPY"):
        if underlying not in IV_INDEX:
            raise ValueError(f"Supported underlyings: {list(IV_INDEX)}")
        self.underlying = underlying
        self.iv_symbol = IV_INDEX[underlying]

    def load_data(self, period: str = "8y") -> pd.DataFrame:
        px = yf.Ticker(self.underlying).history(period=period, auto_adjust=True)
        iv = yf.Ticker(self.iv_symbol).history(period=period)
        # Normalize to naive dates: the ETF and its vol index can come back
        # in different exchange timezones, which breaks the index join.
        px.index = px.index.tz_localize(None).normalize()
        iv.index = iv.index.tz_localize(None).normalize()
        df = pd.DataFrame({
            "close": px["Close"],
            "iv": iv["Close"] / 100.0,
        }).dropna()
        df["sma200"] = df["close"].rolling(200).mean()
        df["iv_pctile"] = df["iv"].rolling(252).rank(pct=True) * 100
        return df.dropna()

    def run(
        self,
        df: pd.DataFrame,
        vol_filter: bool = False,
        trend_filter: bool = False,
        manage: bool = False,
        entry_interval: int = 5,
        profit_take: float = 0.50,
        loss_stop: float = 3.0,
    ) -> dict:
        """Simulate weekly spread entries.

        vol_filter:   enter only when IV percentile (1y) >= 30 — selling
                      premium when vol is at rock bottom collects too little
                      to cover the tail.
        trend_filter: enter only when the underlying is above its SMA200 —
                      short puts are a bullish position; don't sell them
                      into a downtrend.
        manage:       instead of holding to expiry, close early at
                      profit_take x credit profit, or stop out when the
                      spread marks at loss_stop x credit (repriced daily
                      with Black-Scholes at the day's IV).
        """
        closes = df["close"].values
        ivs = df["iv"].values
        sma200 = df["sma200"].values
        pctile = df["iv_pctile"].values
        dates = df.index
        n = len(df)
        t_years = DTE_TRADING_DAYS / 252.0

        equity = 1.0
        trades = []
        equity_curve = []
        # (expiry_idx, risked_amount, credit_per_share, k_short, k_long)
        open_spreads = []

        def close_spread(risked, credit, pnl_per_share, k_short, k_long, when):
            nonlocal equity
            max_loss = (k_short - k_long) - credit
            ror = pnl_per_share / max_loss if max_loss > 0 else 0.0
            equity += risked * ror
            trades.append({
                "date": when,
                "return_on_risk": ror,
                "pnl": risked * ror,
            })

        for i in range(n):
            spot = closes[i]

            # settle / manage open spreads
            still_open = []
            for exp_i, risked, credit, k_short, k_long in open_spreads:
                if i >= exp_i:
                    intrinsic = max(k_short - spot, 0.0) - max(k_long - spot, 0.0)
                    close_spread(risked, credit, credit - intrinsic,
                                 k_short, k_long, dates[min(exp_i, n - 1)])
                    continue
                if manage:
                    t_left = (exp_i - i) / 252.0
                    iv_now = ivs[i] * SKEW_MULT
                    value = (
                        bs_put(spot, k_short, t_left, iv_now)
                        - bs_put(spot, k_long, t_left, iv_now)
                    )
                    if value <= credit * (1 - profit_take):
                        # buy back cheap: keep profit_take share of credit
                        close_spread(risked, credit,
                                     credit - value * (1 + SLIPPAGE_PCT),
                                     k_short, k_long, dates[i])
                        continue
                    if value >= credit * loss_stop:
                        close_spread(risked, credit,
                                     credit - value * (1 + SLIPPAGE_PCT),
                                     k_short, k_long, dates[i])
                        continue
                still_open.append((exp_i, risked, credit, k_short, k_long))
            open_spreads = still_open

            # weekly entry
            if i % entry_interval == 0 and i + DTE_TRADING_DAYS < n:
                enter = True
                if vol_filter and pctile[i] < 30:
                    enter = False
                if trend_filter and spot < sma200[i]:
                    enter = False
                if enter:
                    iv = ivs[i] * SKEW_MULT
                    k_short = strike_for_put_delta(spot, t_years, iv, SHORT_DELTA)
                    k_long = k_short - spot * WIDTH_PCT
                    credit = (
                        bs_put(spot, k_short, t_years, iv)
                        - bs_put(spot, k_long, t_years, iv)
                    ) * (1 - SLIPPAGE_PCT)
                    max_loss = (k_short - k_long) - credit
                    if credit > 0 and max_loss > 0:
                        open_spreads.append(
                            (i + DTE_TRADING_DAYS, equity * RISK_FRACTION,
                             credit, k_short, k_long)
                        )

            equity_curve.append(equity)

        eq = np.array(equity_curve)
        weekly = eq[::5]
        wr = np.diff(weekly) / weekly[:-1]
        sharpe = (
            np.mean(wr) / np.std(wr) * np.sqrt(52) if np.std(wr) > 0 else 0.0
        )
        peak = np.maximum.accumulate(eq)
        max_dd = ((eq - peak) / np.where(peak > 0, peak, 1)).min() * 100
        years = n / 252.0
        total_ret = (equity - 1) * 100
        cagr = ((equity) ** (1 / years) - 1) * 100 if equity > 0 else -100.0
        wins = [t for t in trades if t["pnl"] > 0]

        return {
            "underlying": self.underlying,
            "start": str(dates[0].date()),
            "end": str(dates[-1].date()),
            "vol_filter": vol_filter,
            "trend_filter": trend_filter,
            "managed": manage,
            "n_trades": len(trades),
            "win_rate_pct": round(100 * len(wins) / len(trades), 1) if trades else 0.0,
            "avg_return_on_risk_pct": round(
                100 * float(np.mean([t["return_on_risk"] for t in trades])), 2
            ) if trades else 0.0,
            "total_return_pct": round(total_ret, 2),
            "cagr_pct": round(cagr, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(max_dd, 2),
        }

    @staticmethod
    def format_summary(results: list[dict]) -> str:
        lines = ["=" * 78]
        lines.append("OPTIONS PREMIUM BACKTEST — 30-delta put credit spreads, "
                     f"~45 DTE, {int(RISK_FRACTION*100)}% risk/trade")
        lines.append("=" * 78)
        lines.append(
            f"{'underlying':<11} {'filters':<14} {'trades':>6} {'win%':>6} "
            f"{'avgRoR':>7} {'total':>8} {'CAGR':>7} {'Sharpe':>7} {'maxDD':>7}"
        )
        lines.append("-" * 78)
        for r in results:
            filt = ("vol+trend" if r["vol_filter"] and r["trend_filter"]
                    else "vol" if r["vol_filter"]
                    else "trend" if r["trend_filter"] else "none")
            if r.get("managed"):
                filt += "+mgd"
            lines.append(
                f"{r['underlying']:<11} {filt:<14} {r['n_trades']:>6} "
                f"{r['win_rate_pct']:>5.1f}% {r['avg_return_on_risk_pct']:>+6.1f}% "
                f"{r['total_return_pct']:>+7.1f}% {r['cagr_pct']:>+6.1f}% "
                f"{r['sharpe_ratio']:>7.2f} {r['max_drawdown_pct']:>6.1f}%"
            )
        lines.append("-" * 78)
        lines.append("Model: Black-Scholes entry pricing w/ real IV index "
                     "(+10% skew), 10% credit slippage.")
        lines.append("'+mgd' = 50%-profit take / 3x-credit stop, repriced "
                     "daily. Approximate by construction.")
        lines.append("NOTE: Past performance does NOT guarantee future results.")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Backtest short put credit spreads."
    )
    parser.add_argument("--underlying", default="SPY", choices=list(IV_INDEX))
    parser.add_argument("--period", default="8y")
    parser.add_argument("--compare", action="store_true",
                        help="Run the full filter/management grid")
    args = parser.parse_args()

    bt = OptionsBacktester(args.underlying)
    print(f"Loading {args.underlying} + {IV_INDEX[args.underlying]} "
          f"({args.period})...")
    df = bt.load_data(args.period)
    print(f"{len(df)} trading days: {df.index[0].date()} - {df.index[-1].date()}\n")

    if args.compare:
        results = [
            bt.run(df, vol_filter=v, trend_filter=t, manage=m)
            for v, t, m in [
                (False, False, False), (True, False, False),
                (False, True, False), (True, True, False),
                (False, False, True), (True, True, True),
            ]
        ]
    else:
        results = [bt.run(df), bt.run(df, manage=True)]
    print(OptionsBacktester.format_summary(results))


if __name__ == "__main__":
    main()

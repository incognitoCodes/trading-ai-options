"""
strategies/vertical_spread.py — Bull Put Spread and Bear Call Spread.

WHAT IS A VERTICAL SPREAD?
A vertical spread uses two options of the same type (both calls OR both puts)
with the same expiry but different strikes. One is sold, one is bought.

=== BULL PUT SPREAD (credit spread, bullish) ===
You think the stock will stay ABOVE a certain price.

  Leg 1: SELL 1 Put at higher strike  (collect premium)
  Leg 2: BUY  1 Put at lower strike   (pay premium, limits risk)

  Example: AAPL at $200, you're bullish:
    SELL $195 Put @ $4.00
    BUY  $190 Put @ $2.50
    Net Credit = $1.50/share
    Max Profit = $150 (if AAPL stays above $195)
    Max Loss   = $350 (if AAPL falls below $190)
    Breakeven  = $193.50

=== BEAR CALL SPREAD (credit spread, bearish) ===
You think the stock will stay BELOW a certain price.

  Leg 1: SELL 1 Call at lower strike   (collect premium)
  Leg 2: BUY  1 Call at higher strike  (pay premium, limits risk)

  Example: AAPL at $200, you're bearish:
    SELL $205 Call @ $3.00
    BUY  $210 Call @ $1.50
    Net Credit = $1.50/share
    Max Profit = $150 (if AAPL stays below $205)
    Max Loss   = $350 (if AAPL rises above $210)
    Breakeven  = $206.50
"""

from strategies.base import BaseStrategy, Leg, StrategyResult
from strategies.utils import find_contract as _find_contract
from config import CONTRACT_MULTIPLIER


class BullPutSpread(BaseStrategy):
    """
    Bull Put Spread — credit spread using puts.

    Required strikes dict keys:
        "short_put": Higher strike (sell put here)
        "long_put":  Lower strike  (buy put here)

    Constraint: long_put < short_put
    """

    def build_legs(self, underlying, expiry, strikes, qty, chain_df):
        sp = strikes["short_put"]
        lp = strikes["long_put"]

        if not (lp < sp):
            raise ValueError(
                f"long_put ({lp}) must be less than short_put ({sp})"
            )

        sp_code, sp_prem = _find_contract(chain_df, sp, "PUT")
        lp_code, lp_prem = _find_contract(chain_df, lp, "PUT")

        return [
            Leg(code=sp_code, side="SELL", strike=sp, option_type="PUT",
                expiry=expiry, qty=qty, premium=sp_prem, label="Short Put"),
            Leg(code=lp_code, side="BUY",  strike=lp, option_type="PUT",
                expiry=expiry, qty=qty, premium=lp_prem, label="Long Put"),
        ]

    def compute_metrics(self, legs, underlying, expiry):
        short_put = next(l for l in legs if l.label == "Short Put")
        long_put = next(l for l in legs if l.label == "Long Put")
        qty = legs[0].qty

        net_credit = short_put.premium - long_put.premium
        spread_width = short_put.strike - long_put.strike

        max_profit = net_credit * qty * CONTRACT_MULTIPLIER
        max_loss = -(spread_width - net_credit) * qty * CONTRACT_MULTIPLIER
        breakeven = short_put.strike - net_credit

        return StrategyResult(
            name="Bull Put Spread",
            underlying=underlying,
            expiry=expiry,
            legs=legs,
            net_credit=net_credit,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakevens=[round(breakeven, 2)],
        )


class BearCallSpread(BaseStrategy):
    """
    Bear Call Spread — credit spread using calls.

    Required strikes dict keys:
        "short_call": Lower strike  (sell call here)
        "long_call":  Higher strike (buy call here)

    Constraint: short_call < long_call
    """

    def build_legs(self, underlying, expiry, strikes, qty, chain_df):
        sc = strikes["short_call"]
        lc = strikes["long_call"]

        if not (sc < lc):
            raise ValueError(
                f"short_call ({sc}) must be less than long_call ({lc})"
            )

        sc_code, sc_prem = _find_contract(chain_df, sc, "CALL")
        lc_code, lc_prem = _find_contract(chain_df, lc, "CALL")

        return [
            Leg(code=sc_code, side="SELL", strike=sc, option_type="CALL",
                expiry=expiry, qty=qty, premium=sc_prem, label="Short Call"),
            Leg(code=lc_code, side="BUY",  strike=lc, option_type="CALL",
                expiry=expiry, qty=qty, premium=lc_prem, label="Long Call"),
        ]

    def compute_metrics(self, legs, underlying, expiry):
        short_call = next(l for l in legs if l.label == "Short Call")
        long_call = next(l for l in legs if l.label == "Long Call")
        qty = legs[0].qty

        net_credit = short_call.premium - long_call.premium
        spread_width = long_call.strike - short_call.strike

        max_profit = net_credit * qty * CONTRACT_MULTIPLIER
        max_loss = -(spread_width - net_credit) * qty * CONTRACT_MULTIPLIER
        breakeven = short_call.strike + net_credit

        return StrategyResult(
            name="Bear Call Spread",
            underlying=underlying,
            expiry=expiry,
            legs=legs,
            net_credit=net_credit,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakevens=[round(breakeven, 2)],
        )

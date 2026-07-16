"""
strategies/iron_condor.py — Iron Condor options strategy.

WHAT IS AN IRON CONDOR?
An Iron Condor is a 4-leg, market-neutral strategy that profits when
the stock stays within a price range until expiry.

You SELL a narrower range (the "body") and BUY a wider range (the "wings")
to limit your risk.

STRUCTURE (all same expiry):
  Leg 1: BUY  1 Put  at low strike       (long put wing — protects downside)
  Leg 2: SELL 1 Put  at slightly higher   (short put — collects premium)
  Leg 3: SELL 1 Call at slightly lower    (short call — collects premium)
  Leg 4: BUY  1 Call at high strike       (long call wing — protects upside)

EXAMPLE with AAPL at $200:
  BUY  $175 Put  @ $1.20
  SELL $185 Put  @ $3.50
  SELL $215 Call @ $3.20
  BUY  $225 Call @ $1.10

  Net Credit = (3.50 - 1.20) + (3.20 - 1.10) = $4.40 per share
  Max Profit = $4.40 × 100 = $440 (if AAPL stays between $185-$215)
  Max Loss   = ($10 wing width - $4.40 credit) × 100 = $560

WHEN TO USE:
- You think the stock will stay in a range (low volatility expected)
- You want to collect premium with defined risk
"""

from strategies.base import BaseStrategy, Leg, StrategyResult
from strategies.utils import find_contract as _find_contract
from config import CONTRACT_MULTIPLIER


class IronCondor(BaseStrategy):
    """
    Iron Condor strategy implementation.

    Required strikes dict keys:
        "long_put":   Lowest strike  (buy put here)
        "short_put":  Next strike up (sell put here)
        "short_call": Next strike up (sell call here)
        "long_call":  Highest strike (buy call here)

    All 4 strikes must be in ascending order:
        long_put < short_put < short_call < long_call
    """

    def build_legs(self, underlying, expiry, strikes, qty, chain_df):
        """
        Build 4 Leg objects for an Iron Condor.

        Args:
            underlying: e.g. "AAPL"
            expiry:     e.g. "2025-06-18"
            strikes:    dict with keys: long_put, short_put, short_call, long_call
            qty:        number of contracts per leg
            chain_df:   option chain DataFrame

        Returns:
            list of 4 Leg objects
        """
        # Validate strike ordering
        lp = strikes["long_put"]
        sp = strikes["short_put"]
        sc = strikes["short_call"]
        lc = strikes["long_call"]

        if not (lp < sp < sc < lc):
            raise ValueError(
                f"Strikes must be in order: long_put ({lp}) < short_put ({sp}) "
                f"< short_call ({sc}) < long_call ({lc})"
            )

        # Look up each contract in the chain
        lp_code, lp_prem = _find_contract(chain_df, lp, "PUT")
        sp_code, sp_prem = _find_contract(chain_df, sp, "PUT")
        sc_code, sc_prem = _find_contract(chain_df, sc, "CALL")
        lc_code, lc_prem = _find_contract(chain_df, lc, "CALL")

        legs = [
            Leg(code=lp_code, side="BUY",  strike=lp, option_type="PUT",
                expiry=expiry, qty=qty, premium=lp_prem, label="Long Put Wing"),
            Leg(code=sp_code, side="SELL", strike=sp, option_type="PUT",
                expiry=expiry, qty=qty, premium=sp_prem, label="Short Put"),
            Leg(code=sc_code, side="SELL", strike=sc, option_type="CALL",
                expiry=expiry, qty=qty, premium=sc_prem, label="Short Call"),
            Leg(code=lc_code, side="BUY",  strike=lc, option_type="CALL",
                expiry=expiry, qty=qty, premium=lc_prem, label="Long Call Wing"),
        ]

        return legs

    def compute_metrics(self, legs, underlying, expiry):
        """
        Calculate max profit, max loss, and breakevens for an Iron Condor.

        Math:
            Net Credit = (short_put_prem - long_put_prem) + (short_call_prem - long_call_prem)
            Max Profit = Net Credit × qty × 100
            Max Loss   = (wing_width - Net Credit) × qty × 100
            Breakeven Low  = short_put_strike - Net Credit
            Breakeven High = short_call_strike + Net Credit
        """
        # Identify each leg by label
        long_put = next(l for l in legs if l.label == "Long Put Wing")
        short_put = next(l for l in legs if l.label == "Short Put")
        short_call = next(l for l in legs if l.label == "Short Call")
        long_call = next(l for l in legs if l.label == "Long Call Wing")

        qty = legs[0].qty

        # Net credit per share
        put_credit = short_put.premium - long_put.premium
        call_credit = short_call.premium - long_call.premium
        net_credit = put_credit + call_credit

        # Wing width (assume put side; both sides should be equal for a balanced IC)
        put_wing_width = short_put.strike - long_put.strike
        call_wing_width = long_call.strike - short_call.strike
        wing_width = max(put_wing_width, call_wing_width)

        # Max profit and loss (in dollars)
        max_profit = net_credit * qty * CONTRACT_MULTIPLIER
        max_loss = -(wing_width - net_credit) * qty * CONTRACT_MULTIPLIER

        # Breakeven prices
        be_low = short_put.strike - net_credit
        be_high = short_call.strike + net_credit

        return StrategyResult(
            name="Iron Condor",
            underlying=underlying,
            expiry=expiry,
            legs=legs,
            net_credit=net_credit,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakevens=[round(be_low, 2), round(be_high, 2)],
        )

"""
strategies/iron_butterfly.py — Iron Butterfly options strategy.

WHAT IS AN IRON BUTTERFLY?
An Iron Butterfly is similar to an Iron Condor, but the two short strikes
are at the SAME price (at-the-money). This creates a very concentrated
profit zone — you make the most money if the stock expires exactly at
the short strike.

STRUCTURE (all same expiry):
  Leg 1: BUY  1 Put  at lower strike    (long put wing)
  Leg 2: SELL 1 Put  at middle strike   (short put — ATM)
  Leg 3: SELL 1 Call at middle strike   (short call — ATM, same strike as put)
  Leg 4: BUY  1 Call at higher strike   (long call wing)

EXAMPLE with AAPL at $200:
  BUY  $190 Put  @ $1.50
  SELL $200 Put  @ $5.00
  SELL $200 Call @ $5.50
  BUY  $210 Call @ $2.00

  Net Credit = (5.00 - 1.50) + (5.50 - 2.00) = $7.00 per share
  Max Profit = $7.00 × 100 = $700 (if AAPL is exactly $200 at expiry)
  Max Loss   = ($10 wing width - $7.00 credit) × 100 = $300
  Breakeven Low  = $200 - $7.00 = $193.00
  Breakeven High = $200 + $7.00 = $207.00

WHEN TO USE:
- You think the stock will barely move (very low volatility expected)
- You want higher premium collection than an Iron Condor
- You're OK with a narrower profit zone in exchange for more premium

IRON BUTTERFLY vs IRON CONDOR:
- Butterfly: Short strikes are the same (ATM) → higher premium, narrower range
- Condor: Short strikes are different (OTM) → lower premium, wider range
"""

from strategies.base import BaseStrategy, Leg, StrategyResult
from strategies.utils import find_contract as _find_contract
from config import CONTRACT_MULTIPLIER


class IronButterfly(BaseStrategy):
    """
    Iron Butterfly strategy implementation.

    Required strikes dict keys:
        "long_put":    Lower strike (buy put wing)
        "short_strike": Middle strike (sell both put AND call here — ATM)
        "long_call":   Higher strike (buy call wing)

    Constraints:
        long_put < short_strike < long_call
    """

    def build_legs(self, underlying, expiry, strikes, qty, chain_df):
        """
        Build 4 Leg objects for an Iron Butterfly.

        Note: The short put and short call share the SAME strike price.
        """
        lp = strikes["long_put"]
        ss = strikes["short_strike"]
        lc = strikes["long_call"]

        if not (lp < ss < lc):
            raise ValueError(
                f"Strikes must be in order: long_put ({lp}) < "
                f"short_strike ({ss}) < long_call ({lc})"
            )

        lp_code, lp_prem = _find_contract(chain_df, lp, "PUT")
        sp_code, sp_prem = _find_contract(chain_df, ss, "PUT")
        sc_code, sc_prem = _find_contract(chain_df, ss, "CALL")
        lc_code, lc_prem = _find_contract(chain_df, lc, "CALL")

        legs = [
            Leg(code=lp_code, side="BUY",  strike=lp, option_type="PUT",
                expiry=expiry, qty=qty, premium=lp_prem, label="Long Put Wing"),
            Leg(code=sp_code, side="SELL", strike=ss, option_type="PUT",
                expiry=expiry, qty=qty, premium=sp_prem, label="Short Put (ATM)"),
            Leg(code=sc_code, side="SELL", strike=ss, option_type="CALL",
                expiry=expiry, qty=qty, premium=sc_prem, label="Short Call (ATM)"),
            Leg(code=lc_code, side="BUY",  strike=lc, option_type="CALL",
                expiry=expiry, qty=qty, premium=lc_prem, label="Long Call Wing"),
        ]

        return legs

    def compute_metrics(self, legs, underlying, expiry):
        """
        Calculate metrics for an Iron Butterfly.

        Math:
            Net Credit = (short_put_prem - long_put_prem) + (short_call_prem - long_call_prem)
            Max Profit = Net Credit × qty × 100  (at expiry, stock = short_strike exactly)
            Max Loss   = (wing_width - Net Credit) × qty × 100
            Breakeven Low  = short_strike - Net Credit
            Breakeven High = short_strike + Net Credit
        """
        long_put = next(l for l in legs if l.label == "Long Put Wing")
        short_put = next(l for l in legs if "Short Put" in l.label)
        short_call = next(l for l in legs if "Short Call" in l.label)
        long_call = next(l for l in legs if l.label == "Long Call Wing")

        qty = legs[0].qty
        short_strike = short_put.strike  # Same as short_call.strike

        # Net credit per share
        put_credit = short_put.premium - long_put.premium
        call_credit = short_call.premium - long_call.premium
        net_credit = put_credit + call_credit

        # Wing width (use the wider side if asymmetric)
        put_wing = short_strike - long_put.strike
        call_wing = long_call.strike - short_strike
        wing_width = max(put_wing, call_wing)

        # Max profit and loss
        max_profit = net_credit * qty * CONTRACT_MULTIPLIER
        max_loss = -(wing_width - net_credit) * qty * CONTRACT_MULTIPLIER

        # Breakevens
        be_low = short_strike - net_credit
        be_high = short_strike + net_credit

        return StrategyResult(
            name="Iron Butterfly",
            underlying=underlying,
            expiry=expiry,
            legs=legs,
            net_credit=net_credit,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakevens=[round(be_low, 2), round(be_high, 2)],
        )

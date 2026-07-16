"""
strategies/naked_option.py — Single-leg (naked) option buy or sell.

WHAT IS A NAKED OPTION?
A "naked" option is a single-leg position — you either buy or sell
one option contract without any hedge.

=== NAKED CALL SELL (bearish / neutral) ===
You sell a call without owning the stock. You collect premium and hope
the stock stays below the strike. Risk is theoretically unlimited.

=== NAKED PUT SELL (bullish / neutral) ===
You sell a put without shorting the stock. You collect premium and hope
the stock stays above the strike. Risk is the strike price minus premium
(stock goes to zero).

=== LONG CALL (bullish) ===
You buy a call. You profit if the stock rises above strike + premium.
Max loss is the premium paid.

=== LONG PUT (bearish) ===
You buy a put. You profit if the stock falls below strike - premium.
Max loss is the premium paid.

WHEN TO USE:
- Naked sell: High IV, collecting premium, comfortable with the risk
- Long buy: Directional bet with defined risk
"""

from strategies.base import BaseStrategy, Leg, StrategyResult
from strategies.utils import find_contract as _find_contract
from config import CONTRACT_MULTIPLIER


class NakedOption(BaseStrategy):
    """
    Single-leg option position (buy or sell a single call or put).

    Required strikes dict keys:
        "strike": The strike price
        "option_type": "CALL" or "PUT"
        "side": "BUY" or "SELL"
    """

    def build_legs(self, underlying, expiry, strikes, qty, chain_df):
        """
        Build a single Leg for a naked option.

        Args:
            strikes: dict with keys: strike, option_type, side
        """
        strike = strikes["strike"]
        option_type = strikes["option_type"]
        side = strikes["side"]

        code, premium = _find_contract(chain_df, strike, option_type)

        if side == "SELL":
            label = f"Short {option_type.title()}"
        else:
            label = f"Long {option_type.title()}"

        return [
            Leg(
                code=code,
                side=side,
                strike=strike,
                option_type=option_type,
                expiry=expiry,
                qty=qty,
                premium=premium,
                label=label,
            )
        ]

    def compute_metrics(self, legs, underlying, expiry):
        """
        Calculate metrics for a naked option.

        Math:
            SELL CALL: max_profit = premium * qty * 100, max_loss = "unlimited"
            SELL PUT:  max_profit = premium * qty * 100, max_loss = (strike - premium) * qty * 100
            BUY CALL:  max_profit = "unlimited", max_loss = premium * qty * 100
            BUY PUT:   max_profit = (strike - premium) * qty * 100, max_loss = premium * qty * 100
        """
        leg = legs[0]
        qty = leg.qty
        premium_total = leg.premium * qty * CONTRACT_MULTIPLIER

        if leg.side == "SELL":
            net_credit = leg.premium
            max_profit = premium_total

            if leg.option_type == "CALL":
                # Unlimited risk, cap at 5x premium for display
                max_loss = round(-premium_total * 5, 2)
            else:
                # Max loss if stock goes to 0
                max_loss = round(-(leg.strike - leg.premium) * qty * CONTRACT_MULTIPLIER, 2)

            if leg.option_type == "CALL":
                breakeven = leg.strike + leg.premium
            else:
                breakeven = leg.strike - leg.premium

        else:  # BUY
            net_credit = -leg.premium  # Debit
            max_loss = round(-premium_total, 2)

            if leg.option_type == "CALL":
                # Unlimited upside, cap at 5x premium for display
                max_profit = round(premium_total * 5, 2)
                breakeven = leg.strike + leg.premium
            else:
                # Max profit if stock goes to 0
                max_profit = round((leg.strike - leg.premium) * qty * CONTRACT_MULTIPLIER, 2)
                breakeven = leg.strike - leg.premium

        return StrategyResult(
            name=f"Naked {leg.side.title()} {leg.option_type.title()}",
            underlying=underlying,
            expiry=expiry,
            legs=legs,
            net_credit=net_credit,
            max_profit=round(max_profit, 2),
            max_loss=round(max_loss, 2),
            breakevens=[round(breakeven, 2)],
        )

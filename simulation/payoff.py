"""
simulation/payoff.py — Pure math for computing option payoffs at expiry.

NO API calls happen here. This module works entirely with numbers,
so you can test it without a MooMoo connection or OpenD running.

KEY CONCEPTS FOR BEGINNERS:
- "Payoff" = how much money you make or lose at expiry for a given stock price.
- A CALL option payoff at expiry = max(stock_price - strike, 0) - premium_paid
- A PUT option payoff at expiry  = max(strike - stock_price, 0) - premium_paid
- When you SELL an option, the payoff is the mirror image (you keep the premium
  but face the opposite risk).
- "Breakeven" = the stock price where your total P&L equals zero.
"""

import numpy as np
from config import CONTRACT_MULTIPLIER


def option_payoff_at_expiry(side, option_type, strike, premium, qty, prices):
    """
    Compute the P&L of a single option leg at expiry across a range of prices.

    Args:
        side:        "BUY" or "SELL"
        option_type: "CALL" or "PUT"
        strike:      Strike price (e.g. 185.0)
        premium:     Per-share premium paid/received (e.g. 3.50)
        qty:         Number of contracts (e.g. 1)
        prices:      numpy array of underlying prices to evaluate

    Returns:
        numpy array of P&L values in dollars (one per price point)

    Example:
        If you BUY 1 AAPL $185 Call for $3.50 premium:
        - At AAPL = $190: payoff = (190 - 185 - 3.50) * 100 = $150
        - At AAPL = $180: payoff = (0 - 3.50) * 100 = -$350 (you lose the premium)
    """
    prices = np.asarray(prices, dtype=float)

    # Step 1: Calculate the option's intrinsic value at expiry
    if option_type.upper() == "CALL":
        # Call option: worth something only if stock > strike
        intrinsic = np.maximum(prices - strike, 0)
    else:
        # Put option: worth something only if stock < strike
        intrinsic = np.maximum(strike - prices, 0)

    # Step 2: Calculate P&L per share
    if side.upper() == "BUY":
        # Buyer pays premium upfront, profits from intrinsic value
        pnl_per_share = intrinsic - premium
    else:
        # Seller collects premium upfront, loses from intrinsic value
        pnl_per_share = premium - intrinsic

    # Step 3: Scale by number of contracts and contract multiplier (100 shares per contract)
    total_pnl = pnl_per_share * qty * CONTRACT_MULTIPLIER

    return total_pnl


def combined_payoff(legs, prices):
    """
    Compute the total P&L of a multi-leg strategy at expiry.

    Simply adds up the payoff of each individual leg.

    Args:
        legs:   list of Leg objects (from strategies/base.py)
        prices: numpy array of underlying prices

    Returns:
        numpy array of total P&L values in dollars
    """
    prices = np.asarray(prices, dtype=float)
    total = np.zeros_like(prices)

    for leg in legs:
        total += option_payoff_at_expiry(
            side=leg.side,
            option_type=leg.option_type,
            strike=leg.strike,
            premium=leg.premium,
            qty=leg.qty,
            prices=prices,
        )

    return total


def find_breakevens(payoff, prices):
    """
    Find the stock prices where the strategy's P&L crosses zero.

    Works by detecting sign changes in the payoff array.
    Uses linear interpolation for a more accurate estimate.

    Args:
        payoff: numpy array of P&L values
        prices: numpy array of corresponding stock prices

    Returns:
        list of breakeven prices (floats), sorted ascending

    Example:
        If payoff goes from -100 at price=180 to +50 at price=185,
        the breakeven is approximately $183.33.
    """
    breakevens = []
    for i in range(len(payoff) - 1):
        # Check if the sign changes between consecutive points
        if payoff[i] * payoff[i + 1] < 0:
            # Linear interpolation to find the zero crossing
            # Formula: price = p1 + (p2 - p1) * |pnl1| / (|pnl1| + |pnl2|)
            p1, p2 = prices[i], prices[i + 1]
            pnl1, pnl2 = abs(payoff[i]), abs(payoff[i + 1])
            breakeven = p1 + (p2 - p1) * pnl1 / (pnl1 + pnl2)
            breakevens.append(round(breakeven, 2))

    return sorted(breakevens)


def compute_max_profit_loss(payoff):
    """
    Find the maximum profit and maximum loss from a payoff array.

    Args:
        payoff: numpy array of P&L values

    Returns:
        tuple of (max_profit, max_loss)
        max_profit is positive, max_loss is negative
    """
    max_profit = round(float(np.max(payoff)), 2)
    max_loss = round(float(np.min(payoff)), 2)
    return max_profit, max_loss


def generate_price_range(current_price, range_pct=0.20, steps=500):
    """
    Generate an array of stock prices centered around the current price.

    Args:
        current_price: The current stock price (e.g. 185.0)
        range_pct:     How far to extend on each side (0.20 = 20%)
        steps:         Number of price points to generate

    Returns:
        numpy array of evenly spaced prices

    Example:
        generate_price_range(200, 0.20, 500) → array from $160 to $240
    """
    low = current_price * (1 - range_pct)
    high = current_price * (1 + range_pct)
    return np.linspace(low, high, steps)

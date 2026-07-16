"""
api/orders.py — Wrapper around MooMoo's place_order for option trades.

This module adds safety features on top of the raw SDK:
- dry_run mode: prints what WOULD be ordered without actually sending
- Detailed error reporting
- Returns a clean dict instead of raw SDK output

KEY CONCEPTS:
- Each option order is for a specific contract code (e.g. "US.AAPL250618C185000")
- "BUY" = buy to open (you're buying the option)
- "SELL" = sell to open (you're selling/writing the option)
- qty is in CONTRACTS (1 contract = 100 shares)
- price is the per-share limit price (premium)
"""

import time
from moomoo import RET_OK, TrdSide, OrderType, TrdEnv
from api import MoomooAPIError
import config


def place_single_leg(
    trade_ctx,
    code,
    side,
    qty,
    price,
    trd_env,
    acc_id,
    dry_run=False,
):
    """
    Place a single option order (one leg of a multi-leg strategy).

    Args:
        trade_ctx: An OpenSecTradeContext from connection.py
        code:      Contract code, e.g. "US.AAPL250618C185000"
        side:      "BUY" or "SELL"
        qty:       Number of contracts (e.g. 1)
        price:     Per-share limit price (e.g. 3.50)
        trd_env:   TrdEnv.SIMULATE (paper) or TrdEnv.REAL (live)
        acc_id:    Account ID from broker/account.py
        dry_run:   If True, just print the order without sending it

    Returns:
        dict with keys:
            order_id: str (or "DRY_RUN" if dry_run=True)
            code:     str
            side:     str
            qty:      int
            price:    float
            status:   str ("SUBMITTED" or "DRY_RUN")

    Raises:
        MoomooAPIError if the order placement fails.
    """
    # Map string side to SDK enum
    trd_side = TrdSide.BUY if side.upper() == "BUY" else TrdSide.SELL

    env_label = "PAPER" if trd_env == TrdEnv.SIMULATE else "LIVE"

    if dry_run:
        print(f"  [DRY RUN] {side} {qty}x {code} @ ${price:.2f} ({env_label})")
        return {
            "order_id": "DRY_RUN",
            "code": code,
            "side": side,
            "qty": qty,
            "price": price,
            "status": "DRY_RUN",
        }

    # Small delay to respect rate limits
    time.sleep(config.API_SLEEP_SECONDS)

    ret, data = trade_ctx.place_order(
        price=price,
        qty=qty,
        code=code,
        trd_side=trd_side,
        order_type=OrderType.NORMAL,  # Limit order
        trd_env=trd_env,
        acc_id=acc_id,
    )

    if ret != RET_OK:
        raise MoomooAPIError(
            f"Order failed for {side} {qty}x {code} @ ${price:.2f}: {data}"
        )

    # Extract order ID from the response
    order_id = str(data.iloc[0].get("order_id", "UNKNOWN"))

    print(f"  [PLACED] {side} {qty}x {code} @ ${price:.2f} → Order ID: {order_id} ({env_label})")

    return {
        "order_id": order_id,
        "code": code,
        "side": side,
        "qty": qty,
        "price": price,
        "status": "SUBMITTED",
    }

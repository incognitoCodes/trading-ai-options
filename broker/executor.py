"""
broker/executor.py — Multi-leg trade execution with safety guardrails.

This is the SAFETY GATE of the system. Every trade passes through here.

Safety features:
1. dry_run mode by default — shows what would happen without placing orders
2. Requires explicit "YES" confirmation before any real order
3. Stops immediately if any leg fails (won't blindly continue)
4. Logs every order to CSV
5. Paper trading only (unless you explicitly enable live mode)
"""

from moomoo import TrdEnv
from api.orders import place_single_leg
from api import MoomooAPIError
from logging_utils.trade_logger import log_trade


def confirm_execution(legs, trd_env, dry_run):
    """
    Show a summary of all legs and ask the user to confirm.

    Args:
        legs:    list of Leg objects
        trd_env: TrdEnv.SIMULATE or TrdEnv.REAL
        dry_run: Whether this is a dry run (no real orders)

    Returns:
        True if the user types "YES", False otherwise.
    """
    env_label = "PAPER TRADING" if trd_env == TrdEnv.SIMULATE else "*** LIVE TRADING ***"
    mode_label = "(DRY RUN — no orders will be sent)" if dry_run else "(ORDERS WILL BE PLACED)"

    print()
    print("  " + "=" * 55)
    print(f"  TRADE CONFIRMATION — {env_label}")
    print(f"  {mode_label}")
    print("  " + "=" * 55)
    print()

    for i, leg in enumerate(legs, 1):
        print(
            f"    Leg {i}: {leg.side:<4} {leg.qty}x {leg.option_type:<4} "
            f"${leg.strike:<8.2f} @ ${leg.premium:.2f}  ({leg.label})"
        )

    print()

    if dry_run:
        response = input("  Press Enter to run dry simulation, or 'N' to cancel: ").strip()
        return response.upper() != "N"
    else:
        print("  *** WARNING: This will place real orders! ***")
        response = input("  Type YES to confirm, or anything else to cancel: ").strip()
        return response == "YES"


def execute_strategy(
    conn,
    legs,
    acc_id,
    trd_env,
    strategy_name="",
    underlying="",
    expiry="",
    dry_run=True,
):
    """
    Execute all legs of an options strategy.

    This function iterates through each leg, places the order, and logs it.
    If any leg fails, it STOPS immediately and tells you which legs succeeded.

    Args:
        conn:           MoomooConnection (has .trade_ctx)
        legs:           list of Leg objects from a strategy
        acc_id:         Account ID to trade in
        trd_env:        TrdEnv.SIMULATE or TrdEnv.REAL
        strategy_name:  For logging, e.g. "Iron Condor"
        underlying:     For logging, e.g. "AAPL"
        expiry:         For logging, e.g. "2025-06-18"
        dry_run:        If True, simulate orders without sending (default: True)

    Returns:
        list of result dicts from place_single_leg()

    Raises:
        Nothing — errors are caught and reported to the user.
    """
    # Ask for confirmation first
    if not confirm_execution(legs, trd_env, dry_run):
        print("\n  Trade cancelled by user.")
        return []

    print()
    print("  Executing legs...")
    print("  " + "-" * 40)

    results = []
    failed = False

    for i, leg in enumerate(legs, 1):
        print(f"\n  Leg {i}/{len(legs)}: {leg.label}")

        try:
            result = place_single_leg(
                trade_ctx=conn.trade_ctx,
                code=leg.code,
                side=leg.side,
                qty=leg.qty,
                price=leg.premium,
                trd_env=trd_env,
                acc_id=acc_id,
                dry_run=dry_run,
            )
            results.append(result)

            # Log to CSV
            env_str = "SIMULATE" if trd_env == TrdEnv.SIMULATE else "REAL"
            log_trade(
                strategy=strategy_name,
                underlying=underlying,
                expiry=expiry,
                leg=leg,
                order_result=result,
                trd_env=env_str,
            )

        except MoomooAPIError as e:
            print(f"\n  *** FAILED on Leg {i} ({leg.label}): {e} ***")
            failed = True
            break

        except Exception as e:
            print(f"\n  *** UNEXPECTED ERROR on Leg {i}: {e} ***")
            failed = True
            break

    # Summary
    print()
    print("  " + "-" * 40)

    if failed:
        print(f"  EXECUTION STOPPED: {len(results)}/{len(legs)} legs placed.")
        if results:
            print("  WARNING: Some legs were already placed!")
            print("  Please check your positions in the MooMoo app.")
            print("  You may need to manually close the partial position.")
    else:
        status = "simulated" if dry_run else "placed"
        print(f"  All {len(results)} legs {status} successfully.")

    return results

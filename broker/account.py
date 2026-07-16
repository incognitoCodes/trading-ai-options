"""
broker/account.py — Account discovery and management.

When you connect to MooMoo, you might have multiple accounts:
- A cash account (stocks only)
- A margin account (stocks + options)
- Paper trading accounts (one for stocks, one for options, one for futures)

This module finds the RIGHT account for options paper trading
so you don't accidentally trade in the wrong account.
"""

from datetime import datetime, timezone, timedelta
from moomoo import RET_OK, TrdEnv
from api import MoomooAPIError, MoomooConnectionError


def get_acc_list(trade_ctx):
    """
    Retrieve the full list of trading accounts.

    Args:
        trade_ctx: An OpenSecTradeContext

    Returns:
        DataFrame with columns: acc_id, trd_env, acc_type, sim_acc_type, ...
    """
    ret, data = trade_ctx.get_acc_list()
    if ret != RET_OK:
        raise MoomooAPIError(f"Failed to get account list: {data}")
    return data


def get_options_account(trade_ctx, trd_env):
    """
    Find the account ID suitable for options trading.

    For paper trading (TrdEnv.SIMULATE):
        Looks for sim_acc_type containing "OPTION"

    For live trading (TrdEnv.REAL):
        Looks for a margin-type account (needed for options)

    Args:
        trade_ctx: An OpenSecTradeContext
        trd_env:   TrdEnv.SIMULATE or TrdEnv.REAL

    Returns:
        Integer account ID (acc_id)

    Raises:
        RuntimeError if no matching account is found.
    """
    acc_df = get_acc_list(trade_ctx)

    # Debug: show all accounts so we can see what's available
    print("\n  Available accounts:")
    for _, row in acc_df.iterrows():
        env_val = row.get("trd_env", "?")
        acc_type = row.get("acc_type", "?")
        sim_type = row.get("sim_acc_type", "?")
        acc_id = row.get("acc_id", "?")
        print(f"    acc_id={acc_id}  trd_env={env_val}  acc_type={acc_type}  sim_acc_type={sim_type}")
    print()

    if trd_env == TrdEnv.SIMULATE:
        # Filter for simulation accounts — compare as string since format varies
        sim_accounts = acc_df[acc_df["trd_env"].astype(str).str.contains("SIMULATE|0", case=False, na=False)]

        # If that didn't work, try matching the TrdEnv enum directly
        if sim_accounts.empty:
            sim_accounts = acc_df[acc_df["trd_env"] == TrdEnv.SIMULATE]

        # If still empty, just use all accounts (will filter by sim_acc_type next)
        if sim_accounts.empty:
            sim_accounts = acc_df

        # Try to find an options-specific paper account
        # MooMoo sim_acc_type can be: SimAccType.OPTION, "OPTION", 2, "SimAccType.OPTION", etc.
        for _, row in sim_accounts.iterrows():
            sim_type = str(row.get("sim_acc_type", "")).upper()
            if "OPTION" in sim_type:
                acc_id = int(row["acc_id"])
                print(f"  Found options paper account: acc_id={acc_id}")
                return acc_id

        # Try matching by numeric sim_acc_type (SimAccType.OPTION = 2)
        for _, row in sim_accounts.iterrows():
            sim_type_val = row.get("sim_acc_type", None)
            try:
                if int(sim_type_val) == 2:  # SimAccType.OPTION = 2
                    acc_id = int(row["acc_id"])
                    print(f"  Found options paper account (numeric match): acc_id={acc_id}")
                    return acc_id
            except (ValueError, TypeError):
                pass

        # Last resort: try to find by acc_type containing "margin" or "option"
        for _, row in sim_accounts.iterrows():
            acc_type = str(row.get("acc_type", "")).upper()
            if "OPTION" in acc_type or "MARGIN" in acc_type:
                acc_id = int(row["acc_id"])
                print(f"  Found account by acc_type match: acc_id={acc_id}")
                return acc_id

        # If no options-specific account, show a clear error
        if not sim_accounts.empty:
            print("  WARNING: Could not find an options-specific paper account.")
            print("  Available paper accounts:")
            for _, row in sim_accounts.iterrows():
                print(f"    acc_id={row['acc_id']}  sim_acc_type={row.get('sim_acc_type', '?')}")
            print()
            print("  Please select which account to use:")
            for i, (_, row) in enumerate(sim_accounts.iterrows(), 1):
                print(f"    {i}. acc_id={row['acc_id']}  type={row.get('sim_acc_type', '?')}")
            while True:
                choice = input(f"  Select (1-{len(sim_accounts)}): ").strip()
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(sim_accounts):
                        acc_id = int(sim_accounts.iloc[idx]["acc_id"])
                        print(f"  Using acc_id={acc_id}")
                        return acc_id
                except ValueError:
                    pass
                print("  Invalid choice. Try again.")

        raise RuntimeError(
            "No paper trading account found. Make sure you have a simulation "
            "account set up in your MooMoo app.\n"
            "In MooMoo Desktop: Trade → Paper Trading → make sure US Options paper account exists."
        )

    else:  # TrdEnv.REAL
        # For live trading, look for a REAL account
        real_accounts = acc_df[acc_df["trd_env"].astype(str).str.contains("REAL", case=False, na=False)]
        if real_accounts.empty:
            real_accounts = acc_df[acc_df["trd_env"] == TrdEnv.REAL]

        if not real_accounts.empty:
            # Prefer margin account over cash for options
            for _, row in real_accounts.iterrows():
                acc_type = str(row.get("acc_type", "")).upper()
                if "MARGIN" in acc_type:
                    acc_id = int(row["acc_id"])
                    print(f"  Found real margin account: acc_id={acc_id}")
                    return acc_id
            # Fall back to first real account
            acc_id = int(real_accounts.iloc[0]["acc_id"])
            print(f"  Using real account: acc_id={acc_id}")
            return acc_id

        # No REAL accounts found — check if user has a real brokerage account
        # Let user choose from ANY available account as a fallback
        print("  No REAL trading accounts found.")
        print("  This could mean:")
        print("    1. You don't have a real brokerage account with MooMoo yet")
        print("    2. Options trading isn't enabled on your real account")
        print("    3. OpenD may need the right SecurityFirm setting")
        print()

        if not acc_df.empty:
            print("  Available accounts (all types):")
            for i, (_, row) in enumerate(acc_df.iterrows(), 1):
                print(
                    f"    {i}. acc_id={row['acc_id']}  trd_env={row.get('trd_env', '?')}  "
                    f"acc_type={row.get('acc_type', '?')}  sim_acc_type={row.get('sim_acc_type', '?')}"
                )
            print()
            use_anyway = input("  Try using one of these accounts? (y/n): ").strip().lower()
            if use_anyway == "y":
                while True:
                    choice = input(f"  Select (1-{len(acc_df)}): ").strip()
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(acc_df):
                            acc_id = int(acc_df.iloc[idx]["acc_id"])
                            print(f"  Using acc_id={acc_id}")
                            return acc_id
                    except ValueError:
                        pass
                    print("  Invalid choice. Try again.")

        raise RuntimeError(
            "No live trading account found. Make sure your MooMoo account "
            "is set up for options trading and that OpenD is configured correctly."
        )


def unlock_for_real_trading(trade_ctx, password):
    """
    Unlock the trade context for live trading.
    This is ONLY needed for TrdEnv.REAL — paper trading doesn't need it.

    Args:
        trade_ctx: An OpenSecTradeContext
        password:  Your MooMoo trading password

    Raises:
        PermissionError if the unlock fails.
    """
    if not password:
        raise PermissionError(
            "Trade unlock password is empty. Set TRADE_UNLOCK_PWD in config.py."
        )

    ret, data = trade_ctx.unlock_trade(password=password)
    if ret != RET_OK:
        raise PermissionError(f"Failed to unlock trading: {data}")

    print("  Trade unlocked for live trading.")


def verify_connection(quote_ctx, trade_ctx):
    """
    Quick sanity check that both contexts are working.

    Tests:
    1. Can we get the account list? (trade context works)
    2. Can we get global market state? (quote context works)

    Returns:
        True if both succeed, raises an exception otherwise.
    """
    # Test trade context
    ret, data = trade_ctx.get_acc_list()
    if ret != RET_OK:
        raise MoomooConnectionError(f"Trade context check failed: {data}")

    # Test quote context
    ret, data = quote_ctx.get_global_state()
    if ret != RET_OK:
        raise MoomooConnectionError(f"Quote context check failed: {data}")

    return True


def is_us_market_open():
    """
    Check if the US stock market is currently in regular trading hours.

    US market hours: 9:30 AM - 4:00 PM Eastern Time (ET), Monday-Friday.

    Note: This is a simple check. It doesn't account for holidays.
    Paper trading also only works during market hours for US options.

    Returns:
        True if currently within regular trading hours.
    """
    # US Eastern Time is UTC-5 (or UTC-4 during DST)
    # This is an approximation; for production use a proper timezone library
    utc_now = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-5)  # EST (winter)
    et_now = utc_now + et_offset

    # Check if it's a weekday (Monday=0, Friday=4)
    if et_now.weekday() > 4:
        return False

    # Check if within 9:30 AM - 4:00 PM ET
    market_open = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = et_now.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= et_now <= market_close

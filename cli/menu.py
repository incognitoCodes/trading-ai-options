"""
cli/menu.py — Main interactive menu and strategy workflow orchestration.

This is where everything comes together:
1. User picks a strategy from the menu
2. CLI prompts gather inputs (ticker, expiry, strikes)
3. Strategy builds legs from the option chain
4. Simulation shows payoff, Greeks, and chart
5. User decides to execute or cancel
6. After execution, user can set exit conditions
"""

import time
from datetime import datetime, timezone

from moomoo import TrdEnv

import config
from api.connection import MoomooConnection
from api.quotes import (
    get_expiry_dates,
    get_option_chain,
    get_stock_price,
    get_option_snapshot,
)
from api import MoomooConnectionError, MoomooAPIError
from broker.account import get_options_account, unlock_for_real_trading, verify_connection
from broker.executor import execute_strategy
from broker.exit_manager import (
    ConditionType,
    ExitCondition,
    TrackedPosition,
    add_position,
    add_exit_condition,
    get_open_positions,
    get_all_positions,
    close_position,
    remove_exit_condition,
    toggle_exit_condition,
    evaluate_conditions,
    build_closing_legs,
    estimate_current_pnl,
    update_peak_pnl,
)
from strategies.iron_condor import IronCondor
from strategies.vertical_spread import BullPutSpread, BearCallSpread
from strategies.iron_butterfly import IronButterfly
from strategies.naked_option import NakedOption
from simulation.payoff import combined_payoff, generate_price_range, find_breakevens
from simulation.greeks import aggregate_greeks
from simulation.chart import draw_payoff_diagram
from simulation.summary import print_strategy_summary
from logging_utils.trade_logger import print_trade_log
from cli.prompts import (
    prompt_ticker,
    prompt_expiry,
    prompt_strike,
    prompt_qty,
    prompt_side,
    prompt_option_type,
    prompt_yes_no,
    prompt_float,
    prompt_int,
    prompt_choice,
)
from cli.display import (
    print_banner,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_separator,
    print_menu,
    print_exit_conditions,
    format_currency,
)


# ---------------------------------------------------------------------------
# Trading environment resolution
# ---------------------------------------------------------------------------

def _resolve_trd_env():
    """Convert config string to moomoo TrdEnv enum."""
    if config.TRADING_ENV == "REAL":
        return TrdEnv.REAL
    return TrdEnv.SIMULATE


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

MAIN_MENU_OPTIONS = [
    ("iron_condor",      "Iron Condor (4-leg, range-bound)"),
    ("bull_put",         "Bull Put Spread (2-leg, bullish credit)"),
    ("bear_call",        "Bear Call Spread (2-leg, bearish credit)"),
    ("iron_butterfly",   "Iron Butterfly (4-leg, pin to strike)"),
    ("naked_option",     "Naked Option (single leg buy/sell)"),
    ("manage_exits",     "Manage Exit Conditions"),
    ("monitor",          "Monitor Open Positions"),
    ("positions",        "View All Positions"),
    ("trade_log",        "View Trade Log"),
    ("quit",             "Quit"),
]


def main_menu():
    """Run the main interactive menu loop."""
    print_banner()

    conn = None
    acc_id = None
    trd_env = _resolve_trd_env()

    while True:
        print_menu("MAIN MENU", MAIN_MENU_OPTIONS)
        choice = input("  Select (1-10): ").strip()

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(MAIN_MENU_OPTIONS):
                action = MAIN_MENU_OPTIONS[idx][0]
            else:
                print_error("Invalid choice.")
                continue
        except ValueError:
            print_error("Enter a number.")
            continue

        if action == "quit":
            if conn:
                conn.close()
            print_info("Goodbye.")
            break

        # Trade log doesn't need a connection
        if action == "trade_log":
            print_trade_log()
            continue

        # Position viewing doesn't need a connection
        if action == "positions":
            _view_positions()
            continue

        # Everything else needs a connection
        if conn is None:
            try:
                print_info("Connecting to OpenD...")
                conn = MoomooConnection()
                conn.connect()
                verify_connection(conn.quote_ctx, conn.trade_ctx)
                acc_id = get_options_account(conn.trade_ctx, trd_env)
                print_success(f"Connected. Account: {acc_id}")

                # Unlock for real trading if needed
                if trd_env == TrdEnv.REAL:
                    unlock_for_real_trading(conn.trade_ctx, config.TRADE_UNLOCK_PWD)

            except (MoomooConnectionError, MoomooAPIError) as e:
                print_error(f"Connection failed: {e}")
                conn = None
                continue
            except Exception as e:
                print_error(f"Unexpected error: {e}")
                conn = None
                continue

        # Route to the right flow
        try:
            if action == "iron_condor":
                _iron_condor_flow(conn, acc_id, trd_env)
            elif action == "bull_put":
                _bull_put_flow(conn, acc_id, trd_env)
            elif action == "bear_call":
                _bear_call_flow(conn, acc_id, trd_env)
            elif action == "iron_butterfly":
                _iron_butterfly_flow(conn, acc_id, trd_env)
            elif action == "naked_option":
                _naked_option_flow(conn, acc_id, trd_env)
            elif action == "manage_exits":
                _manage_exits_flow(conn)
            elif action == "monitor":
                _monitor_positions_flow(conn)
        except KeyboardInterrupt:
            print("\n  Interrupted.")
        except MoomooAPIError as e:
            print_error(f"API error: {e}")
        except Exception as e:
            print_error(f"Error: {e}")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_chain_and_price(conn, ticker, expiry):
    """Fetch option chain and current stock price. Returns (chain_df, stock_price)."""
    print_info(f"Fetching option chain for {ticker} at {expiry}...")
    chain_df = get_option_chain(conn.quote_ctx, ticker, expiry)

    # Enrich chain with snapshot prices if last_price is 0 (market closed)
    chain_df = _enrich_chain_prices(conn, chain_df)

    # Try to get stock price; fall back to estimating from option chain
    try:
        stock_price = get_stock_price(conn.quote_ctx, ticker)
    except MoomooAPIError:
        print_warning("Could not fetch stock price (no LV1 quote rights).")
        print_info("Estimating from option chain (midpoint of ATM strikes)...")
        stock_price = _estimate_price_from_chain(chain_df)

    print_success(f"Got {len(chain_df)} contracts. {ticker} at ${stock_price:.2f}")
    return chain_df, stock_price


def _enrich_chain_prices(conn, chain_df):
    """
    Fill in last_price from snapshot data when it's 0 (e.g. market closed).

    Tries in order:
    1. last_price (already in chain — use if > 0)
    2. prev_close_price from snapshot
    3. (bid + ask) / 2 midpoint from snapshot
    """
    if "last_price" not in chain_df.columns:
        return chain_df

    # Check how many contracts have 0 or NaN prices
    zero_mask = (chain_df["last_price"].isna()) | (chain_df["last_price"] == 0)
    zero_count = zero_mask.sum()

    if zero_count == 0:
        return chain_df  # All prices are fine

    print_info(f"  {zero_count}/{len(chain_df)} contracts have no last_price (market closed?).")
    print_info("  Fetching snapshot prices (prev close / bid-ask)...")

    # Get snapshot for contracts with missing prices (batch in groups of 200)
    codes_needing_price = chain_df.loc[zero_mask, "code"].tolist()

    batch_size = 200
    for i in range(0, len(codes_needing_price), batch_size):
        batch = codes_needing_price[i:i + batch_size]
        try:
            snapshot_df = get_option_snapshot(conn.quote_ctx, batch)
            if snapshot_df.empty:
                continue

            for _, snap_row in snapshot_df.iterrows():
                code = snap_row["code"]
                # Try prev_close_price first, then bid-ask midpoint
                price = 0
                if "prev_close_price" in snap_row and snap_row.get("prev_close_price", 0):
                    price = float(snap_row["prev_close_price"])

                if price == 0:
                    bid = float(snap_row.get("bid_price", 0) or 0)
                    ask = float(snap_row.get("ask_price", 0) or 0)
                    if bid > 0 and ask > 0:
                        price = (bid + ask) / 2
                    elif bid > 0:
                        price = bid
                    elif ask > 0:
                        price = ask

                if price == 0 and "last_price" in snap_row:
                    price = float(snap_row.get("last_price", 0) or 0)

                if price > 0:
                    chain_df.loc[chain_df["code"] == code, "last_price"] = price

        except MoomooAPIError as e:
            print_warning(f"  Snapshot batch failed: {e}")
            continue

    # Report how many we fixed
    still_zero = ((chain_df["last_price"].isna()) | (chain_df["last_price"] == 0)).sum()
    fixed = zero_count - still_zero
    if fixed > 0:
        print_success(f"  Filled {fixed} prices from snapshot data.")
    if still_zero > 0:
        print_warning(f"  {still_zero} contracts still have no price data.")

    return chain_df


def _estimate_price_from_chain(chain_df):
    """
    Estimate the underlying price from the option chain.

    Strategy: find the strike where the call and put have the closest
    premiums (put-call parity tells us that's near the current price).
    Falls back to median strike if that fails.
    """
    try:
        # Find all columns — print them for debugging on first run
        cols = list(chain_df.columns)
        print_info(f"  Chain columns: {cols}")

        # Find the premium column (varies by API version)
        price_col = None
        for candidate in ["last_price", "option_price", "close", "cur_price"]:
            if candidate in cols:
                price_col = candidate
                break

        if price_col is None:
            # Can't find premium column — use median strike
            return float(chain_df["strike_price"].median())

        calls = chain_df[chain_df["option_type"].str.upper() == "CALL"]
        puts = chain_df[chain_df["option_type"].str.upper() == "PUT"]

        if calls.empty or puts.empty:
            return float(chain_df["strike_price"].median())

        # For each strike that has both a call and put, find where premiums are closest
        call_prices = calls.set_index("strike_price")[price_col]
        put_prices = puts.set_index("strike_price")[price_col]
        common_strikes = call_prices.index.intersection(put_prices.index)

        if common_strikes.empty:
            return float(chain_df["strike_price"].median())

        best_strike = None
        best_diff = float("inf")
        for strike in common_strikes:
            c = float(call_prices.loc[strike] if not hasattr(call_prices.loc[strike], '__len__') else call_prices.loc[strike].iloc[0])
            p = float(put_prices.loc[strike] if not hasattr(put_prices.loc[strike], '__len__') else put_prices.loc[strike].iloc[0])
            diff = abs(c - p)
            if diff < best_diff:
                best_diff = diff
                best_strike = strike

        return float(best_strike) if best_strike else float(chain_df["strike_price"].median())

    except Exception as e:
        print_warning(f"  Price estimation error: {e}")
        return float(chain_df["strike_price"].median())


def _simulate_and_show(strategy_result, chain_df, stock_price):
    """Run simulation, print summary, show chart. Returns greeks dict."""
    # Greeks
    greeks = aggregate_greeks(strategy_result.legs, chain_df)

    # Print summary
    print_strategy_summary(strategy_result, greeks)

    # Payoff chart
    prices = generate_price_range(stock_price)
    payoff = combined_payoff(strategy_result.legs, prices)
    breakevens = find_breakevens(payoff, prices)

    if prompt_yes_no("Show payoff chart?", default="y"):
        draw_payoff_diagram(
            strategy_name=strategy_result.name,
            underlying=strategy_result.underlying,
            current_price=stock_price,
            prices=prices,
            payoff=payoff,
            breakevens=strategy_result.breakevens or breakevens,
            max_profit=strategy_result.max_profit,
            max_loss=strategy_result.max_loss,
        )

    return greeks


def _execute_and_track(conn, strategy_result, acc_id, trd_env):
    """Execute the strategy and optionally track for exit conditions."""
    dry_run = prompt_yes_no("Dry run (simulate without placing orders)?", default="y")

    results = execute_strategy(
        conn=conn,
        legs=strategy_result.legs,
        acc_id=acc_id,
        trd_env=trd_env,
        strategy_name=strategy_result.name,
        underlying=strategy_result.underlying,
        expiry=strategy_result.expiry,
        dry_run=dry_run,
    )

    if not results:
        return

    # Track position for exit management
    if prompt_yes_no("Track this position for exit conditions?", default="y"):
        auto = prompt_yes_no("Enable auto-close (no confirmation needed)?", default="n")
        pos = add_position(strategy_result, auto_close=auto)
        print_success(f"Position tracked: {pos.position_id}")

        # Offer to add exit conditions right away
        if prompt_yes_no("Add exit conditions now?", default="y"):
            _add_exit_conditions_interactive(pos.position_id)


# ---------------------------------------------------------------------------
# Strategy flows
# ---------------------------------------------------------------------------

def _iron_condor_flow(conn, acc_id, trd_env):
    """Interactive flow for building and executing an Iron Condor."""
    print_header("IRON CONDOR")

    ticker = prompt_ticker()
    expiry_dates = get_expiry_dates(conn.quote_ctx, ticker)
    expiry = prompt_expiry(expiry_dates)
    if not expiry:
        return

    chain_df, stock_price = _get_chain_and_price(conn, ticker, expiry)

    put_strikes = sorted(
        chain_df[chain_df["option_type"].str.upper() == "PUT"]["strike_price"].unique()
    )
    call_strikes = sorted(
        chain_df[chain_df["option_type"].str.upper() == "CALL"]["strike_price"].unique()
    )

    print_info(f"\n  Current price: ${stock_price:.2f}")
    print_info("  Select 4 strikes: long_put < short_put < short_call < long_call")

    long_put = prompt_strike(chain_df, "PUT", "long put (lowest, protection)")
    short_put = prompt_strike(chain_df, "PUT", "short put (sell, above long put)")
    short_call = prompt_strike(chain_df, "CALL", "short call (sell, above stock)")
    long_call = prompt_strike(chain_df, "CALL", "long call (highest, protection)")
    qty = prompt_qty()

    strikes = {
        "long_put": long_put,
        "short_put": short_put,
        "short_call": short_call,
        "long_call": long_call,
    }

    strategy = IronCondor()
    legs = strategy.build_legs(ticker, expiry, strikes, qty, chain_df)
    result = strategy.compute_metrics(legs, ticker, expiry)

    _simulate_and_show(result, chain_df, stock_price)

    if prompt_yes_no("Proceed to execution?"):
        _execute_and_track(conn, result, acc_id, trd_env)


def _bull_put_flow(conn, acc_id, trd_env):
    """Interactive flow for a Bull Put Spread."""
    print_header("BULL PUT SPREAD")

    ticker = prompt_ticker()
    expiry_dates = get_expiry_dates(conn.quote_ctx, ticker)
    expiry = prompt_expiry(expiry_dates)
    if not expiry:
        return

    chain_df, stock_price = _get_chain_and_price(conn, ticker, expiry)

    print_info(f"\n  Current price: ${stock_price:.2f}")
    print_info("  Select 2 put strikes: long_put < short_put (both below stock price)")

    short_put = prompt_strike(chain_df, "PUT", "short put (higher, sell here)")
    long_put = prompt_strike(chain_df, "PUT", "long put (lower, protection)")
    qty = prompt_qty()

    strikes = {"short_put": short_put, "long_put": long_put}

    strategy = BullPutSpread()
    legs = strategy.build_legs(ticker, expiry, strikes, qty, chain_df)
    result = strategy.compute_metrics(legs, ticker, expiry)

    _simulate_and_show(result, chain_df, stock_price)

    if prompt_yes_no("Proceed to execution?"):
        _execute_and_track(conn, result, acc_id, trd_env)


def _bear_call_flow(conn, acc_id, trd_env):
    """Interactive flow for a Bear Call Spread."""
    print_header("BEAR CALL SPREAD")

    ticker = prompt_ticker()
    expiry_dates = get_expiry_dates(conn.quote_ctx, ticker)
    expiry = prompt_expiry(expiry_dates)
    if not expiry:
        return

    chain_df, stock_price = _get_chain_and_price(conn, ticker, expiry)

    print_info(f"\n  Current price: ${stock_price:.2f}")
    print_info("  Select 2 call strikes: short_call < long_call (both above stock price)")

    short_call = prompt_strike(chain_df, "CALL", "short call (lower, sell here)")
    long_call = prompt_strike(chain_df, "CALL", "long call (higher, protection)")
    qty = prompt_qty()

    strikes = {"short_call": short_call, "long_call": long_call}

    strategy = BearCallSpread()
    legs = strategy.build_legs(ticker, expiry, strikes, qty, chain_df)
    result = strategy.compute_metrics(legs, ticker, expiry)

    _simulate_and_show(result, chain_df, stock_price)

    if prompt_yes_no("Proceed to execution?"):
        _execute_and_track(conn, result, acc_id, trd_env)


def _iron_butterfly_flow(conn, acc_id, trd_env):
    """Interactive flow for an Iron Butterfly."""
    print_header("IRON BUTTERFLY")

    ticker = prompt_ticker()
    expiry_dates = get_expiry_dates(conn.quote_ctx, ticker)
    expiry = prompt_expiry(expiry_dates)
    if not expiry:
        return

    chain_df, stock_price = _get_chain_and_price(conn, ticker, expiry)

    print_info(f"\n  Current price: ${stock_price:.2f}")
    print_info("  Select 3 strikes: long_put < short_strike (ATM) < long_call")

    short_strike = prompt_strike(chain_df, "PUT", "short strike (ATM, sell both put+call)")
    long_put = prompt_strike(chain_df, "PUT", "long put (lower, protection)")
    long_call = prompt_strike(chain_df, "CALL", "long call (higher, protection)")
    qty = prompt_qty()

    strikes = {
        "long_put": long_put,
        "short_strike": short_strike,
        "long_call": long_call,
    }

    strategy = IronButterfly()
    legs = strategy.build_legs(ticker, expiry, strikes, qty, chain_df)
    result = strategy.compute_metrics(legs, ticker, expiry)

    _simulate_and_show(result, chain_df, stock_price)

    if prompt_yes_no("Proceed to execution?"):
        _execute_and_track(conn, result, acc_id, trd_env)


def _naked_option_flow(conn, acc_id, trd_env):
    """Interactive flow for a single-leg (naked) option."""
    print_header("NAKED OPTION (Single Leg)")

    ticker = prompt_ticker()
    expiry_dates = get_expiry_dates(conn.quote_ctx, ticker)
    expiry = prompt_expiry(expiry_dates)
    if not expiry:
        return

    chain_df, stock_price = _get_chain_and_price(conn, ticker, expiry)

    print_info(f"\n  Current price: ${stock_price:.2f}")

    side = prompt_side()
    option_type = prompt_option_type()
    strike = prompt_strike(chain_df, option_type, f"{side.lower()} {option_type.lower()} strike")
    qty = prompt_qty()

    strikes = {"strike": strike, "option_type": option_type, "side": side}

    strategy = NakedOption()
    legs = strategy.build_legs(ticker, expiry, strikes, qty, chain_df)
    result = strategy.compute_metrics(legs, ticker, expiry)

    _simulate_and_show(result, chain_df, stock_price)

    if prompt_yes_no("Proceed to execution?"):
        _execute_and_track(conn, result, acc_id, trd_env)


# ---------------------------------------------------------------------------
# Exit condition management
# ---------------------------------------------------------------------------

def _manage_exits_flow(conn):
    """Manage exit conditions on tracked positions."""
    print_header("MANAGE EXIT CONDITIONS")

    positions = get_open_positions()
    if not positions:
        print_info("No open positions to manage.")
        return

    # Show positions
    print("\n  Open Positions:")
    for i, pos in enumerate(positions, 1):
        n_conds = len(pos.exit_conditions)
        print(
            f"    {i}. {pos.strategy:<20} {pos.underlying:<6} "
            f"Exp: {pos.expiry}  Credit: ${pos.net_credit:.2f}  "
            f"Exit rules: {n_conds}"
        )

    choice = input(f"\n  Select position (1-{len(positions)}): ").strip()
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(positions)):
            print_error("Invalid selection.")
            return
    except ValueError:
        print_error("Enter a number.")
        return

    pos = positions[idx]
    _position_exit_menu(pos)


def _position_exit_menu(pos):
    """Sub-menu for managing exit conditions on a specific position."""
    while True:
        print_header(f"Exit Conditions: {pos.strategy} {pos.underlying}")
        print_exit_conditions(pos.exit_conditions)

        options = [
            ("add", "Add exit condition"),
            ("remove", "Remove exit condition"),
            ("toggle", "Toggle condition active/inactive"),
            ("close", "Manually close this position"),
            ("back", "Back to main menu"),
        ]
        print_menu("Actions", options)
        action = input("  Select (1-5): ").strip()

        try:
            idx = int(action) - 1
            if not (0 <= idx < len(options)):
                continue
            action = options[idx][0]
        except ValueError:
            continue

        if action == "back":
            break
        elif action == "add":
            _add_exit_conditions_interactive(pos.position_id)
            # Reload
            for p in get_open_positions():
                if p.position_id == pos.position_id:
                    pos = p
                    break
        elif action == "remove":
            if not pos.exit_conditions:
                print_info("No conditions to remove.")
                continue
            idx = prompt_int("Condition number to remove", minimum=1) - 1
            if remove_exit_condition(pos.position_id, idx):
                print_success("Condition removed.")
                for p in get_open_positions():
                    if p.position_id == pos.position_id:
                        pos = p
                        break
            else:
                print_error("Could not remove condition.")
        elif action == "toggle":
            if not pos.exit_conditions:
                print_info("No conditions to toggle.")
                continue
            idx = prompt_int("Condition number to toggle", minimum=1) - 1
            if toggle_exit_condition(pos.position_id, idx):
                print_success("Condition toggled.")
                for p in get_open_positions():
                    if p.position_id == pos.position_id:
                        pos = p
                        break
            else:
                print_error("Could not toggle condition.")
        elif action == "close":
            if prompt_yes_no("Are you sure you want to mark this position as closed?"):
                close_position(pos.position_id, "Manual close from menu")
                print_success("Position marked as closed.")
                break


def _add_exit_conditions_interactive(position_id):
    """Interactive prompt to add exit conditions to a position."""
    condition_types = [
        (ConditionType.PROFIT_TARGET_PCT, "Profit target (% of max profit)"),
        (ConditionType.STOP_LOSS_PCT, "Stop loss (% of max loss)"),
        (ConditionType.STOP_LOSS_MULTIPLE, "Stop loss (multiple of credit received)"),
        (ConditionType.DTE_THRESHOLD, "Days to expiry threshold"),
        (ConditionType.UNDERLYING_ABOVE, "Close if underlying above price"),
        (ConditionType.UNDERLYING_BELOW, "Close if underlying below price"),
        (ConditionType.DELTA_THRESHOLD, "Close if |delta| exceeds threshold"),
        (ConditionType.TRAILING_STOP_PCT, "Trailing stop (% drop from peak P&L)"),
    ]

    while True:
        print("\n  Add Exit Condition:")
        for i, (_, label) in enumerate(condition_types, 1):
            print(f"    {i}. {label}")
        print(f"    {len(condition_types) + 1}. Done (back)")

        choice = input(f"\n  Select (1-{len(condition_types) + 1}): ").strip()
        try:
            idx = int(choice) - 1
            if idx == len(condition_types):
                break
            if not (0 <= idx < len(condition_types)):
                continue
        except ValueError:
            continue

        ct, label = condition_types[idx]

        # Prompt for the threshold value
        if ct == ConditionType.PROFIT_TARGET_PCT:
            value = prompt_float("Target profit % (e.g. 50 for 50%)", default=50)
        elif ct == ConditionType.STOP_LOSS_PCT:
            value = prompt_float("Max loss % before closing (e.g. 100 for full max loss)", default=100)
        elif ct == ConditionType.STOP_LOSS_MULTIPLE:
            value = prompt_float("Loss multiple of credit (e.g. 2.0 for 2x credit)", default=2.0)
        elif ct == ConditionType.DTE_THRESHOLD:
            value = prompt_float("Close at how many DTE (e.g. 21)", default=21)
        elif ct == ConditionType.UNDERLYING_ABOVE:
            value = prompt_float("Close if underlying above $")
        elif ct == ConditionType.UNDERLYING_BELOW:
            value = prompt_float("Close if underlying below $")
        elif ct == ConditionType.DELTA_THRESHOLD:
            value = prompt_float("Close if |net delta| exceeds (e.g. 0.30)", default=0.30)
        elif ct == ConditionType.TRAILING_STOP_PCT:
            value = prompt_float("% drop from peak profit to trigger (e.g. 25)", default=25)
        else:
            continue

        cond = ExitCondition(
            condition_type=ct,
            value=value,
            active=True,
            label=label,
        )

        if add_exit_condition(position_id, cond):
            print_success(f"Added: {cond.description()}")
        else:
            print_error("Position not found. Could not add condition.")
            break


# ---------------------------------------------------------------------------
# Position monitoring
# ---------------------------------------------------------------------------

def _monitor_positions_flow(conn):
    """
    Monitor all open positions, check exit conditions, and alert on triggers.
    Runs one check cycle (not a background loop).
    """
    print_header("POSITION MONITOR")

    positions = get_open_positions()
    if not positions:
        print_info("No open positions to monitor.")
        return

    print_info(f"Checking {len(positions)} open position(s)...\n")

    for pos in positions:
        print_separator()
        print_info(
            f"{pos.strategy} | {pos.underlying} | Exp: {pos.expiry} | "
            f"Credit: ${pos.net_credit:.2f}"
        )

        # Get current prices for all legs
        codes = [leg["code"] for leg in pos.legs]
        try:
            snapshot_df = get_option_snapshot(conn.quote_ctx, codes)
            current_price = get_stock_price(conn.quote_ctx, pos.underlying)
        except MoomooAPIError as e:
            print_error(f"  Could not fetch prices: {e}")
            continue

        # Build price map: code → mid price
        price_map = {}
        for _, row in snapshot_df.iterrows():
            bid = row.get("bid_price", 0) or 0
            ask = row.get("ask_price", 0) or 0
            mid = (bid + ask) / 2 if (bid and ask) else row.get("last_price", 0)
            price_map[row["code"]] = float(mid)

        # Estimate current P&L
        current_pnl = estimate_current_pnl(pos, price_map)
        update_peak_pnl(pos.position_id, current_pnl)

        pnl_color = "+" if current_pnl >= 0 else ""
        print_info(f"  Current P&L: {pnl_color}${current_pnl:,.2f}")
        print_info(f"  Underlying: ${current_price:.2f}")
        print_info(f"  Peak P&L: ${pos.peak_pnl:,.2f}")

        # Check exit conditions
        if not pos.exit_conditions:
            print_info("  No exit conditions set.")
            continue

        triggered = evaluate_conditions(pos, current_price, current_pnl)

        if not triggered:
            print_info(f"  {len(pos.exit_conditions)} conditions checked — none triggered.")
        else:
            print_warning(f"  {len(triggered)} EXIT CONDITION(S) TRIGGERED:")
            for cond, reason in triggered:
                print_warning(f"    -> {reason}")

            # Show closing legs
            closing_legs = build_closing_legs(pos)
            print_info("\n  Closing legs needed:")
            for cl in closing_legs:
                current = price_map.get(cl["code"], 0)
                print_info(
                    f"    {cl['side']:<4} {cl['qty']}x {cl['option_type']:<4} "
                    f"${cl['strike']:<8.2f} (current: ${current:.2f})  {cl['label']}"
                )

            if pos.auto_close:
                print_warning("  AUTO-CLOSE enabled — would execute closing orders.")
            else:
                if prompt_yes_no("Execute closing orders now?"):
                    print_info("  To close, place the opposite trades manually or through the menu.")
                    print_info("  (Automated closing execution coming in a future update.)")
                    if prompt_yes_no("Mark position as closed?"):
                        close_position(pos.position_id, triggered[0][1])
                        print_success("Position marked as closed.")

    print_separator()
    print_info("Monitor check complete.")


def _view_positions():
    """View all tracked positions (open and closed)."""
    print_header("ALL POSITIONS")

    positions = get_all_positions()
    if not positions:
        print_info("No positions tracked yet.")
        return

    open_count = sum(1 for p in positions if not p.closed)
    closed_count = sum(1 for p in positions if p.closed)

    print_info(f"  Total: {len(positions)} ({open_count} open, {closed_count} closed)\n")

    for pos in positions:
        status = "CLOSED" if pos.closed else "OPEN"
        n_legs = len(pos.legs)
        n_conds = len(pos.exit_conditions)
        print(
            f"  [{status:<6}] {pos.strategy:<20} {pos.underlying:<6} "
            f"Exp: {pos.expiry}  Legs: {n_legs}  Credit: ${pos.net_credit:.2f}  "
            f"Exit rules: {n_conds}"
        )
        if pos.closed:
            print(f"           Reason: {pos.close_reason}")

    print()

"""
cli/display.py — Console formatting helpers for the trading CLI.

Provides reusable formatting for headers, banners, tables,
and status messages used across all CLI flows.
"""

import config


def print_banner():
    """Print the application startup banner."""
    env = config.TRADING_ENV
    env_label = "PAPER TRADING" if env == "SIMULATE" else "*** LIVE TRADING ***"

    print()
    print("  " + "=" * 55)
    print("  MooMoo Options Trading System")
    print(f"  Mode: {env_label}")
    print(f"  Gateway: {config.OPEND_HOST}:{config.OPEND_PORT}")
    print("  " + "=" * 55)
    print()


def print_header(title):
    """Print a section header."""
    print()
    print("  " + "-" * 50)
    print(f"  {title}")
    print("  " + "-" * 50)


def print_success(message):
    """Print a success message."""
    print(f"  [OK] {message}")


def print_error(message):
    """Print an error message."""
    print(f"  [ERROR] {message}")


def print_warning(message):
    """Print a warning message."""
    print(f"  [WARN] {message}")


def print_info(message):
    """Print an info message."""
    print(f"  {message}")


def print_separator():
    """Print a thin separator line."""
    print("  " + "-" * 50)


def print_menu(title, options):
    """
    Print a numbered menu.

    Args:
        title:   Menu title string
        options: List of (key, label) tuples. key is what's returned,
                 label is what's displayed.
    """
    print()
    print(f"  {title}")
    print()
    for i, (_, label) in enumerate(options, 1):
        print(f"    {i}. {label}")
    print()


def print_position_table(positions):
    """
    Print a table of active positions.

    Args:
        positions: List of dicts with keys:
                   strategy, underlying, expiry, legs, net_credit,
                   open_time, exit_conditions
    """
    if not positions:
        print("  No active positions.")
        return

    print()
    print("  Active Positions:")
    print("  " + "=" * 70)

    for i, pos in enumerate(positions, 1):
        n_legs = len(pos.get("legs", []))
        n_conds = len(pos.get("exit_conditions", []))
        print(
            f"  {i:>3}. {pos['strategy']:<20} {pos['underlying']:<6} "
            f"Exp: {pos['expiry']}  Legs: {n_legs}  "
            f"Exit rules: {n_conds}"
        )

    print("  " + "=" * 70)
    print()


def print_exit_conditions(conditions):
    """
    Print the exit conditions for a position.

    Args:
        conditions: List of ExitCondition objects
    """
    if not conditions:
        print("  No exit conditions set.")
        return

    print()
    print("  Exit Conditions:")
    print("  " + "-" * 55)

    for i, cond in enumerate(conditions, 1):
        status = "ACTIVE" if cond.active else "INACTIVE"
        print(f"    {i}. [{status}] {cond.description()}")

    print("  " + "-" * 55)
    print()


def format_currency(amount):
    """Format a number as currency string."""
    if amount >= 0:
        return f"${amount:,.2f}"
    return f"-${abs(amount):,.2f}"


def format_pct(value):
    """Format a decimal as percentage string."""
    return f"{value * 100:.1f}%"

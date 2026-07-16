"""
cli/prompts.py — Input helpers for interactive strategy setup.

Provides validated prompts for:
- Ticker symbol entry
- Expiry date selection (from available dates)
- Strike price selection (from the option chain)
- Quantity input
- Yes/No confirmations
"""


def prompt_ticker():
    """
    Ask the user for a stock ticker symbol.

    Returns:
        Uppercase ticker string, e.g. "AAPL"
    """
    while True:
        ticker = input("\n  Enter ticker symbol (e.g. AAPL): ").strip().upper()
        if ticker and ticker.isalpha():
            return ticker
        print("  Invalid ticker. Use letters only (e.g. AAPL, TSLA, SPY).")


def prompt_expiry(expiry_dates):
    """
    Show available expiry dates and let the user pick one.

    Args:
        expiry_dates: List of date strings from api/quotes.py

    Returns:
        Selected date string, e.g. "2025-06-18"
    """
    if not expiry_dates:
        print("  No expiry dates available.")
        return None

    print("\n  Available expiry dates:")
    for i, d in enumerate(expiry_dates, 1):
        print(f"    {i:>3}. {d}")

    while True:
        choice = input(f"\n  Select expiry (1-{len(expiry_dates)}): ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(expiry_dates):
                return expiry_dates[idx]
        except ValueError:
            pass
        print(f"  Enter a number between 1 and {len(expiry_dates)}.")


def prompt_strike(chain_df, option_type, label="strike"):
    """
    Show available strikes for a given option type and let the user pick one.

    Args:
        chain_df:    Option chain DataFrame
        option_type: "CALL" or "PUT"
        label:       Display label, e.g. "short put strike"

    Returns:
        Selected strike price as float
    """
    filtered = chain_df[chain_df["option_type"].str.upper() == option_type.upper()]
    strikes = sorted(filtered["strike_price"].unique())

    if not strikes:
        print(f"  No {option_type} strikes available.")
        return None

    print(f"\n  Available {option_type} strikes:")
    cols = 5
    for i in range(0, len(strikes), cols):
        row = strikes[i:i + cols]
        line = "    " + "  ".join(f"{j + i + 1:>3}. ${s:<8.2f}" for j, s in enumerate(row))
        print(line)

    while True:
        choice = input(f"\n  Select {label} (1-{len(strikes)}, or type price): ").strip()
        try:
            # Try as index first
            idx = int(choice) - 1
            if 0 <= idx < len(strikes):
                return strikes[idx]
        except ValueError:
            pass

        # Try as direct price
        try:
            price = float(choice.replace("$", ""))
            if price in strikes:
                return price
            # Find nearest
            nearest = min(strikes, key=lambda s: abs(s - price))
            yn = input(f"  ${price:.2f} not available. Use nearest ${nearest:.2f}? (y/n): ").strip()
            if yn.lower() == "y":
                return nearest
        except ValueError:
            pass

        print(f"  Enter a number 1-{len(strikes)} or a valid strike price.")


def prompt_strike_price(available_strikes, label="strike"):
    """
    Prompt for a strike from a pre-filtered list of available strikes.

    Args:
        available_strikes: Sorted list of strike prices
        label:             Display label

    Returns:
        Selected strike price as float
    """
    if not available_strikes:
        print(f"  No strikes available for {label}.")
        return None

    print(f"\n  Available strikes for {label}:")
    cols = 5
    for i in range(0, len(available_strikes), cols):
        row = available_strikes[i:i + cols]
        line = "    " + "  ".join(f"{j + i + 1:>3}. ${s:<8.2f}" for j, s in enumerate(row))
        print(line)

    while True:
        choice = input(f"\n  Select {label} (1-{len(available_strikes)}, or type price): ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(available_strikes):
                return available_strikes[idx]
        except ValueError:
            pass

        try:
            price = float(choice.replace("$", ""))
            if price in available_strikes:
                return price
            nearest = min(available_strikes, key=lambda s: abs(s - price))
            yn = input(f"  ${price:.2f} not listed. Use ${nearest:.2f}? (y/n): ").strip()
            if yn.lower() == "y":
                return nearest
        except ValueError:
            pass

        print(f"  Enter a number 1-{len(available_strikes)} or a valid price.")


def prompt_qty():
    """
    Ask the user how many contracts per leg.

    Returns:
        Positive integer
    """
    while True:
        qty = input("\n  Number of contracts per leg [1]: ").strip()
        if not qty:
            return 1
        try:
            n = int(qty)
            if n > 0:
                return n
        except ValueError:
            pass
        print("  Enter a positive integer.")


def prompt_side():
    """
    Ask the user for BUY or SELL direction.

    Returns:
        "BUY" or "SELL"
    """
    while True:
        side = input("\n  Side — (B)uy or (S)ell: ").strip().upper()
        if side in ("B", "BUY"):
            return "BUY"
        if side in ("S", "SELL"):
            return "SELL"
        print("  Enter B (buy) or S (sell).")


def prompt_option_type():
    """
    Ask the user for CALL or PUT.

    Returns:
        "CALL" or "PUT"
    """
    while True:
        ot = input("\n  Option type — (C)all or (P)ut: ").strip().upper()
        if ot in ("C", "CALL"):
            return "CALL"
        if ot in ("P", "PUT"):
            return "PUT"
        print("  Enter C (call) or P (put).")


def prompt_yes_no(message, default="n"):
    """
    Simple yes/no prompt.

    Args:
        message: The question to ask
        default: "y" or "n" — used when user just presses Enter

    Returns:
        True for yes, False for no
    """
    hint = "(Y/n)" if default == "y" else "(y/N)"
    response = input(f"  {message} {hint}: ").strip().lower()
    if not response:
        return default == "y"
    return response in ("y", "yes")


def prompt_float(message, default=None):
    """
    Prompt for a float value.

    Args:
        message: The prompt text
        default: Default value if user presses Enter

    Returns:
        Float value
    """
    default_hint = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"  {message}{default_hint}: ").strip()
        if not val and default is not None:
            return float(default)
        try:
            return float(val)
        except ValueError:
            print("  Enter a valid number.")


def prompt_int(message, default=None, minimum=0):
    """
    Prompt for an integer value.

    Args:
        message: The prompt text
        default: Default value if user presses Enter
        minimum: Minimum allowed value

    Returns:
        Integer value
    """
    default_hint = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"  {message}{default_hint}: ").strip()
        if not val and default is not None:
            return int(default)
        try:
            n = int(val)
            if n >= minimum:
                return n
            print(f"  Value must be >= {minimum}.")
        except ValueError:
            print("  Enter a valid integer.")


def prompt_choice(message, options):
    """
    Present a numbered list of options.

    Args:
        message: Header text
        options: List of (value, label) tuples

    Returns:
        The selected value
    """
    print(f"\n  {message}")
    for i, (_, label) in enumerate(options, 1):
        print(f"    {i}. {label}")

    while True:
        choice = input(f"\n  Select (1-{len(options)}): ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(f"  Enter a number between 1 and {len(options)}.")

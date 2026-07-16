"""
strategies/utils.py — Shared utilities for all strategy modules.

The _find_contract helper is used by every strategy to look up
contract codes and premiums from the option chain.
"""


def find_contract(chain_df, strike, option_type):
    """
    Find a contract code in the chain DataFrame matching strike and type.

    If the premium (last_price) is 0 or missing (market closed), prompts
    the user to enter it manually.

    Args:
        chain_df:    Option chain DataFrame
        strike:      Strike price, e.g. 185.0
        option_type: "CALL" or "PUT"

    Returns:
        (code, premium) tuple

    Raises:
        ValueError if no matching contract exists.
    """
    mask = (
        (chain_df["strike_price"] == strike)
        & (chain_df["option_type"].str.upper() == option_type.upper())
    )
    matches = chain_df[mask]
    if matches.empty:
        raise ValueError(
            f"No {option_type} contract found at strike ${strike:.2f}. "
            f"Available strikes: {sorted(chain_df['strike_price'].unique())}"
        )

    row = matches.iloc[0]
    code = row["code"]

    # Try multiple price columns
    premium = 0
    for col in ["last_price", "prev_close_price", "close"]:
        val = row.get(col, 0)
        if val is not None and val == val and val > 0:  # not None, not NaN, > 0
            premium = float(val)
            break

    # Try bid/ask midpoint
    if premium == 0:
        bid = row.get("bid_price", 0)
        ask = row.get("ask_price", 0)
        bid = float(bid) if (bid is not None and bid == bid) else 0
        ask = float(ask) if (ask is not None and ask == ask) else 0
        if bid > 0 and ask > 0:
            premium = (bid + ask) / 2
        elif bid > 0:
            premium = bid
        elif ask > 0:
            premium = ask

    # If still 0, ask user for manual input
    if premium == 0:
        print(f"    No price data for {option_type} ${strike:.2f} ({code}).")
        print(f"    Market may be closed. Enter the premium manually.")
        print(f"    (Check your MooMoo app or options chain for the last price.)")
        while True:
            val = input(f"    Premium for {option_type} ${strike:.2f} (or 0 to skip): ").strip()
            try:
                premium = float(val.replace("$", ""))
                break
            except ValueError:
                print("    Enter a valid number.")

    return code, float(premium)

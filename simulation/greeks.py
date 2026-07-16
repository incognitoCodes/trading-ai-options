"""
simulation/greeks.py — Aggregate Greeks across all legs of a strategy.

KEY CONCEPTS FOR BEGINNERS:
- "Greeks" measure how an option's price changes relative to various factors:
  - Delta: How much option price moves per $1 move in the stock
  - Gamma: How fast Delta itself changes (acceleration)
  - Theta: How much value the option loses per day (time decay)
  - Vega:  How much option price moves per 1% change in volatility
  - Rho:   How much option price moves per 1% change in interest rates

- When you BUY an option, you ADD its Greeks to your position.
- When you SELL an option, you SUBTRACT its Greeks from your position.
- A "delta-neutral" strategy (net delta ≈ 0) means the position doesn't
  care much if the stock moves up or down by a small amount.
"""


def aggregate_greeks(legs, chain_df):
    """
    Look up each leg's Greeks from the option chain and sum them.

    For SELL legs, the Greeks are subtracted (flipped sign).
    For BUY legs, the Greeks are added as-is.

    Args:
        legs:     list of Leg objects (from strategies/base.py)
        chain_df: DataFrame from api/quotes.py containing columns like:
                  [code, delta, gamma, theta, vega, rho, implied_volatility]

    Returns:
        dict with keys:
            net_delta, net_gamma, net_theta, net_vega, net_rho, avg_iv

        If Greeks data is not available in chain_df, returns zeros
        with a warning message.
    """
    result = {
        "net_delta": 0.0,
        "net_gamma": 0.0,
        "net_theta": 0.0,
        "net_vega": 0.0,
        "net_rho": 0.0,
        "avg_iv": 0.0,
    }

    # Check if the chain DataFrame has Greek columns
    greek_columns = ["delta", "gamma", "theta", "vega"]
    if chain_df is None:
        print("  Note: No option chain data provided. Greeks set to zero.")
        return result

    available_greeks = [col for col in greek_columns if col in chain_df.columns]
    if not available_greeks:
        print("  Note: Greeks not available in option chain data. Values set to zero.")
        return result

    iv_values = []

    for leg in legs:
        # Find this leg's contract in the chain
        match = chain_df[chain_df["code"] == leg.code]

        if match.empty:
            print(f"  Warning: Could not find Greeks for {leg.code}. Skipping.")
            continue

        row = match.iloc[0]

        # Determine sign: BUY adds Greeks, SELL subtracts them
        sign = 1 if leg.side.upper() == "BUY" else -1
        multiplier = sign * leg.qty

        # Sum each Greek
        for greek in available_greeks:
            value = row.get(greek, 0)
            if value is not None and value == value:  # Check for NaN
                result[f"net_{greek}"] += value * multiplier

        # Rho (if available)
        if "rho" in chain_df.columns:
            rho_val = row.get("rho", 0)
            if rho_val is not None and rho_val == rho_val:
                result["net_rho"] += rho_val * multiplier

        # Implied volatility (for averaging)
        if "implied_volatility" in chain_df.columns:
            iv = row.get("implied_volatility", 0)
            if iv is not None and iv == iv and iv > 0:
                iv_values.append(iv)

    # Average IV across all legs
    if iv_values:
        result["avg_iv"] = sum(iv_values) / len(iv_values)

    # Round for display
    for key in result:
        result[key] = round(result[key], 4)

    return result

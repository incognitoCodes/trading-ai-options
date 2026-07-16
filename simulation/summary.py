"""
simulation/summary.py — Formatted console output for strategy analysis.

Prints a clear, tabular summary of strategy metrics so you can
review max profit, max loss, breakevens, and Greeks before trading.
"""


def print_strategy_summary(result, greeks=None):
    """
    Print a formatted summary table for a strategy.

    Args:
        result: StrategyResult from strategies/base.py
        greeks: Optional dict with keys like "net_delta", "net_theta", etc.
                If None, the Greeks section is skipped.

    Output looks like:
    ╔══════════════════════════════════════════════════╗
    ║  IRON CONDOR — AAPL (2025-06-18)                ║
    ╠══════════════════════════════════════════════════╣
    ║  LEGS:                                          ║
    ║    BUY  1x PUT  $175.00  @ $1.20  (Long Put)    ║
    ║    SELL 1x PUT  $185.00  @ $3.50  (Short Put)   ║
    ║    SELL 1x CALL $215.00  @ $3.20  (Short Call)  ║
    ║    BUY  1x CALL $225.00  @ $1.10  (Long Call)   ║
    ╠══════════════════════════════════════════════════╣
    ║  Net Credit:     $4.40 per share ($440.00 total) ║
    ║  Max Profit:     $440.00                         ║
    ║  Max Loss:       -$560.00                        ║
    ║  Breakeven Low:  $180.60                         ║
    ║  Breakeven High: $219.40                         ║
    ╠══════════════════════════════════════════════════╣
    ║  GREEKS (net position):                          ║
    ║    Delta:  0.002   Theta: +0.082                 ║
    ║    Gamma: -0.015   Vega:  -0.210                 ║
    ╚══════════════════════════════════════════════════╝
    """
    width = 55
    line = "═" * width

    print()
    print(f"  ╔{line}╗")
    print(f"  ║  {result.name.upper()} — {result.underlying} ({result.expiry})".ljust(width + 2) + " ║")
    print(f"  ╠{line}╣")

    # --- Legs ---
    print(f"  ║  {'LEGS:':<{width - 1}}║")
    for leg in result.legs:
        side_str = leg.side.ljust(4)
        leg_line = (
            f"    {side_str} {leg.qty}x {leg.option_type:<4} "
            f"${leg.strike:<8.2f} @ ${leg.premium:<6.2f} ({leg.label})"
        )
        print(f"  ║  {leg_line:<{width - 1}}║")

    print(f"  ╠{line}╣")

    # --- Metrics ---
    net_per_share = abs(result.net_credit)
    credit_or_debit = "Credit" if result.net_credit >= 0 else "Debit"
    total = abs(result.net_credit) * result.legs[0].qty * 100 if result.legs else 0

    metrics = [
        f"Net {credit_or_debit}:     ${net_per_share:.2f} per share (${total:,.2f} total)",
        f"Max Profit:     ${result.max_profit:,.2f}",
        f"Max Loss:       ${result.max_loss:,.2f}",
    ]
    for i, be in enumerate(result.breakevens):
        label = "Breakeven" if len(result.breakevens) == 1 else f"Breakeven {'Low' if i == 0 else 'High'}"
        metrics.append(f"{label}:  ${be:,.2f}")

    for m in metrics:
        print(f"  ║  {m:<{width - 1}}║")

    # --- Greeks (optional) ---
    if greeks:
        print(f"  ╠{line}╣")
        print(f"  ║  {'GREEKS (net position):':<{width - 1}}║")
        g_line1 = (
            f"    Delta: {greeks.get('net_delta', 0):>7.3f}   "
            f"Theta: {greeks.get('net_theta', 0):>+7.3f}"
        )
        g_line2 = (
            f"    Gamma: {greeks.get('net_gamma', 0):>7.3f}   "
            f"Vega:  {greeks.get('net_vega', 0):>+7.3f}"
        )
        print(f"  ║  {g_line1:<{width - 1}}║")
        print(f"  ║  {g_line2:<{width - 1}}║")
        if "avg_iv" in greeks:
            iv_line = f"    Avg IV: {greeks['avg_iv']:.1f}%"
            print(f"  ║  {iv_line:<{width - 1}}║")

    print(f"  ╚{line}╝")
    print()


def print_legs_table(legs):
    """
    Print a simple table of legs for confirmation before placing orders.

    Args:
        legs: list of Leg objects
    """
    print()
    print("  ┌──────┬─────┬──────┬──────────┬──────────┬────────────────┐")
    print("  │ Side │ Qty │ Type │  Strike  │ Premium  │ Label          │")
    print("  ├──────┼─────┼──────┼──────────┼──────────┼────────────────┤")
    for leg in legs:
        print(
            f"  │ {leg.side:<4} │ {leg.qty:>3} │ {leg.option_type:<4} "
            f"│ ${leg.strike:>7.2f} │ ${leg.premium:>7.2f} │ {leg.label:<14} │"
        )
    print("  └──────┴─────┴──────┴──────────┴──────────┴────────────────┘")
    print()

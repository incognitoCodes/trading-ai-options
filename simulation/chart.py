"""
simulation/chart.py — Payoff diagram visualization using matplotlib.

Draws a clear, color-coded chart showing:
- The P&L curve across different stock prices at expiry
- Profit zone (green), loss zone (red)
- Breakeven points, max profit/loss lines, current stock price
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — saves charts to file
import matplotlib.pyplot as plt


def draw_payoff_diagram(
    strategy_name,
    underlying,
    current_price,
    prices,
    payoff,
    breakevens,
    max_profit,
    max_loss,
    save_path=None,
):
    """
    Draw a professional payoff diagram for an options strategy.

    Args:
        strategy_name: e.g. "Iron Condor"
        underlying:    e.g. "AAPL"
        current_price: Current stock price (shown as vertical line)
        prices:        numpy array of stock prices (x-axis)
        payoff:        numpy array of P&L values (y-axis)
        breakevens:    list of breakeven prices
        max_profit:    Maximum profit value
        max_loss:      Maximum loss value
        save_path:     If given, save chart to this file path (e.g. "payoff.png")
                       If None, display interactively

    The chart shows:
        - Blue line:      P&L curve
        - Green shading:  Profitable zone (P&L > 0)
        - Red shading:    Loss zone (P&L < 0)
        - Orange dashed:  Current stock price
        - Purple dashed:  Breakeven points
        - Gray dashed:    Zero P&L line
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    # --- P&L curve ---
    ax.plot(prices, payoff, color="#2196F3", linewidth=2.5, label="P&L at Expiry")

    # --- Shade profit zone (green) and loss zone (red) ---
    ax.fill_between(
        prices, payoff, 0,
        where=(payoff >= 0),
        color="#4CAF50", alpha=0.15, label="Profit Zone"
    )
    ax.fill_between(
        prices, payoff, 0,
        where=(payoff < 0),
        color="#F44336", alpha=0.15, label="Loss Zone"
    )

    # --- Zero line ---
    ax.axhline(y=0, color="gray", linestyle="--", linewidth=0.8)

    # --- Current stock price (vertical orange line) ---
    ax.axvline(
        x=current_price, color="#FF9800", linestyle="--", linewidth=1.5,
        label=f"Current Price: ${current_price:.2f}"
    )

    # --- Breakeven points (vertical purple lines) ---
    for i, be in enumerate(breakevens):
        label = f"Breakeven: ${be:.2f}" if i == 0 else f"${be:.2f}"
        ax.axvline(x=be, color="#9C27B0", linestyle=":", linewidth=1.2, label=label)

    # --- Max profit line ---
    ax.axhline(
        y=max_profit, color="#4CAF50", linestyle=":", linewidth=1,
        alpha=0.7, label=f"Max Profit: ${max_profit:,.2f}"
    )

    # --- Max loss line ---
    ax.axhline(
        y=max_loss, color="#F44336", linestyle=":", linewidth=1,
        alpha=0.7, label=f"Max Loss: ${max_loss:,.2f}"
    )

    # --- Labels and formatting ---
    ax.set_title(
        f"{strategy_name} — {underlying} Payoff at Expiry",
        fontsize=14, fontweight="bold", pad=15
    )
    ax.set_xlabel("Stock Price at Expiry ($)", fontsize=11)
    ax.set_ylabel("Profit / Loss ($)", fontsize=11)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax.grid(True, alpha=0.3)

    # Add thousands separator to y-axis
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    plt.tight_layout()

    # Always save to file, then open it with the system viewer
    if not save_path:
        save_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "payoff_chart.png"
        )

    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Chart saved to: {save_path}")

    # Try to open the chart with the default image viewer
    try:
        import subprocess
        subprocess.Popen(["open", save_path])  # macOS
        print("  (Chart opened in Preview.)")
    except Exception:
        print("  Open the file above to view the chart.")

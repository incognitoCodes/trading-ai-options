"""
logging_utils/trade_logger.py — Logs every trade to a CSV file.

Every order placed (or dry-run simulated) gets a row in trades.csv.
This gives you a complete history of everything the system has done.

The CSV file is created automatically on the first trade.
You can open it in Excel, Google Sheets, or any spreadsheet program.
"""

import csv
import os
from datetime import datetime, timezone
import config


# Column headers for the CSV file
COLUMNS = [
    "timestamp",      # When the order was placed (UTC)
    "strategy",       # e.g. "Iron Condor"
    "underlying",     # e.g. "AAPL"
    "expiry",         # e.g. "2025-06-18"
    "leg_label",      # e.g. "Short Put"
    "code",           # Contract code
    "side",           # "BUY" or "SELL"
    "strike",         # Strike price
    "option_type",    # "CALL" or "PUT"
    "qty",            # Number of contracts
    "premium",        # Limit price (per share)
    "order_id",       # Order ID from the API (or "DRY_RUN")
    "status",         # "SUBMITTED" or "DRY_RUN"
    "trd_env",        # "SIMULATE" or "REAL"
]


def _ensure_csv_exists():
    """Create the CSV file with headers if it doesn't exist yet."""
    path = config.TRADE_LOG_PATH

    # Create directory if needed
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

    # Create file with headers if it doesn't exist
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)


def log_trade(strategy, underlying, expiry, leg, order_result, trd_env):
    """
    Append one row to the trade log CSV.

    Args:
        strategy:     Strategy name, e.g. "Iron Condor"
        underlying:   Ticker, e.g. "AAPL"
        expiry:       Expiration date, e.g. "2025-06-18"
        leg:          Leg object from strategies/base.py
        order_result: Dict from api/orders.py (has order_id, status)
        trd_env:      "SIMULATE" or "REAL"
    """
    _ensure_csv_exists()

    timestamp = datetime.now(timezone.utc).isoformat()

    row = [
        timestamp,
        strategy,
        underlying,
        expiry,
        leg.label,
        leg.code,
        leg.side,
        leg.strike,
        leg.option_type,
        leg.qty,
        leg.premium,
        order_result.get("order_id", "UNKNOWN"),
        order_result.get("status", "UNKNOWN"),
        trd_env,
    ]

    with open(config.TRADE_LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def read_trade_log():
    """
    Read the trade log CSV into a pandas DataFrame.

    Returns:
        DataFrame with all logged trades, or an empty DataFrame
        if no trades have been logged yet.
    """
    import pandas as pd

    path = config.TRADE_LOG_PATH

    if not os.path.exists(path):
        print("  No trades logged yet.")
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(path)
    return df


def print_trade_log():
    """
    Print the trade log in a readable format to the console.
    """
    df = read_trade_log()

    if df.empty:
        print("  No trades logged yet.")
        return

    print(f"\n  Trade Log ({len(df)} entries):")
    print("  " + "=" * 70)

    for _, row in df.iterrows():
        print(
            f"  {row['timestamp'][:19]}  {row['strategy']:<18} "
            f"{row['side']:<4} {row['qty']}x {row['option_type']:<4} "
            f"${float(row['strike']):>8.2f}  [{row['status']}] ({row['trd_env']})"
        )

    print("  " + "=" * 70)
    print(f"  Full log at: {config.TRADE_LOG_PATH}")

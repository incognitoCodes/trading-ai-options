"""
config.py — Central configuration for the MooMoo Options Trading System.

All tuneable settings live here. Other modules import from this file
so nothing is hard-coded elsewhere.

IMPORTANT: TRADING_ENV defaults to SIMULATE (paper trading).
To switch to live trading, you must:
  1. Change TRADING_ENV to "REAL" below
  2. Set MOOMOO_TRADE_PWD environment variable (or create a .env file)
  3. Type "LIVE MODE" when prompted in the CLI

SECURITY:
  The trading password is loaded from environment variable MOOMOO_TRADE_PWD.
  Set it in your shell:   export MOOMOO_TRADE_PWD="your_password"
  Or create a .env file in the project root (never commit this file).
"""

import os

# ---------------------------------------------------------------------------
# OpenD Gateway Settings
# ---------------------------------------------------------------------------
# OpenD is MooMoo's local gateway that sits between your code and their servers.
# You must download and run OpenD before using this system.
# Default: runs on localhost port 11111
OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111

# ---------------------------------------------------------------------------
# Trading Environment
# ---------------------------------------------------------------------------
# TrdEnv.SIMULATE = paper trading (safe, no real money)
# TrdEnv.REAL     = live trading (real money!)
#
# We import these lazily so config.py works even if moomoo-api isn't installed yet.
# The actual enum values are: SIMULATE = 0, REAL = 1
# Loaded from the TRADING_ENV environment variable. Defaults to SIMULATE
# (paper trading) so a fresh checkout can never place a real-money order by
# accident. Set TRADING_ENV=REAL in your .env for live trading.
TRADING_ENV = os.environ.get("TRADING_ENV", "SIMULATE").upper()

# Which market to trade options on (US options are fully supported from SG)
TRADING_MARKET = "US"

# ---------------------------------------------------------------------------
# Account Settings
# ---------------------------------------------------------------------------
# Trade unlock password — only needed for REAL trading.
# Loaded from environment variable MOOMOO_TRADE_PWD (or .env file).
# NEVER hardcode your password here.
TRADE_UNLOCK_PWD = os.environ.get("MOOMOO_TRADE_PWD", "")

# ---------------------------------------------------------------------------
# Trade Logging
# ---------------------------------------------------------------------------
TRADE_LOG_DIR = os.path.join(os.path.dirname(__file__), "logging_utils")
TRADE_LOG_PATH = os.path.join(TRADE_LOG_DIR, "trades.csv")

# ---------------------------------------------------------------------------
# Payoff Diagram Settings
# ---------------------------------------------------------------------------
PAYOFF_STEPS = 500       # Number of price points on the x-axis
PAYOFF_RANGE_PCT = 0.20  # Chart shows +/- 20% around current price

# ---------------------------------------------------------------------------
# API Rate Limiting
# ---------------------------------------------------------------------------
# MooMoo allows ~15 requests per 30 seconds. This adds a small pause between calls.
API_SLEEP_SECONDS = 0.1

# ---------------------------------------------------------------------------
# Options Contract Multiplier
# ---------------------------------------------------------------------------
# US options: 1 contract = 100 shares
CONTRACT_MULTIPLIER = 100

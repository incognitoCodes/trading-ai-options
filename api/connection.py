"""
api/connection.py — Manages connections to the MooMoo OpenD gateway.

WHAT IS OpenD?
OpenD is a local program (gateway) that you must download and run on your
computer. It sits between your Python code and MooMoo's servers:

    Your Python Script  →  OpenD (localhost:11111)  →  MooMoo Servers

Think of OpenD as a translator: your code speaks to OpenD using the
moomoo-api SDK, and OpenD handles the secure communication with MooMoo.

HOW TO SET UP OpenD:
1. Download OpenD from: https://www.moomoo.com/download
   (Look for "MooMoo OpenD" in the developer tools section)
2. Install and launch it
3. Log in with your MooMoo account credentials
4. It will run in the background on port 11111 by default

This module creates two "contexts" (connections):
- QuoteContext: for fetching market data (prices, option chains)
- TradeContext: for placing orders
"""

import time
from moomoo import (
    OpenQuoteContext,
    OpenSecTradeContext,
    RET_OK,
    TrdEnv,
    TrdMarket,
    SecurityFirm,
)
from api import MoomooConnectionError
import config


class MoomooConnection:
    """
    Holds one QuoteContext and one TradeContext as a single bundle.

    Usage as a context manager (recommended):
        with MoomooConnection() as conn:
            data = conn.quote_ctx.get_market_snapshot(...)
            conn.trade_ctx.place_order(...)
        # Both contexts are automatically closed when the 'with' block ends

    Or manually:
        conn = MoomooConnection()
        conn.connect()
        # ... do work ...
        conn.close()
    """

    def __init__(self, host=None, port=None):
        self.host = host or config.OPEND_HOST
        self.port = port or config.OPEND_PORT
        self._quote_ctx = None
        self._trade_ctx = None

    def connect(self):
        """
        Open both quote and trade connections to OpenD.
        Raises MoomooConnectionError if OpenD is not running.

        The trade context uses filter_trdmarket=US and tries to detect
        the correct security firm (FUTU Inc for US, FUTU Securities for HK, etc.)
        """
        try:
            self._quote_ctx = OpenQuoteContext(host=self.host, port=self.port)

            # Try to detect the right SecurityFirm for this account.
            # FUTUINC = US, FUTUSECURITIES = HK/SG, FUTUAU = AU
            security_firm = SecurityFirm.FUTUINC
            try:
                self._trade_ctx = OpenSecTradeContext(
                    host=self.host,
                    port=self.port,
                    filter_trdmarket=TrdMarket.US,
                    security_firm=security_firm,
                )
            except Exception:
                # Fall back without security_firm filter
                self._trade_ctx = OpenSecTradeContext(
                    host=self.host, port=self.port,
                )
        except Exception as e:
            self.close()
            raise MoomooConnectionError(
                f"Could not connect to OpenD at {self.host}:{self.port}. "
                f"Make sure OpenD is running.\n"
                f"Error: {e}"
            )

    @property
    def quote_ctx(self):
        """Access the market data context."""
        if self._quote_ctx is None:
            raise MoomooConnectionError("Not connected. Call connect() first.")
        return self._quote_ctx

    @property
    def trade_ctx(self):
        """Access the trading context."""
        if self._trade_ctx is None:
            raise MoomooConnectionError("Not connected. Call connect() first.")
        return self._trade_ctx

    def close(self):
        """Close both connections cleanly."""
        if self._quote_ctx is not None:
            try:
                self._quote_ctx.close()
            except Exception:
                pass
            self._quote_ctx = None

        if self._trade_ctx is not None:
            try:
                self._trade_ctx.close()
            except Exception:
                pass
            self._trade_ctx = None

    def __enter__(self):
        """Support 'with MoomooConnection() as conn:' syntax."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatically close connections when exiting 'with' block."""
        self.close()
        return False  # Don't suppress exceptions


def create_connection():
    """
    Factory function that creates and connects a MoomooConnection
    using settings from config.py.

    Returns:
        A connected MoomooConnection instance.
        Remember to call .close() when done, or use it as a context manager.

    Raises:
        MoomooConnectionError if OpenD is not reachable.
    """
    conn = MoomooConnection(
        host=config.OPEND_HOST,
        port=config.OPEND_PORT,
    )
    conn.connect()
    return conn

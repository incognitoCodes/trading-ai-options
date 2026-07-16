"""
tests/test_connection.py — Integration test for MooMoo OpenD connection.

This test REQUIRES OpenD to be running locally on the configured port.
Skip if OpenD is not available:
    python -m pytest tests/test_connection.py -v

The test will be skipped gracefully if OpenD is not reachable.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config

try:
    import moomoo  # noqa: F401
    HAS_MOOMOO = True
except ImportError:
    HAS_MOOMOO = False

pytestmark = pytest.mark.skipif(not HAS_MOOMOO, reason="moomoo-api not installed")

if HAS_MOOMOO:
    from api.connection import MoomooConnection
    from api import MoomooConnectionError


def _opend_available():
    """Check if OpenD is reachable by attempting a socket connection."""
    if not HAS_MOOMOO:
        return False
    import socket
    try:
        sock = socket.create_connection(
            (config.OPEND_HOST, config.OPEND_PORT), timeout=2
        )
        sock.close()
        return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


_opend_up = _opend_available()
requires_opend = pytest.mark.skipif(
    not _opend_up,
    reason=f"OpenD not running at {config.OPEND_HOST}:{config.OPEND_PORT}"
)


@requires_opend
class TestConnection:
    """Integration tests that require a live OpenD gateway."""

    def test_connect_and_close(self):
        """Can we connect and cleanly disconnect?"""
        conn = MoomooConnection()
        conn.connect()
        assert conn._quote_ctx is not None
        assert conn._trade_ctx is not None
        conn.close()
        assert conn._quote_ctx is None
        assert conn._trade_ctx is None

    def test_context_manager(self):
        """Test the 'with' statement usage."""
        with MoomooConnection() as conn:
            assert conn._quote_ctx is not None
            assert conn._trade_ctx is not None
        # After exiting, contexts should be closed
        assert conn._quote_ctx is None

    def test_verify_connection(self):
        """Test that verify_connection succeeds with live OpenD."""
        from broker.account import verify_connection
        with MoomooConnection() as conn:
            assert verify_connection(conn.quote_ctx, conn.trade_ctx) is True

    def test_get_account_list(self):
        """Test that we can fetch the account list."""
        from broker.account import get_acc_list
        with MoomooConnection() as conn:
            df = get_acc_list(conn.trade_ctx)
            assert not df.empty
            assert "acc_id" in df.columns

    def test_get_stock_price(self):
        """Test fetching a stock price."""
        from api.quotes import get_stock_price
        with MoomooConnection() as conn:
            price = get_stock_price(conn.quote_ctx, "AAPL")
            assert isinstance(price, float)
            assert price > 0


class TestConnectionErrors:
    """Test connection error handling (no OpenD needed)."""

    def test_connect_bad_port(self):
        """Connecting to a wrong port should raise MoomooConnectionError."""
        conn = MoomooConnection(host="127.0.0.1", port=99999)
        with pytest.raises((MoomooConnectionError, Exception)):
            conn.connect()

    def test_quote_ctx_before_connect(self):
        """Accessing quote_ctx before connect() should raise."""
        conn = MoomooConnection()
        with pytest.raises(MoomooConnectionError):
            _ = conn.quote_ctx

    def test_trade_ctx_before_connect(self):
        """Accessing trade_ctx before connect() should raise."""
        conn = MoomooConnection()
        with pytest.raises(MoomooConnectionError):
            _ = conn.trade_ctx

    def test_double_close(self):
        """Calling close() twice should not raise."""
        conn = MoomooConnection()
        conn.close()
        conn.close()  # Should not raise

"""
api/ — Low-level wrappers around the MooMoo (moomoo-api) SDK.

This package handles:
  - Connecting to the OpenD gateway (connection.py)
  - Fetching market data and option chains (quotes.py)
  - Placing individual option orders (orders.py)
"""


class MoomooConnectionError(Exception):
    """Raised when we can't connect to OpenD or the connection drops."""
    pass


class MoomooAPIError(Exception):
    """Raised when an API call returns a non-OK status."""
    pass


class ContractNotFoundError(Exception):
    """Raised when a strike/expiry combination doesn't exist in the option chain."""
    pass

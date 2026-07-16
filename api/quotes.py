"""
api/quotes.py — Market data functions for fetching option chains and prices.

All functions take a QuoteContext (from connection.py) and return
clean Python objects or DataFrames.

KEY CONCEPTS:
- "Option chain" = the list of all available option contracts for a stock,
  organized by strike price and expiry date.
- Each contract has a unique "code" (e.g. "US.AAPL250618C185000") that
  you use when placing orders.
"""

import time
import pandas as pd
from moomoo import (
    RET_OK,
    OptionType,
    OptionCondType,
    SubType,
)
from api import MoomooAPIError, ContractNotFoundError
import config


def get_expiry_dates(quote_ctx, ticker):
    """
    Get all available option expiration dates for a stock.

    Args:
        quote_ctx: An OpenQuoteContext from connection.py
        ticker:    Stock symbol with market prefix, e.g. "US.AAPL"

    Returns:
        Sorted list of date strings in "YYYY-MM-DD" format.
        Example: ["2025-03-21", "2025-04-17", "2025-06-20", ...]

    Raises:
        MoomooAPIError if the API call fails.
    """
    # Add "US." prefix if not already present
    if not ticker.startswith("US."):
        ticker = f"US.{ticker}"

    ret, data = quote_ctx.get_option_expiration_date(code=ticker)

    if ret != RET_OK:
        raise MoomooAPIError(
            f"Failed to get expiry dates for {ticker}: {data}"
        )

    # The API returns a DataFrame with a 'strike_time' column
    dates = sorted(data["strike_time"].tolist())
    return dates


def get_option_chain(
    quote_ctx,
    ticker,
    expiry_date,
    option_type=None,
    delta_min=None,
    delta_max=None,
):
    """
    Fetch the option chain for a stock at a specific expiry date.

    Args:
        quote_ctx:   An OpenQuoteContext
        ticker:      e.g. "US.AAPL" or just "AAPL"
        expiry_date: e.g. "2025-06-18"
        option_type: Optional filter: "CALL", "PUT", or None for both
        delta_min:   Optional minimum delta filter (e.g. 0.2)
        delta_max:   Optional maximum delta filter (e.g. 0.8)

    Returns:
        pandas DataFrame with columns including:
        - code: Contract code for placing orders
        - name: Contract name
        - strike_price: Strike price
        - option_type: "CALL" or "PUT"
        - last_price: Last traded price (premium)
        - volume: Trading volume
        - open_interest: Open interest
        - delta, gamma, theta, vega: Greeks (if available)
        - implied_volatility: IV (if available)

    Raises:
        MoomooAPIError if the API call fails.
    """
    if not ticker.startswith("US."):
        ticker = f"US.{ticker}"

    # Build optional Greek filter
    data_filter = None
    if delta_min is not None or delta_max is not None:
        from moomoo import OptionDataFilter
        data_filter = OptionDataFilter()
        if delta_min is not None:
            data_filter.delta_min = delta_min
        if delta_max is not None:
            data_filter.delta_max = delta_max

    # Map option_type string to SDK enum
    opt_type_enum = OptionType.ALL
    if option_type:
        if option_type.upper() == "CALL":
            opt_type_enum = OptionType.CALL
        elif option_type.upper() == "PUT":
            opt_type_enum = OptionType.PUT

    time.sleep(config.API_SLEEP_SECONDS)

    ret, data = quote_ctx.get_option_chain(
        code=ticker,
        start=expiry_date,
        end=expiry_date,
        option_type=opt_type_enum,
        option_cond_type=OptionCondType.ALL,
        data_filter=data_filter,
    )

    if ret != RET_OK:
        raise MoomooAPIError(
            f"Failed to get option chain for {ticker} at {expiry_date}: {data}"
        )

    return data


def get_option_snapshot(quote_ctx, codes):
    """
    Get a real-time price snapshot for specific option contracts.

    Useful for getting the current bid/ask/last price to set limit order prices.

    Args:
        quote_ctx: An OpenQuoteContext
        codes:     List of contract codes, e.g. ["US.AAPL250618C185000"]

    Returns:
        DataFrame with columns: code, last_price, bid_price, ask_price, volume

    Raises:
        MoomooAPIError if the API call fails.
    """
    if not codes:
        return pd.DataFrame()

    time.sleep(config.API_SLEEP_SECONDS)

    ret, data = quote_ctx.get_market_snapshot(codes)

    if ret != RET_OK:
        raise MoomooAPIError(f"Failed to get snapshot for {codes}: {data}")

    return data


def find_contract_by_strike(chain_df, strike, option_type):
    """
    Search the option chain for a contract matching a specific strike and type.

    Args:
        chain_df:    DataFrame from get_option_chain()
        strike:      Strike price, e.g. 185.0
        option_type: "CALL" or "PUT"

    Returns:
        The contract code string, e.g. "US.AAPL250618C185000"

    Raises:
        ContractNotFoundError if no matching contract exists.
    """
    mask = (
        (chain_df["strike_price"] == strike)
        & (chain_df["option_type"].str.upper() == option_type.upper())
    )
    matches = chain_df[mask]

    if matches.empty:
        available = sorted(chain_df["strike_price"].unique())
        raise ContractNotFoundError(
            f"No {option_type} contract at strike ${strike:.2f}.\n"
            f"Available strikes: {available}"
        )

    return matches.iloc[0]["code"]


def get_stock_price(quote_ctx, ticker):
    """
    Get the current price of a stock.

    Args:
        quote_ctx: An OpenQuoteContext
        ticker:    e.g. "US.AAPL" or "AAPL"

    Returns:
        Current stock price as a float.
    """
    if not ticker.startswith("US."):
        ticker = f"US.{ticker}"

    time.sleep(config.API_SLEEP_SECONDS)
    ret, data = quote_ctx.get_market_snapshot([ticker])

    if ret != RET_OK:
        raise MoomooAPIError(f"Failed to get price for {ticker}: {data}")

    if data.empty:
        raise MoomooAPIError(f"No data returned for {ticker}")

    return float(data.iloc[0]["last_price"])

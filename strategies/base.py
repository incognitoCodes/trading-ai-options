"""
strategies/base.py — Core data structures and abstract base class for all strategies.

KEY CONCEPTS FOR BEGINNERS:
- A "leg" is one option contract in a multi-leg strategy.
  For example, an Iron Condor has 4 legs (2 puts + 2 calls).
- A "strategy result" bundles all the legs together with computed metrics
  like max profit, max loss, and breakeven prices.
- Every strategy inherits from BaseStrategy and must implement two methods:
  build_legs() and compute_metrics().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Leg:
    """
    Represents one option contract in a multi-leg strategy.

    Example: Selling a $185 put expiring 2025-06-18 on AAPL:
        Leg(
            code="US.AAPL250618P185000",
            side="SELL",
            strike=185.0,
            option_type="PUT",
            expiry="2025-06-18",
            qty=1,
            premium=3.50,
            label="Short Put"
        )
    """
    code: str            # MooMoo contract code, e.g. "US.AAPL250618P185000"
    side: str            # "BUY" or "SELL"
    strike: float        # Strike price in dollars
    option_type: str     # "CALL" or "PUT"
    expiry: str          # Expiration date "YYYY-MM-DD"
    qty: int             # Number of contracts
    premium: float       # Per-share premium (price of the option)
    label: str           # Human-readable label, e.g. "Long Put Wing"


@dataclass
class StrategyResult:
    """
    The complete output of a strategy — used by simulation and execution.

    Fields:
        name:       Strategy name, e.g. "Iron Condor"
        underlying: Ticker symbol, e.g. "AAPL"
        legs:       List of Leg objects
        net_credit: Positive = you receive money upfront (credit strategy)
                    Negative = you pay money upfront (debit strategy)
        max_profit: Best-case P&L (positive number)
        max_loss:   Worst-case P&L (negative number)
        breakevens: Price(s) where P&L = 0 at expiry
    """
    name: str
    underlying: str
    expiry: str
    legs: list = field(default_factory=list)
    net_credit: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakevens: list = field(default_factory=list)


class BaseStrategy(ABC):
    """
    Abstract base class that all option strategies must implement.

    HOW IT WORKS:
    1. build_legs() takes user inputs + the option chain data and
       constructs the Leg objects (finds the right contract codes).
    2. compute_metrics() takes those legs and calculates max profit,
       max loss, and breakeven prices using options math.

    This separation means we can test the math (compute_metrics)
    without needing a live API connection.
    """

    @abstractmethod
    def build_legs(self, underlying, expiry, strikes, qty, chain_df):
        """
        Construct Leg objects from user inputs and the option chain.

        Args:
            underlying: Ticker symbol, e.g. "AAPL"
            expiry:     Expiration date string, e.g. "2025-06-18"
            strikes:    Dict of strike prices (keys vary by strategy)
            qty:        Number of contracts per leg
            chain_df:   DataFrame from api/quotes.py with columns:
                        [code, strike_price, option_type, last_price, ...]

        Returns:
            list[Leg]: The constructed legs ready for simulation/execution.
        """
        pass

    @abstractmethod
    def compute_metrics(self, legs, underlying, expiry):
        """
        Calculate max profit, max loss, and breakeven prices.

        Args:
            legs:       list[Leg] from build_legs()
            underlying: Ticker symbol
            expiry:     Expiration date

        Returns:
            StrategyResult with all fields populated.
        """
        pass

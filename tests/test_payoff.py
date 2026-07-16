"""
tests/test_payoff.py — Unit tests for simulation/payoff.py

Tests the pure-math payoff functions without any API connection.
Run with: python -m pytest tests/test_payoff.py -v
"""

import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from simulation.payoff import (
    option_payoff_at_expiry,
    combined_payoff,
    find_breakevens,
    compute_max_profit_loss,
    generate_price_range,
)
from strategies.base import Leg


class TestOptionPayoff:
    """Tests for single-leg option payoff at expiry."""

    def test_long_call_itm(self):
        """Buying a call that finishes in the money."""
        prices = np.array([210.0])
        pnl = option_payoff_at_expiry("BUY", "CALL", 200.0, 5.0, 1, prices)
        # (210 - 200 - 5) * 100 = 500
        assert pnl[0] == pytest.approx(500.0)

    def test_long_call_otm(self):
        """Buying a call that finishes out of the money."""
        prices = np.array([190.0])
        pnl = option_payoff_at_expiry("BUY", "CALL", 200.0, 5.0, 1, prices)
        # (0 - 5) * 100 = -500
        assert pnl[0] == pytest.approx(-500.0)

    def test_long_call_at_breakeven(self):
        """Call at exactly the breakeven price (strike + premium)."""
        prices = np.array([205.0])
        pnl = option_payoff_at_expiry("BUY", "CALL", 200.0, 5.0, 1, prices)
        assert pnl[0] == pytest.approx(0.0)

    def test_short_call_otm(self):
        """Selling a call that expires worthless — max profit."""
        prices = np.array([195.0])
        pnl = option_payoff_at_expiry("SELL", "CALL", 200.0, 5.0, 1, prices)
        # (5 - 0) * 100 = 500
        assert pnl[0] == pytest.approx(500.0)

    def test_short_call_itm(self):
        """Selling a call that finishes deep ITM — big loss."""
        prices = np.array([220.0])
        pnl = option_payoff_at_expiry("SELL", "CALL", 200.0, 5.0, 1, prices)
        # (5 - 20) * 100 = -1500
        assert pnl[0] == pytest.approx(-1500.0)

    def test_long_put_itm(self):
        """Buying a put that finishes in the money."""
        prices = np.array([180.0])
        pnl = option_payoff_at_expiry("BUY", "PUT", 200.0, 4.0, 1, prices)
        # (20 - 4) * 100 = 1600
        assert pnl[0] == pytest.approx(1600.0)

    def test_long_put_otm(self):
        """Buying a put that expires worthless."""
        prices = np.array([210.0])
        pnl = option_payoff_at_expiry("BUY", "PUT", 200.0, 4.0, 1, prices)
        # (0 - 4) * 100 = -400
        assert pnl[0] == pytest.approx(-400.0)

    def test_short_put_otm(self):
        """Selling a put that expires worthless — max profit."""
        prices = np.array([210.0])
        pnl = option_payoff_at_expiry("SELL", "PUT", 200.0, 4.0, 1, prices)
        # (4 - 0) * 100 = 400
        assert pnl[0] == pytest.approx(400.0)

    def test_short_put_itm(self):
        """Selling a put that finishes deep ITM."""
        prices = np.array([180.0])
        pnl = option_payoff_at_expiry("SELL", "PUT", 200.0, 4.0, 1, prices)
        # (4 - 20) * 100 = -1600
        assert pnl[0] == pytest.approx(-1600.0)

    def test_multiple_contracts(self):
        """Qty > 1 should scale linearly."""
        prices = np.array([210.0])
        pnl_1 = option_payoff_at_expiry("BUY", "CALL", 200.0, 5.0, 1, prices)
        pnl_3 = option_payoff_at_expiry("BUY", "CALL", 200.0, 5.0, 3, prices)
        assert pnl_3[0] == pytest.approx(pnl_1[0] * 3)

    def test_array_prices(self):
        """Should work across an array of prices."""
        prices = np.array([190.0, 200.0, 210.0])
        pnl = option_payoff_at_expiry("BUY", "CALL", 200.0, 5.0, 1, prices)
        assert len(pnl) == 3
        assert pnl[0] == pytest.approx(-500.0)
        assert pnl[1] == pytest.approx(-500.0)
        assert pnl[2] == pytest.approx(500.0)


class TestCombinedPayoff:
    """Tests for multi-leg combined payoff."""

    def _make_iron_condor_legs(self):
        """Create standard IC legs for testing."""
        return [
            Leg("P1", "BUY", 175.0, "PUT", "2025-06-18", 1, 1.20, "Long Put Wing"),
            Leg("P2", "SELL", 185.0, "PUT", "2025-06-18", 1, 3.50, "Short Put"),
            Leg("C1", "SELL", 215.0, "CALL", "2025-06-18", 1, 3.20, "Short Call"),
            Leg("C2", "BUY", 225.0, "CALL", "2025-06-18", 1, 1.10, "Long Call Wing"),
        ]

    def test_iron_condor_max_profit_zone(self):
        """IC should have max profit when stock is between short strikes."""
        legs = self._make_iron_condor_legs()
        prices = np.array([200.0])
        pnl = combined_payoff(legs, prices)
        # Net credit = (3.50-1.20) + (3.20-1.10) = 4.40
        # Max profit = 4.40 * 100 = 440
        assert pnl[0] == pytest.approx(440.0)

    def test_iron_condor_max_loss_low(self):
        """IC max loss when stock drops below long put."""
        legs = self._make_iron_condor_legs()
        prices = np.array([160.0])
        pnl = combined_payoff(legs, prices)
        # Wing width = 10, net credit = 4.40
        # Max loss = (10 - 4.40) * 100 = -560
        assert pnl[0] == pytest.approx(-560.0)

    def test_iron_condor_max_loss_high(self):
        """IC max loss when stock rises above long call."""
        legs = self._make_iron_condor_legs()
        prices = np.array([240.0])
        pnl = combined_payoff(legs, prices)
        assert pnl[0] == pytest.approx(-560.0)


class TestBreakevens:
    """Tests for breakeven detection."""

    def test_single_breakeven(self):
        """A simple payoff crossing zero once."""
        payoff = np.array([-100, -50, 10, 50, 100])
        prices = np.array([180, 190, 200, 210, 220])
        be = find_breakevens(payoff, prices)
        assert len(be) == 1
        assert 190 < be[0] < 200

    def test_two_breakevens(self):
        """Payoff that crosses zero twice (like an IC)."""
        payoff = np.array([-200, -50, 100, 100, -50, -200])
        prices = np.array([170, 180, 190, 210, 220, 230])
        be = find_breakevens(payoff, prices)
        assert len(be) == 2
        assert be[0] < be[1]

    def test_no_breakeven(self):
        """Payoff always positive — no breakeven."""
        payoff = np.array([10, 20, 30])
        prices = np.array([100, 110, 120])
        be = find_breakevens(payoff, prices)
        assert len(be) == 0


class TestMaxProfitLoss:
    """Tests for compute_max_profit_loss."""

    def test_basic(self):
        payoff = np.array([-500, -200, 0, 300, 440])
        max_p, max_l = compute_max_profit_loss(payoff)
        assert max_p == 440.0
        assert max_l == -500.0


class TestPriceRange:
    """Tests for generate_price_range."""

    def test_centered(self):
        prices = generate_price_range(200.0, 0.20, 100)
        assert len(prices) == 100
        assert prices[0] == pytest.approx(160.0)
        assert prices[-1] == pytest.approx(240.0)

    def test_midpoint(self):
        prices = generate_price_range(100.0, 0.10, 201)
        mid = prices[100]
        assert mid == pytest.approx(100.0, abs=0.1)

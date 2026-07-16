"""
tests/test_strategies.py — Unit tests for strategy leg construction and metrics.

Uses a mock option chain DataFrame so no API connection is needed.
Run with: python -m pytest tests/test_strategies.py -v
"""

import sys
import os
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strategies.iron_condor import IronCondor
from strategies.vertical_spread import BullPutSpread, BearCallSpread
from strategies.iron_butterfly import IronButterfly
from strategies.naked_option import NakedOption


def _mock_chain():
    """
    Create a mock option chain DataFrame resembling real API data.
    Simulates AAPL ~$200, with strikes from $170 to $230.
    """
    rows = []
    for strike in range(170, 235, 5):
        for opt_type in ["CALL", "PUT"]:
            # Simulate realistic premiums
            if opt_type == "CALL":
                intrinsic = max(200 - strike, 0)
                premium = intrinsic + 3.0 + (200 - strike) * 0.05
            else:
                intrinsic = max(strike - 200, 0)
                premium = intrinsic + 3.0 + (strike - 200) * 0.05

            premium = max(round(premium, 2), 0.50)

            rows.append({
                "code": f"US.AAPL250618{'C' if opt_type == 'CALL' else 'P'}{strike * 1000}",
                "name": f"AAPL {strike} {opt_type}",
                "strike_price": float(strike),
                "option_type": opt_type,
                "last_price": premium,
                "bid_price": round(premium - 0.10, 2),
                "ask_price": round(premium + 0.10, 2),
                "volume": 100,
                "open_interest": 500,
                "delta": 0.50 if opt_type == "CALL" else -0.50,
                "gamma": 0.02,
                "theta": -0.05,
                "vega": 0.15,
                "implied_volatility": 30.0,
            })

    return pd.DataFrame(rows)


class TestIronCondor:
    """Tests for Iron Condor strategy."""

    def test_build_legs_count(self):
        chain = _mock_chain()
        ic = IronCondor()
        strikes = {"long_put": 175.0, "short_put": 185.0, "short_call": 215.0, "long_call": 225.0}
        legs = ic.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        assert len(legs) == 4

    def test_build_legs_order(self):
        chain = _mock_chain()
        ic = IronCondor()
        strikes = {"long_put": 175.0, "short_put": 185.0, "short_call": 215.0, "long_call": 225.0}
        legs = ic.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        assert legs[0].side == "BUY"
        assert legs[0].option_type == "PUT"
        assert legs[1].side == "SELL"
        assert legs[1].option_type == "PUT"
        assert legs[2].side == "SELL"
        assert legs[2].option_type == "CALL"
        assert legs[3].side == "BUY"
        assert legs[3].option_type == "CALL"

    def test_compute_metrics(self):
        chain = _mock_chain()
        ic = IronCondor()
        strikes = {"long_put": 175.0, "short_put": 185.0, "short_call": 215.0, "long_call": 225.0}
        legs = ic.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        result = ic.compute_metrics(legs, "AAPL", "2025-06-18")
        assert result.name == "Iron Condor"
        assert result.net_credit > 0
        assert result.max_profit > 0
        assert result.max_loss < 0
        assert len(result.breakevens) == 2
        assert result.breakevens[0] < result.breakevens[1]

    def test_invalid_strike_order(self):
        chain = _mock_chain()
        ic = IronCondor()
        strikes = {"long_put": 185.0, "short_put": 175.0, "short_call": 215.0, "long_call": 225.0}
        with pytest.raises(ValueError):
            ic.build_legs("AAPL", "2025-06-18", strikes, 1, chain)

    def test_strike_not_in_chain(self):
        chain = _mock_chain()
        ic = IronCondor()
        strikes = {"long_put": 173.0, "short_put": 185.0, "short_call": 215.0, "long_call": 225.0}
        with pytest.raises(ValueError):
            ic.build_legs("AAPL", "2025-06-18", strikes, 1, chain)


class TestBullPutSpread:
    """Tests for Bull Put Spread strategy."""

    def test_build_legs_count(self):
        chain = _mock_chain()
        bps = BullPutSpread()
        strikes = {"short_put": 195.0, "long_put": 190.0}
        legs = bps.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        assert len(legs) == 2

    def test_legs_structure(self):
        chain = _mock_chain()
        bps = BullPutSpread()
        strikes = {"short_put": 195.0, "long_put": 190.0}
        legs = bps.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        assert legs[0].side == "SELL"
        assert legs[0].option_type == "PUT"
        assert legs[1].side == "BUY"
        assert legs[1].option_type == "PUT"

    def test_credit_spread(self):
        chain = _mock_chain()
        bps = BullPutSpread()
        strikes = {"short_put": 195.0, "long_put": 190.0}
        legs = bps.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        result = bps.compute_metrics(legs, "AAPL", "2025-06-18")
        # Short put premium should be higher than long put (it's closer to ATM)
        assert result.net_credit > 0
        assert result.max_profit > 0
        assert result.max_loss < 0
        assert len(result.breakevens) == 1

    def test_invalid_order(self):
        chain = _mock_chain()
        bps = BullPutSpread()
        strikes = {"short_put": 190.0, "long_put": 195.0}
        with pytest.raises(ValueError):
            bps.build_legs("AAPL", "2025-06-18", strikes, 1, chain)


class TestBearCallSpread:
    """Tests for Bear Call Spread strategy."""

    def test_build_legs_count(self):
        chain = _mock_chain()
        bcs = BearCallSpread()
        strikes = {"short_call": 205.0, "long_call": 210.0}
        legs = bcs.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        assert len(legs) == 2

    def test_credit_spread(self):
        chain = _mock_chain()
        bcs = BearCallSpread()
        strikes = {"short_call": 205.0, "long_call": 210.0}
        legs = bcs.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        result = bcs.compute_metrics(legs, "AAPL", "2025-06-18")
        assert result.net_credit > 0
        assert result.max_profit > 0
        assert result.max_loss < 0


class TestIronButterfly:
    """Tests for Iron Butterfly strategy."""

    def test_build_legs_count(self):
        chain = _mock_chain()
        ib = IronButterfly()
        strikes = {"long_put": 190.0, "short_strike": 200.0, "long_call": 210.0}
        legs = ib.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        assert len(legs) == 4

    def test_short_strikes_same(self):
        chain = _mock_chain()
        ib = IronButterfly()
        strikes = {"long_put": 190.0, "short_strike": 200.0, "long_call": 210.0}
        legs = ib.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        short_legs = [l for l in legs if l.side == "SELL"]
        assert len(short_legs) == 2
        assert short_legs[0].strike == short_legs[1].strike == 200.0

    def test_metrics(self):
        chain = _mock_chain()
        ib = IronButterfly()
        strikes = {"long_put": 190.0, "short_strike": 200.0, "long_call": 210.0}
        legs = ib.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        result = ib.compute_metrics(legs, "AAPL", "2025-06-18")
        assert result.name == "Iron Butterfly"
        assert result.net_credit > 0
        assert len(result.breakevens) == 2


class TestNakedOption:
    """Tests for Naked Option (single-leg) strategy."""

    def test_sell_put(self):
        chain = _mock_chain()
        no = NakedOption()
        strikes = {"strike": 195.0, "option_type": "PUT", "side": "SELL"}
        legs = no.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        assert len(legs) == 1
        assert legs[0].side == "SELL"
        assert legs[0].option_type == "PUT"

    def test_buy_call(self):
        chain = _mock_chain()
        no = NakedOption()
        strikes = {"strike": 210.0, "option_type": "CALL", "side": "BUY"}
        legs = no.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        assert len(legs) == 1
        assert legs[0].side == "BUY"
        assert legs[0].option_type == "CALL"

    def test_sell_put_metrics(self):
        chain = _mock_chain()
        no = NakedOption()
        strikes = {"strike": 195.0, "option_type": "PUT", "side": "SELL"}
        legs = no.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        result = no.compute_metrics(legs, "AAPL", "2025-06-18")
        assert "Sell" in result.name
        assert result.net_credit > 0
        assert result.max_profit > 0
        assert result.max_loss < 0

    def test_buy_call_metrics(self):
        chain = _mock_chain()
        no = NakedOption()
        strikes = {"strike": 210.0, "option_type": "CALL", "side": "BUY"}
        legs = no.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        result = no.compute_metrics(legs, "AAPL", "2025-06-18")
        assert "Buy" in result.name
        assert result.net_credit < 0  # Debit
        assert result.max_loss < 0

    def test_qty_scaling(self):
        chain = _mock_chain()
        no = NakedOption()
        strikes = {"strike": 195.0, "option_type": "PUT", "side": "SELL"}
        legs1 = no.build_legs("AAPL", "2025-06-18", strikes, 1, chain)
        legs3 = no.build_legs("AAPL", "2025-06-18", strikes, 3, chain)
        r1 = no.compute_metrics(legs1, "AAPL", "2025-06-18")
        r3 = no.compute_metrics(legs3, "AAPL", "2025-06-18")
        assert r3.max_profit == pytest.approx(r1.max_profit * 3)

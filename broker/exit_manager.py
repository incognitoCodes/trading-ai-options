"""
broker/exit_manager.py — Exit order conditions and monitoring for open positions.

Allows you to set automatic close conditions on your option positions:
- Profit target: close when P&L reaches X% of max profit
- Stop loss: close when loss reaches X% of max loss (or X multiple of credit)
- Days to expiry: close when N days remain before expiry
- Underlying price breach: close if stock crosses a price level
- Delta threshold: close if position delta exceeds a limit
- Time-based: close at a specific date/time
- Trailing stop: lock in profits as they grow

HOW IT WORKS:
1. After opening a position, you add one or more ExitConditions.
2. The monitor loop periodically checks all conditions.
3. When ANY condition triggers, it prepares the closing orders.
4. You confirm the close (or it auto-closes if you enabled that).

All positions and conditions are persisted to JSON so they survive restarts.
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

import config


# ---------------------------------------------------------------------------
# Exit condition types
# ---------------------------------------------------------------------------

class ConditionType(str, Enum):
    PROFIT_TARGET_PCT = "profit_target_pct"
    STOP_LOSS_PCT = "stop_loss_pct"
    STOP_LOSS_MULTIPLE = "stop_loss_multiple"
    DTE_THRESHOLD = "dte_threshold"
    UNDERLYING_ABOVE = "underlying_above"
    UNDERLYING_BELOW = "underlying_below"
    DELTA_THRESHOLD = "delta_threshold"
    TRAILING_STOP_PCT = "trailing_stop_pct"
    TIME_BASED = "time_based"


@dataclass
class ExitCondition:
    """
    A single exit rule attached to a position.

    Fields:
        condition_type: One of ConditionType values
        value:          The threshold / target value (meaning depends on type)
        active:         Whether this condition is currently enabled
        label:          Short user-facing label
    """
    condition_type: str
    value: float
    active: bool = True
    label: str = ""

    def description(self):
        """Human-readable description of this condition."""
        ct = self.condition_type
        v = self.value

        descriptions = {
            ConditionType.PROFIT_TARGET_PCT:
                f"Close at {v:.0f}% of max profit",
            ConditionType.STOP_LOSS_PCT:
                f"Close at {v:.0f}% of max loss",
            ConditionType.STOP_LOSS_MULTIPLE:
                f"Close if loss exceeds {v:.1f}x credit received",
            ConditionType.DTE_THRESHOLD:
                f"Close at {int(v)} days to expiry",
            ConditionType.UNDERLYING_ABOVE:
                f"Close if underlying rises above ${v:.2f}",
            ConditionType.UNDERLYING_BELOW:
                f"Close if underlying falls below ${v:.2f}",
            ConditionType.DELTA_THRESHOLD:
                f"Close if |net delta| exceeds {v:.2f}",
            ConditionType.TRAILING_STOP_PCT:
                f"Trailing stop: close if profit drops {v:.0f}% from peak",
            ConditionType.TIME_BASED:
                f"Close at {datetime.fromtimestamp(v).strftime('%Y-%m-%d %H:%M')}",
        }
        return descriptions.get(ct, f"{ct}: {v}")

    def to_dict(self):
        return {
            "condition_type": self.condition_type,
            "value": self.value,
            "active": self.active,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# ---------------------------------------------------------------------------
# Tracked position — an open multi-leg position with exit rules
# ---------------------------------------------------------------------------

@dataclass
class TrackedPosition:
    """
    An open option position being tracked for exit conditions.

    Fields:
        position_id:      Unique ID for this position
        strategy:         Strategy name, e.g. "Iron Condor"
        underlying:       Ticker, e.g. "AAPL"
        expiry:           Expiration date string
        legs:             List of leg dicts (code, side, strike, option_type, qty, premium, label)
        net_credit:       Net credit/debit per share
        max_profit:       Max profit in dollars
        max_loss:         Max loss in dollars
        open_time:        ISO timestamp when position was opened
        exit_conditions:  List of ExitCondition objects
        auto_close:       If True, closes automatically when triggered (no confirmation)
        peak_pnl:         Highest P&L observed (for trailing stops)
        closed:           Whether position has been closed
        close_reason:     Why the position was closed
    """
    position_id: str
    strategy: str
    underlying: str
    expiry: str
    legs: list = field(default_factory=list)
    net_credit: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    open_time: str = ""
    exit_conditions: list = field(default_factory=list)
    auto_close: bool = False
    peak_pnl: float = 0.0
    closed: bool = False
    close_reason: str = ""

    def to_dict(self):
        d = {
            "position_id": self.position_id,
            "strategy": self.strategy,
            "underlying": self.underlying,
            "expiry": self.expiry,
            "legs": self.legs,
            "net_credit": self.net_credit,
            "max_profit": self.max_profit,
            "max_loss": self.max_loss,
            "open_time": self.open_time,
            "exit_conditions": [c.to_dict() for c in self.exit_conditions],
            "auto_close": self.auto_close,
            "peak_pnl": self.peak_pnl,
            "closed": self.closed,
            "close_reason": self.close_reason,
        }
        return d

    @classmethod
    def from_dict(cls, d):
        conditions = [ExitCondition.from_dict(c) for c in d.get("exit_conditions", [])]
        pos = cls(
            position_id=d["position_id"],
            strategy=d["strategy"],
            underlying=d["underlying"],
            expiry=d["expiry"],
            legs=d.get("legs", []),
            net_credit=d.get("net_credit", 0),
            max_profit=d.get("max_profit", 0),
            max_loss=d.get("max_loss", 0),
            open_time=d.get("open_time", ""),
            exit_conditions=conditions,
            auto_close=d.get("auto_close", False),
            peak_pnl=d.get("peak_pnl", 0),
            closed=d.get("closed", False),
            close_reason=d.get("close_reason", ""),
        )
        return pos


# ---------------------------------------------------------------------------
# Position store — saves/loads positions to JSON
# ---------------------------------------------------------------------------

POSITIONS_FILE = os.path.join(os.path.dirname(config.TRADE_LOG_PATH), "positions.json")


def _load_positions():
    """Load all tracked positions from disk."""
    if not os.path.exists(POSITIONS_FILE):
        return []
    with open(POSITIONS_FILE, "r") as f:
        data = json.load(f)
    return [TrackedPosition.from_dict(d) for d in data]


def _save_positions(positions):
    """Save all tracked positions to disk."""
    directory = os.path.dirname(POSITIONS_FILE)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    with open(POSITIONS_FILE, "w") as f:
        json.dump([p.to_dict() for p in positions], f, indent=2)


def get_open_positions():
    """Get all positions that are not yet closed."""
    return [p for p in _load_positions() if not p.closed]


def get_all_positions():
    """Get all positions (open and closed)."""
    return _load_positions()


def add_position(strategy_result, auto_close=False):
    """
    Track a new position after it's been executed.

    Args:
        strategy_result: StrategyResult from a strategy's compute_metrics()
        auto_close:      If True, exit conditions trigger without confirmation

    Returns:
        The created TrackedPosition
    """
    positions = _load_positions()

    # Generate unique ID
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pid = f"{strategy_result.underlying}_{strategy_result.name.replace(' ', '_')}_{ts}"

    # Convert legs to dicts for JSON storage
    legs_data = []
    for leg in strategy_result.legs:
        legs_data.append({
            "code": leg.code,
            "side": leg.side,
            "strike": leg.strike,
            "option_type": leg.option_type,
            "qty": leg.qty,
            "premium": leg.premium,
            "label": leg.label,
            "expiry": leg.expiry,
        })

    pos = TrackedPosition(
        position_id=pid,
        strategy=strategy_result.name,
        underlying=strategy_result.underlying,
        expiry=strategy_result.expiry,
        legs=legs_data,
        net_credit=strategy_result.net_credit,
        max_profit=strategy_result.max_profit,
        max_loss=strategy_result.max_loss,
        open_time=datetime.now(timezone.utc).isoformat(),
        auto_close=auto_close,
    )

    positions.append(pos)
    _save_positions(positions)
    return pos


def add_exit_condition(position_id, condition):
    """
    Add an exit condition to a tracked position.

    Args:
        position_id: The position's ID string
        condition:    An ExitCondition object

    Returns:
        True if added successfully, False if position not found
    """
    positions = _load_positions()
    for pos in positions:
        if pos.position_id == position_id:
            pos.exit_conditions.append(condition)
            _save_positions(positions)
            return True
    return False


def remove_exit_condition(position_id, condition_index):
    """
    Remove an exit condition by index.

    Returns:
        True if removed, False if not found
    """
    positions = _load_positions()
    for pos in positions:
        if pos.position_id == position_id:
            if 0 <= condition_index < len(pos.exit_conditions):
                pos.exit_conditions.pop(condition_index)
                _save_positions(positions)
                return True
    return False


def toggle_exit_condition(position_id, condition_index):
    """Toggle an exit condition active/inactive."""
    positions = _load_positions()
    for pos in positions:
        if pos.position_id == position_id:
            if 0 <= condition_index < len(pos.exit_conditions):
                cond = pos.exit_conditions[condition_index]
                cond.active = not cond.active
                _save_positions(positions)
                return True
    return False


def close_position(position_id, reason="Manual close"):
    """Mark a position as closed."""
    positions = _load_positions()
    for pos in positions:
        if pos.position_id == position_id:
            pos.closed = True
            pos.close_reason = reason
            _save_positions(positions)
            return True
    return False


def update_peak_pnl(position_id, current_pnl):
    """Update the peak P&L for trailing stop tracking."""
    positions = _load_positions()
    for pos in positions:
        if pos.position_id == position_id:
            if current_pnl > pos.peak_pnl:
                pos.peak_pnl = current_pnl
                _save_positions(positions)
            return True
    return False


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

def evaluate_conditions(position, current_price, current_pnl, current_delta=None):
    """
    Check all active exit conditions for a position.

    Args:
        position:       TrackedPosition object
        current_price:  Current price of the underlying
        current_pnl:    Current unrealized P&L of the position
        current_delta:  Current net delta (optional, for delta-based exits)

    Returns:
        List of (condition, reason_string) tuples for conditions that triggered.
        Empty list if nothing triggered.
    """
    triggered = []

    for cond in position.exit_conditions:
        if not cond.active:
            continue

        ct = cond.condition_type

        # Profit target: close when current P&L >= X% of max profit
        if ct == ConditionType.PROFIT_TARGET_PCT:
            if position.max_profit > 0:
                pct_achieved = (current_pnl / position.max_profit) * 100
                if pct_achieved >= cond.value:
                    triggered.append((
                        cond,
                        f"Profit target reached: {pct_achieved:.1f}% of max profit "
                        f"(target: {cond.value:.0f}%)"
                    ))

        # Stop loss by percentage of max loss
        elif ct == ConditionType.STOP_LOSS_PCT:
            if position.max_loss < 0:
                pct_loss = (current_pnl / position.max_loss) * 100
                if pct_loss >= cond.value:
                    triggered.append((
                        cond,
                        f"Stop loss hit: {pct_loss:.1f}% of max loss "
                        f"(limit: {cond.value:.0f}%)"
                    ))

        # Stop loss by multiple of credit received
        elif ct == ConditionType.STOP_LOSS_MULTIPLE:
            if position.net_credit > 0:
                credit_total = position.net_credit * config.CONTRACT_MULTIPLIER
                loss_limit = credit_total * cond.value
                if current_pnl <= -loss_limit:
                    triggered.append((
                        cond,
                        f"Loss exceeds {cond.value:.1f}x credit received "
                        f"(P&L: ${current_pnl:,.2f}, limit: -${loss_limit:,.2f})"
                    ))

        # Days to expiry
        elif ct == ConditionType.DTE_THRESHOLD:
            try:
                expiry_date = datetime.strptime(position.expiry, "%Y-%m-%d")
                today = datetime.now()
                dte = (expiry_date - today).days
                if dte <= cond.value:
                    triggered.append((
                        cond,
                        f"DTE threshold: {dte} days remaining (limit: {int(cond.value)})"
                    ))
            except ValueError:
                pass

        # Underlying price above
        elif ct == ConditionType.UNDERLYING_ABOVE:
            if current_price >= cond.value:
                triggered.append((
                    cond,
                    f"Underlying at ${current_price:.2f} >= ${cond.value:.2f}"
                ))

        # Underlying price below
        elif ct == ConditionType.UNDERLYING_BELOW:
            if current_price <= cond.value:
                triggered.append((
                    cond,
                    f"Underlying at ${current_price:.2f} <= ${cond.value:.2f}"
                ))

        # Delta threshold
        elif ct == ConditionType.DELTA_THRESHOLD:
            if current_delta is not None:
                if abs(current_delta) >= cond.value:
                    triggered.append((
                        cond,
                        f"|Net delta| = {abs(current_delta):.3f} >= {cond.value:.2f}"
                    ))

        # Trailing stop
        elif ct == ConditionType.TRAILING_STOP_PCT:
            if position.peak_pnl > 0 and current_pnl > 0:
                drop_pct = ((position.peak_pnl - current_pnl) / position.peak_pnl) * 100
                if drop_pct >= cond.value:
                    triggered.append((
                        cond,
                        f"Trailing stop: profit dropped {drop_pct:.1f}% from peak "
                        f"${position.peak_pnl:,.2f} (limit: {cond.value:.0f}%)"
                    ))

        # Time-based (Unix timestamp)
        elif ct == ConditionType.TIME_BASED:
            now_ts = datetime.now(timezone.utc).timestamp()
            if now_ts >= cond.value:
                target_time = datetime.fromtimestamp(cond.value).strftime("%Y-%m-%d %H:%M")
                triggered.append((
                    cond,
                    f"Time-based exit reached: {target_time}"
                ))

    return triggered


def build_closing_legs(position):
    """
    Build the opposite legs needed to close a position.

    For each leg in the position:
        BUY  → SELL to close
        SELL → BUY to close

    Args:
        position: TrackedPosition object

    Returns:
        List of dicts with keys: code, side, qty, option_type, strike, label
    """
    closing = []
    for leg in position.legs:
        close_side = "SELL" if leg["side"] == "BUY" else "BUY"
        closing.append({
            "code": leg["code"],
            "side": close_side,
            "qty": leg["qty"],
            "option_type": leg["option_type"],
            "strike": leg["strike"],
            "label": f"Close {leg['label']}",
        })
    return closing


# ---------------------------------------------------------------------------
# Current P&L estimation
# ---------------------------------------------------------------------------

def estimate_current_pnl(position, current_prices_map):
    """
    Estimate the current unrealized P&L for a position.

    Args:
        position:           TrackedPosition object
        current_prices_map: Dict mapping contract code → current mid price

    Returns:
        Estimated P&L in dollars.

    How it works:
        For each leg, compute the P&L if you closed it now:
        - If you SOLD at open_premium and can BUY back at current_price:
          P&L per share = open_premium - current_price
        - If you BOUGHT at open_premium and can SELL at current_price:
          P&L per share = current_price - open_premium
    """
    total_pnl = 0.0

    for leg in position.legs:
        code = leg["code"]
        open_premium = leg["premium"]
        qty = leg["qty"]
        current_price = current_prices_map.get(code, open_premium)

        if leg["side"] == "SELL":
            pnl_per_share = open_premium - current_price
        else:
            pnl_per_share = current_price - open_premium

        total_pnl += pnl_per_share * qty * config.CONTRACT_MULTIPLIER

    return round(total_pnl, 2)

"""
portfolio_advisor.py — Portfolio Advisory Agent.

Connects to MooMoo OpenD to fetch live portfolio positions,
cross-references with daily research signals, and generates
personalized BUY / HOLD / TRIM / SELL / NEW BUY recommendations
targeting 3%+ monthly portfolio growth.

Requires MooMoo OpenD running on localhost:11111.
"""

import logging
import time
from datetime import datetime
from typing import Optional

from moomoo import (
    OpenSecTradeContext,
    OpenQuoteContext,
    TrdEnv,
    TrdMarket,
    RET_OK,
    SecurityFirm,
)

logger = logging.getLogger(__name__)

# Monthly growth target
MONTHLY_TARGET_PCT = 3.0

# Allocation limits
MAX_SINGLE_POSITION_PCT = 15.0  # Max % of portfolio in one stock
MAX_SECTOR_PCT = 35.0           # Max % in one sector
MIN_POSITIONS = 8               # Minimum diversification


class PortfolioAdvisor:
    """Fetches live portfolio and generates actionable recommendations."""

    def __init__(self, host="127.0.0.1", port=11111):
        self.host = host
        self.port = port
        self._trade_ctx = None
        self._quote_ctx = None

    def connect(self):
        """Connect to MooMoo OpenD."""
        try:
            self._trade_ctx = OpenSecTradeContext(
                host=self.host,
                port=self.port,
                filter_trdmarket=TrdMarket.US,
                security_firm=SecurityFirm.FUTUSG,
            )
            self._quote_ctx = OpenQuoteContext(
                host=self.host,
                port=self.port,
            )
            logger.info("Connected to MooMoo OpenD")
        except Exception as e:
            logger.error(f"Failed to connect to MooMoo OpenD: {e}")
            raise

    def close(self):
        """Close connections."""
        if self._trade_ctx:
            self._trade_ctx.close()
        if self._quote_ctx:
            self._quote_ctx.close()

    def fetch_account_info(self, trd_env=TrdEnv.REAL) -> Optional[dict]:
        """Fetch account balance, buying power, etc."""
        try:
            ret, data = self._trade_ctx.accinfo_query(
                trd_env=trd_env, currency="USD"
            )
            if ret != RET_OK:
                logger.error(f"Account info query failed: {data}")
                return None

            if data.empty:
                logger.warning("No account info returned")
                return None

            row = data.iloc[0]

            def _float(val, default=0):
                try:
                    return float(val) if val is not None else default
                except (ValueError, TypeError):
                    return default

            return {
                "total_assets": _float(row.get("total_assets")),
                "cash": _float(row.get("cash")),
                "market_value": _float(row.get("market_val")),
                "frozen_cash": _float(row.get("frozen_cash")),
                "available_funds": _float(row.get("avl_withdrawal_cash")),
                "unrealized_pnl": _float(row.get("unrealized_pl")),
                "realized_pnl": _float(row.get("realized_pl")),
                "buying_power": _float(row.get("power", row.get("max_power_short", 0))),
                "risk_level": row.get("risk_level", "N/A"),
                "currency": "USD",
            }
        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            return None

    def fetch_positions(self, trd_env=TrdEnv.REAL) -> list[dict]:
        """Fetch all current portfolio positions."""
        try:
            ret, data = self._trade_ctx.position_list_query(
                trd_env=trd_env
            )
            if ret != RET_OK:
                logger.error(f"Position query failed: {data}")
                return []

            if data.empty:
                logger.info("No open positions")
                return []

            positions = []
            for _, row in data.iterrows():
                code = row.get("code", "")
                # Extract ticker from MooMoo format (US.AAPL -> AAPL)
                ticker = code.split(".")[-1] if "." in code else code

                def _f(val, default=0):
                    try:
                        return float(val) if val is not None else default
                    except (ValueError, TypeError):
                        return default

                pos = {
                    "code": code,
                    "ticker": ticker,
                    "name": row.get("stock_name", ticker),
                    "qty": _f(row.get("qty")),
                    "can_sell_qty": _f(row.get("can_sell_qty")),
                    "cost_price": _f(row.get("cost_price")),
                    "current_price": _f(row.get("nominal_price")),
                    "market_value": _f(row.get("market_val")),
                    "unrealized_pnl": _f(row.get("unrealized_pl")),
                    "unrealized_pnl_pct": _f(row.get("pl_ratio")),
                    "today_pnl": _f(row.get("today_pl_val")),
                    "today_pnl_pct": _f(row.get("today_pl_ratio")),
                    "position_side": row.get("position_side", "LONG"),
                }
                positions.append(pos)

            logger.info(f"Fetched {len(positions)} positions")
            return positions

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def fetch_recent_deals(self, trd_env=TrdEnv.REAL, days=30) -> list[dict]:
        """Fetch recent trade history."""
        try:
            end = datetime.now().strftime("%Y-%m-%d")
            from datetime import timedelta
            start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            ret, data = self._trade_ctx.history_deal_list_query(
                start=start, end=end, trd_env=trd_env
            )
            if ret != RET_OK:
                logger.error(f"Deal history query failed: {data}")
                return []

            if data.empty:
                return []

            deals = []
            for _, row in data.iterrows():
                code = row.get("code", "")
                ticker = code.split(".")[-1] if "." in code else code
                deals.append({
                    "ticker": ticker,
                    "code": code,
                    "side": row.get("trd_side", ""),
                    "qty": row.get("qty", 0),
                    "price": row.get("price", 0),
                    "time": row.get("create_time", ""),
                })

            return deals
        except Exception as e:
            logger.error(f"Error fetching deals: {e}")
            return []

    def generate_recommendations(
        self,
        positions: list[dict],
        account_info: dict,
        technical_results: list[dict],
        fundamental_results: list[dict],
        dip_buys: list[dict],
        dip_sells: list[dict],
        opportunities: list[dict],
    ) -> dict:
        """Generate personalized portfolio recommendations.

        Returns a dict with:
          - portfolio_summary: overall portfolio health
          - hold: positions to keep
          - trim: positions to reduce
          - sell: positions to exit
          - add: existing positions to add to
          - new_buy: new positions to initiate
          - rebalance: allocation adjustments
          - risk_alerts: concentration/risk warnings
        """
        # Build lookups
        tech_lookup = {t["ticker"]: t for t in technical_results if t}
        fund_lookup = {f["ticker"]: f for f in fundamental_results if f}
        dip_buy_lookup = {d["ticker"]: d for d in (dip_buys or [])}
        dip_sell_lookup = {d["ticker"]: d for d in (dip_sells or [])}
        opp_lookup = {o["ticker"]: o for o in (opportunities or [])}

        total_value = account_info.get("total_assets", 0) or 1
        cash = account_info.get("cash", 0)
        cash_pct = (cash / total_value * 100) if total_value > 0 else 0

        # Analyze each position
        hold_list = []
        trim_list = []
        sell_list = []
        add_list = []

        held_tickers = set()
        sector_exposure = {}

        for pos in positions:
            ticker = pos["ticker"]
            held_tickers.add(ticker)
            tech = tech_lookup.get(ticker, {})
            fund = fund_lookup.get(ticker, {})
            dip_sell = dip_sell_lookup.get(ticker)
            dip_buy = dip_buy_lookup.get(ticker)
            opp = opp_lookup.get(ticker)

            # Position weight
            pos_value = pos.get("market_value", 0)
            weight = (pos_value / total_value * 100) if total_value > 0 else 0
            pos["weight_pct"] = round(weight, 2)

            # Sector tracking
            sector = fund.get("sector", "Unknown")
            pos["sector"] = sector
            sector_exposure[sector] = sector_exposure.get(sector, 0) + weight

            # Unrealized P&L
            pnl_pct = pos.get("unrealized_pnl_pct", 0) or 0

            # Technical signal
            signal = tech.get("signal", "HOLD")
            composite = tech.get("composite_score", 0)
            rsi = tech.get("rsi", 50)
            trend = tech.get("trend", "UNKNOWN")

            # Fund quality
            quality = fund.get("quality", "N/A")
            fund_score = fund.get("total_score", 0)

            # Analyst target
            target = fund.get("target_mean")
            current = pos.get("current_price", 0)
            upside = ((target - current) / current * 100) if target and current else None

            # Build recommendation
            rec = {
                **pos,
                "signal": signal,
                "composite_score": composite,
                "rsi": rsi,
                "trend": trend,
                "fund_quality": quality,
                "fund_score": fund_score,
                "analyst_target": target,
                "upside_pct": upside,
                "pnl_pct": pnl_pct,
                "reasons": [],
                "action_detail": "",
            }

            # === Decision Logic ===

            # SELL: Fundamental deterioration
            if dip_sell:
                rec["action"] = "SELL"
                rec["reasons"].append(f"Fundamental deterioration detected (sell score {dip_sell['sell_score']}/100)")
                for ins in dip_sell.get("insights", [])[:2]:
                    rec["reasons"].append(ins)
                sell_list.append(rec)
                continue

            # SELL: Strong sell signal + poor fundamentals
            if signal in ("STRONG_SELL", "SELL") and quality in ("POOR",):
                rec["action"] = "SELL"
                rec["reasons"].append(f"Technical {signal} + {quality} fundamentals")
                if pnl_pct > 0:
                    rec["reasons"].append(f"Lock in {pnl_pct:.1f}% gain before further deterioration")
                sell_list.append(rec)
                continue

            # TRIM: Overweight position
            if weight > MAX_SINGLE_POSITION_PCT:
                rec["action"] = "TRIM"
                rec["reasons"].append(f"Position is {weight:.1f}% of portfolio (max {MAX_SINGLE_POSITION_PCT}%)")
                rec["action_detail"] = f"Trim to {MAX_SINGLE_POSITION_PCT:.0f}% allocation"
                trim_list.append(rec)
                continue

            # TRIM: Big gain + overbought
            if pnl_pct > 50 and rsi and rsi > 75:
                rec["action"] = "TRIM"
                rec["reasons"].append(f"Up {pnl_pct:.0f}% with RSI overbought at {rsi:.0f}")
                rec["reasons"].append("Take partial profits to lock in gains")
                rec["action_detail"] = "Sell 30-50% of position to lock profits"
                trim_list.append(rec)
                continue

            # TRIM: Hit analyst target
            if upside is not None and upside < -5:
                rec["action"] = "TRIM"
                rec["reasons"].append(f"Trading {abs(upside):.0f}% above analyst target ${target:.0f}")
                rec["reasons"].append("Price may be fully valued — take partial profits")
                rec["action_detail"] = "Trim 25-50% and reassess"
                trim_list.append(rec)
                continue

            # ADD: Position is a dip buy opportunity (already own it, add more)
            if dip_buy and weight < MAX_SINGLE_POSITION_PCT * 0.8:
                rec["action"] = "ADD"
                rec["reasons"].append(f"Dip-buy opportunity (score {dip_buy['dip_score']}/100) — add to existing position")
                for ins in dip_buy.get("insights", [])[:2]:
                    rec["reasons"].append(ins)
                rec["action_detail"] = f"Add up to {MAX_SINGLE_POSITION_PCT:.0f}% total weight"
                add_list.append(rec)
                continue

            # ADD: Strong buy signal on existing position with room
            if signal in ("STRONG_BUY", "BUY") and weight < 8 and quality in ("EXCELLENT", "GOOD"):
                rec["action"] = "ADD"
                rec["reasons"].append(f"Technical {signal} with {quality} fundamentals")
                if upside and upside > 15:
                    rec["reasons"].append(f"Analyst target implies {upside:.0f}% upside")
                rec["action_detail"] = "Increase position by 25-50%"
                add_list.append(rec)
                continue

            # HOLD: Everything else with intact thesis
            rec["action"] = "HOLD"
            if quality in ("EXCELLENT", "GOOD"):
                rec["reasons"].append(f"Fundamentals {quality} — thesis intact")
            if "UPTREND" in trend:
                rec["reasons"].append("Long-term uptrend intact")
            if upside and upside > 10:
                rec["reasons"].append(f"Analyst target ${target:.0f} ({upside:+.0f}% upside)")
            if signal == "HOLD":
                rec["reasons"].append("Technical signals neutral — no action needed")
            if not rec["reasons"]:
                rec["reasons"].append("No clear catalyst for change — maintain position")
            hold_list.append(rec)

        # === NEW BUY ideas (not already in portfolio) ===
        new_buy_list = []

        # From dip buys
        for d in (dip_buys or [])[:20]:
            if d["ticker"] not in held_tickers:
                tech = tech_lookup.get(d["ticker"], {})
                fund = fund_lookup.get(d["ticker"], {})
                new_buy_list.append({
                    "ticker": d["ticker"],
                    "name": d.get("name", d["ticker"]),
                    "current_price": d.get("current_price"),
                    "source": "DIP_BUY",
                    "score": d["dip_score"],
                    "fund_quality": d.get("fund_quality", "N/A"),
                    "fund_score": d.get("fund_score", 0),
                    "rsi": d.get("rsi"),
                    "analyst_target": d.get("analyst_target"),
                    "upside_pct": ((d.get("analyst_target", 0) - d.get("current_price", 1)) / d.get("current_price", 1) * 100) if d.get("analyst_target") and d.get("current_price") else None,
                    "reasons": d.get("insights", [])[:3],
                    "risk_factors": d.get("risk_factors", [])[:2],
                    "sector": fund.get("sector", "Unknown"),
                    "pct_from_52w_high": d.get("pct_from_52w_high"),
                    "revenue_growth": d.get("revenue_growth"),
                    "earnings_growth": d.get("earnings_growth"),
                })

        # From top opportunities not in portfolio
        for o in (opportunities or [])[:15]:
            if o["ticker"] not in held_tickers and o["ticker"] not in {n["ticker"] for n in new_buy_list}:
                if o.get("opportunity_score", 0) >= 50:
                    new_buy_list.append({
                        "ticker": o["ticker"],
                        "name": o.get("ticker"),
                        "current_price": o.get("current_price"),
                        "source": "THEMATIC",
                        "score": o.get("opportunity_score", 0),
                        "fund_quality": o.get("fund_quality", "N/A"),
                        "fund_score": 0,
                        "rsi": None,
                        "analyst_target": o.get("analyst_target"),
                        "upside_pct": ((o.get("analyst_target", 0) - o.get("current_price", 1)) / o.get("current_price", 1) * 100) if o.get("analyst_target") and o.get("current_price") else None,
                        "reasons": [o.get("thesis", "")] + o.get("multibagger_signals", [])[:2],
                        "risk_factors": o.get("risk_factors", [])[:2],
                        "sector": "Technology",  # Most are tech
                        "pct_from_52w_high": None,
                        "revenue_growth": o.get("revenue_growth"),
                        "earnings_growth": o.get("earnings_growth"),
                    })

        # Sort new buys by score
        new_buy_list.sort(key=lambda x: x.get("score", 0), reverse=True)

        # === Risk Alerts ===
        risk_alerts = []

        # Concentration risk
        for sector, exposure in sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True):
            if exposure > MAX_SECTOR_PCT:
                risk_alerts.append({
                    "type": "SECTOR_CONCENTRATION",
                    "severity": "HIGH",
                    "message": f"{sector} sector at {exposure:.1f}% of portfolio (max {MAX_SECTOR_PCT}%). Consider diversifying.",
                })

        # Cash drag
        if cash_pct > 30:
            risk_alerts.append({
                "type": "EXCESS_CASH",
                "severity": "MEDIUM",
                "message": f"Cash is {cash_pct:.1f}% of portfolio. Deploy into conviction ideas to hit 3%+ monthly target.",
            })
        elif cash_pct < 5:
            risk_alerts.append({
                "type": "LOW_CASH",
                "severity": "MEDIUM",
                "message": f"Cash only {cash_pct:.1f}%. Maintain 5-10% cash reserve for dip-buying opportunities.",
            })

        # Under-diversification
        if len(positions) < MIN_POSITIONS and len(positions) > 0:
            risk_alerts.append({
                "type": "UNDER_DIVERSIFIED",
                "severity": "HIGH",
                "message": f"Only {len(positions)} positions. Minimum {MIN_POSITIONS} recommended for risk management.",
            })

        # Portfolio monthly growth estimate
        # Rough estimate based on avg analyst upside / 12
        avg_upside = 0
        upside_count = 0
        for pos in positions:
            ticker = pos["ticker"]
            fund = fund_lookup.get(ticker, {})
            target = fund.get("target_mean")
            current = pos.get("current_price", 0)
            if target and current and current > 0:
                avg_upside += (target - current) / current * 100
                upside_count += 1
        monthly_est = (avg_upside / upside_count / 12) if upside_count else 0

        # Portfolio summary
        portfolio_summary = {
            "total_value": total_value,
            "cash": cash,
            "cash_pct": round(cash_pct, 1),
            "market_value": account_info.get("market_value", 0),
            "unrealized_pnl": account_info.get("unrealized_pnl", 0),
            "realized_pnl": account_info.get("realized_pnl", 0),
            "num_positions": len(positions),
            "sector_exposure": sector_exposure,
            "estimated_monthly_return": round(monthly_est, 2),
            "on_track_for_target": monthly_est >= MONTHLY_TARGET_PCT,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        return {
            "portfolio_summary": portfolio_summary,
            "hold": hold_list,
            "trim": trim_list,
            "sell": sell_list,
            "add": add_list,
            "new_buy": new_buy_list[:10],
            "risk_alerts": risk_alerts,
        }

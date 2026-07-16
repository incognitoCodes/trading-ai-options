#!/usr/bin/env python3
"""
run_options_daily.py — Orchestrator for Options Premium Advisory.

Run this script to scan top ~100 blue-chip stocks + indices for
premium selling opportunities based on elevated implied volatility.

Usage:
  python -m research_agents.run_options_daily               # Full scan
  python -m research_agents.run_options_daily --quick        # Quick (~25 tickers)
  python -m research_agents.run_options_daily --no-email     # Skip email
  python -m research_agents.run_options_daily --tickers NVDA AAPL SPY

Cron example (run at 6am + 6pm SGT every weekday):
  0 6,18 * * 1-5 cd /path/to/Trading_AI && python -m research_agents.run_options_daily
"""

import sys
import os
import argparse
import logging
import time
from datetime import datetime

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Load .env
_env_file = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

from research_agents.data_collector import DataCollector
from research_agents.options_advisor import OptionsAdvisor, OPTIONS_UNIVERSE
from research_agents.options_report import OptionsReportGenerator
from research_agents.email_sender import EmailSender
from research_agents.config import OPTIONS_EMAIL_RECIPIENT
from research_agents.watchlist import QUICK_SCAN

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_options_daily")


def run(
    tickers: list[str] = None,
    quick: bool = False,
    send_email: bool = True,
):
    """Options premium advisory pipeline."""
    start_time = time.time()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"=== Options Premium Advisory — {date_str} ===")

    # Select tickers
    if tickers:
        watchlist = tickers
    elif quick:
        watchlist = QUICK_SCAN
    else:
        watchlist = OPTIONS_UNIVERSE

    logger.info(
        f"Scanning {len(watchlist)} tickers: "
        f"{', '.join(watchlist[:10])}{'...' if len(watchlist) > 10 else ''}"
    )

    # Initialize agents
    collector = DataCollector()
    advisor = OptionsAdvisor()
    report_gen = OptionsReportGenerator()
    emailer = EmailSender()

    # Step 1: VIX Context
    logger.info("Step 1/5: Fetching VIX and market volatility context...")
    vix_context = advisor.get_vix_context()
    if vix_context:
        logger.info(
            f"  VIX: {vix_context.get('vix')} "
            f"({vix_context.get('regime')}) "
            f"Percentile: {vix_context.get('vix_percentile')}%"
        )

    # Step 2: Price Data (for realized vol)
    logger.info("Step 2/5: Fetching 1-year price data for realized volatility...")
    price_data = collector.get_batch_data(watchlist)
    logger.info(f"  Got price data for {len(price_data)} tickers")

    # Step 3: Options Analysis
    logger.info("Step 3/5: Scanning option chains and scoring premium opportunities...")
    options_results = advisor.analyze_options(price_data, tickers=watchlist)
    top_opps = advisor.get_top_opportunities(options_results, n=20)
    logger.info(
        f"  Analyzed {len(options_results)} tickers with options data"
    )
    if top_opps:
        logger.info(
            f"  Top opportunity: {top_opps[0]['ticker']} "
            f"(score {top_opps[0]['premium_score']}/100)"
        )

    # Step 3b: Build weekly trade portfolio ($5K target, max 40 contracts)
    logger.info("Step 3b: Building weekly trade portfolio (target $5,000)...")
    portfolio = advisor.build_weekly_portfolio(
        options_results,
        target_premium=5000.0,
        max_contracts=30,
        max_per_ticker=5,
    )
    logger.info(
        f"  Portfolio: {portfolio['total_contracts']} contracts, "
        f"${portfolio['total_premium']:,.0f} premium "
        f"({portfolio['pct_of_target']:.0f}% of target)"
    )

    # Step 4: Generate Report
    logger.info("Step 4/5: Generating options advisory report...")
    html = report_gen.generate(
        vix_context=vix_context,
        options_results=options_results,
        top_opportunities=top_opps,
        portfolio=portfolio,
    )

    # Step 5: Email (ONLY to the configured OPTIONS_EMAIL_RECIPIENT)
    if send_email:
        logger.info("Step 5/5: Emailing options advisory...")
        date_label = datetime.now().strftime("%Y-%m-%d")
        subject = f"Options Premium Advisory — {date_label}"
        sent = emailer.send_report(
            html,
            subject=subject,
            recipients=[OPTIONS_EMAIL_RECIPIENT],
        )
        if sent:
            logger.info(f"  Email sent to {OPTIONS_EMAIL_RECIPIENT}")
        else:
            logger.warning("  Email not sent.")

    elapsed = time.time() - start_time
    logger.info(f"=== Options Advisory Complete in {elapsed:.1f}s ===")

    # ─── Console Output ─────────────────────────────────────────────

    print("\n" + "=" * 80)
    print("OPTIONS PREMIUM ADVISORY — Sell Overpriced Volatility")
    print("=" * 80)

    if vix_context:
        print(
            f"  VIX: {vix_context.get('vix', 'N/A')}  "
            f"({vix_context.get('regime', '')})  "
            f"Percentile: {vix_context.get('vix_percentile', '')}%  "
            f"52W: {vix_context.get('vix_52w_low', '')}–"
            f"{vix_context.get('vix_52w_high', '')}"
        )

    # ─── Weekly Trade Portfolio ─────────────────────────────────────
    print("\n" + "=" * 80)
    print("💰 WEEKLY TRADE PORTFOLIO — Target: $5,000/week")
    print("=" * 80)

    if portfolio and portfolio.get("trades"):
        p_trades = portfolio["trades"]
        p_total = portfolio["total_premium"]
        p_contracts = portfolio["total_contracts"]
        p_pct = portfolio["pct_of_target"]
        p_max_loss = portfolio.get("total_max_loss", 0)
        tier_bk = portfolio.get("tier_breakdown", {})

        print(
            f"  Total Premium: ${p_total:,.0f}  |  "
            f"Target: {p_pct:.0f}%  |  "
            f"Contracts: {p_contracts}/40  |  "
            f"Max Risk: ${p_max_loss:,.0f}  |  "
            f"Portfolio R/R: 1:{p_max_loss/p_total:.1f}" if p_total > 0 else ""
        )
        # Risk tier breakdown
        if tier_bk:
            agg = tier_bk.get("aggressive", 0)
            mod = tier_bk.get("moderate", 0)
            con = tier_bk.get("conservative", 0)
            print(
                f"  Risk Mix: 🛡️ Conservative ${con:,.0f} "
                f"({con/p_total*100:.0f}%)  |  "
                f"⚖️ Moderate ${mod:,.0f} "
                f"({mod/p_total*100:.0f}%)  |  "
                f"⚡ Aggressive ${agg:,.0f} "
                f"({agg/p_total*100:.0f}%)" if p_total > 0 else ""
            )
        print("-" * 80)
        print(
            f"  {'#':>2}  {'Ticker':<6} {'Risk':<13} {'Strategy':<20} "
            f"{'Qty':>3} {'Prem/Ct':>8} {'Total':>8} "
            f"{'Running':>8} {'MaxLoss':>9} {'POP':>5}  Remark"
        )
        print("-" * 80)

        tier_icons = {
            "conservative": "🛡️ Conserv",
            "moderate": "⚖️ Moderate",
            "aggressive": "⚡ Aggress",
        }
        running = 0.0
        for i, t in enumerate(p_trades, 1):
            running += t["total_premium"]
            tier_str = tier_icons.get(t.get("risk_tier", ""), "")
            pop_str = f"{t['pop']:.0f}%" if t.get("pop") else "—"
            print(
                f"  {i:>2}  {t['ticker']:<6} "
                f"{tier_str:<13} "
                f"{t['strategy_display']:<20} "
                f"{t['contracts']:>3} "
                f"${t['premium_per_contract']:>7,.0f} "
                f"${t['total_premium']:>7,.0f} "
                f"${running:>7,.0f} "
                f"${t['total_max_loss']:>8,.0f} "
                f"{pop_str:>5}  "
                f"{t['remark']}"
            )

        print("-" * 80)
        print(
            f"  {'TOTAL':>43} {p_contracts:>3} "
            f"{'':>9} ${p_total:>7,.0f} "
            f"{'':>9} ${p_max_loss:>8,.0f}"
        )
    else:
        print("  No trades qualify for the portfolio today.")

    print("\n" + "-" * 80)
    print("TOP PREMIUM SELLING OPPORTUNITIES")
    print("-" * 80)

    if top_opps:
        for opp in top_opps[:12]:
            iv_str = f"{opp['atm_iv']*100:.1f}%" if opp.get("atm_iv") else "N/A"
            hv_str = f"{opp['hv_20']*100:.1f}%" if opp.get("hv_20") else "N/A"
            prem = opp.get("iv_premium")
            prem_str = f"{prem*100:+.1f}pp" if prem is not None else ""
            pctile = opp.get("iv_percentile")
            pctile_str = f"%ile:{pctile:.0f}%" if pctile is not None else ""

            print(
                f"\n  {opp['ticker']:<6} ${opp['current_price']:>8,.2f}  "
                f"Score: {opp['premium_score']}/100  "
                f"IV: {iv_str}  HV: {hv_str}  "
                f"{prem_str}  {pctile_str}"
            )
            # Price ranges + daily movement
            pr = opp.get("price_ranges") or {}
            rng_parts = []
            for label, key in [("1W", "range_1w"), ("2W", "range_2w"), ("1M", "range_1m")]:
                rng = pr.get(key)
                if rng:
                    rng_parts.append(f"{label}: ${rng['low']:.2f}–${rng['high']:.2f} ({rng['spread_pct']:.1f}%)")
            if rng_parts:
                print(f"    📊 {' | '.join(rng_parts)}")
            # ATR daily movement
            atr_val = opp.get("atr_14")
            daily_mv = opp.get("daily_move_pct")
            if atr_val and daily_mv:
                print(f"    📐 ATR(14): ${atr_val:.2f}/day ({daily_mv:.1f}% daily move)")
            # Upcoming events
            for ev in opp.get("upcoming_events", [])[:2]:
                move_part = f" (est. ±{ev['est_move']:.1f}%)" if ev.get("est_move") else ""
                print(f"    📅 [{ev['impact']}] {ev['event']} — {ev['date']} ({ev['days_away']}d){move_part}")
            # Strategy suggestion
            ss = opp.get("strategy_suggestion") or {}
            if ss:
                direction = ss.get("direction", "")
                print(f"    🎯 [{direction}] {ss.get('primary', '—')}  (alt: {ss.get('secondary', '—')})")
                if ss.get("event_note"):
                    print(f"       ⚠️  {ss['event_note']}")
            for ins in opp.get("insights", [])[:2]:
                print(f"    > {ins}")
            for trade in opp.get("trades", [])[:2]:
                pop_str = f"  POP: {trade['pop']:.0f}%" if trade.get("pop") else ""
                print(
                    f"    >> {trade['strategy_display']}: {trade['action']}  "
                    f"Credit: ${trade['premium']:.2f}  "
                    f"MaxProfit: ${trade['max_profit']:,.0f}  "
                    f"MaxLoss: ${trade['max_loss']:,.0f}"
                    f"{pop_str}"
                )
    else:
        print("  No premium selling opportunities found today.")

    print("\n" + "=" * 80)
    print(
        "DISCLAIMER: Options research signals only — NOT financial advice. "
        "Options involve risk of substantial loss.\n"
    )

    return options_results


def main():
    parser = argparse.ArgumentParser(
        description="Options Premium Advisory — Volatility Crush Opportunities"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick scan (~25 top tickers only)",
    )
    parser.add_argument(
        "--no-email", action="store_true",
        help="Skip email delivery",
    )
    parser.add_argument(
        "--tickers", nargs="+",
        help="Custom ticker list",
    )
    args = parser.parse_args()

    run(
        tickers=args.tickers,
        quick=args.quick,
        send_email=not args.no_email,
    )


if __name__ == "__main__":
    main()

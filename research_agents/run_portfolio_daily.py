#!/usr/bin/env python3
"""
run_portfolio_daily.py — Portfolio Action Plan Orchestrator.

Connects to MooMoo OpenD, fetches live portfolio positions,
runs the full research pipeline, cross-references positions
with signals, and emails a personalized Portfolio Action Plan.

Requires MooMoo OpenD running on localhost:11111.

Usage:
  python -m research_agents.run_portfolio_daily
  python -m research_agents.run_portfolio_daily --no-email
  python -m research_agents.run_portfolio_daily --paper   # Use paper trading account
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

from moomoo import TrdEnv

from research_agents.data_collector import DataCollector
from research_agents.technical_analyzer import TechnicalAnalyzer
from research_agents.fundamental_screener import FundamentalScreener
from research_agents.sector_analyzer import SectorAnalyzer
from research_agents.opportunity_finder import OpportunityFinder
from research_agents.dip_hunter import DipHunter
from research_agents.portfolio_advisor import PortfolioAdvisor
from research_agents.portfolio_report import PortfolioReportGenerator
from research_agents.email_sender import EmailSender
from research_agents.watchlist import DEFAULT_WATCHLIST

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_portfolio")


def run(send_email: bool = True, paper: bool = False):
    """Main portfolio advisory pipeline."""
    start_time = time.time()
    trd_env = TrdEnv.SIMULATE if paper else TrdEnv.REAL
    env_label = "PAPER" if paper else "REAL"

    logger.info(f"=== Portfolio Action Plan — {datetime.now():%Y-%m-%d %H:%M} ({env_label}) ===")

    # --- Step 1: Connect to MooMoo and fetch portfolio ---
    logger.info("Step 1/5: Connecting to MooMoo OpenD...")
    advisor = PortfolioAdvisor()
    try:
        advisor.connect()
    except Exception as e:
        logger.error(f"Cannot connect to MooMoo OpenD: {e}")
        logger.error("Make sure OpenD is running on localhost:11111")
        return

    logger.info("  Fetching account info...")
    account_info = advisor.fetch_account_info(trd_env=trd_env)
    if not account_info:
        logger.error("Failed to fetch account info")
        advisor.close()
        return
    logger.info(f"  Total assets: ${account_info['total_assets']:,.0f} | Cash: ${account_info['cash']:,.0f}")

    logger.info("  Fetching positions...")
    positions = advisor.fetch_positions(trd_env=trd_env)
    logger.info(f"  Found {len(positions)} open positions")

    # Get stock tickers from positions (filter out options contracts like SOXL260417C84000)
    import re
    held_tickers = [
        p["ticker"] for p in positions
        if not re.match(r'^[A-Z]+\d{6}[CP]\d+$', p["ticker"])
    ]

    # --- Step 2: Run research on held tickers + default watchlist ---
    logger.info("Step 2/5: Running research analysis...")
    # Analyze held tickers + DEFAULT_WATCHLIST for new buy ideas
    all_tickers = list(set(held_tickers + DEFAULT_WATCHLIST))

    collector = DataCollector()
    tech_analyzer = TechnicalAnalyzer()
    fund_screener = FundamentalScreener()
    opp_finder = OpportunityFinder()
    dip_hunter = DipHunter()

    # Market overview
    market_summary = collector.get_market_summary()
    logger.info(f"  Market data: {len(market_summary)} indicators")

    # Price + technicals
    price_data = collector.get_batch_data(all_tickers)
    technical_results = []
    for ticker in all_tickers:
        df = price_data.get(ticker)
        if df is not None:
            result = tech_analyzer.analyze(ticker, df)
            if result:
                technical_results.append(result)
    logger.info(f"  Technical analysis: {len(technical_results)} tickers")

    # Fundamentals
    fundamentals_raw = collector.get_batch_fundamentals(all_tickers)
    fundamental_results = []
    for ticker in all_tickers:
        fund = fundamentals_raw.get(ticker)
        if fund:
            scored = fund_screener.score(fund)
            if scored:
                fundamental_results.append(scored)
    logger.info(f"  Fundamentals: {len(fundamental_results)} tickers")

    # --- Step 3: Opportunities and dip analysis ---
    logger.info("Step 3/5: Scanning for opportunities...")
    opportunities = opp_finder.analyze_opportunities(technical_results, fundamental_results)
    top_opps = opp_finder.get_top_opportunities(opportunities, n=15)

    dip_buys = dip_hunter.find_dip_buys(technical_results, fundamental_results, market_summary)
    dip_sells = dip_hunter.find_sell_signals(technical_results, fundamental_results)
    # Remove overlaps
    sell_tickers = {d["ticker"] for d in dip_sells}
    dip_buys = [d for d in dip_buys if d["ticker"] not in sell_tickers]

    logger.info(f"  Dip buys: {len(dip_buys)} | Sell signals: {len(dip_sells)} | Opportunities: {len(top_opps)}")

    # --- Step 4: Generate recommendations ---
    logger.info("Step 4/5: Generating portfolio recommendations...")
    recommendations = advisor.generate_recommendations(
        positions=positions,
        account_info=account_info,
        technical_results=technical_results,
        fundamental_results=fundamental_results,
        dip_buys=dip_buys,
        dip_sells=dip_sells,
        opportunities=top_opps,
    )

    # Stats
    summary = recommendations["portfolio_summary"]
    n_sell = len(recommendations["sell"])
    n_trim = len(recommendations["trim"])
    n_add = len(recommendations["add"])
    n_hold = len(recommendations["hold"])
    n_new = len(recommendations["new_buy"])
    logger.info(
        f"  Recommendations: {n_sell} SELL | {n_trim} TRIM | "
        f"{n_add} ADD | {n_hold} HOLD | {n_new} NEW BUY"
    )

    # --- Step 5: Generate report and email ---
    logger.info("Step 5/5: Generating report...")
    report_gen = PortfolioReportGenerator()
    html = report_gen.generate(recommendations)

    if send_email:
        logger.info("Sending portfolio email...")
        emailer = EmailSender()
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        subject = f"Portfolio Action Plan \u2014 {date_str}"
        sent = emailer.send_report(
            html,
            subject=subject,
        )
        if sent:
            logger.info("  Portfolio email sent!")
        else:
            logger.warning("  Email not sent — check credentials")

    advisor.close()

    elapsed = time.time() - start_time
    logger.info(f"=== Complete in {elapsed:.1f}s ===")

    # Console summary
    print(f"\n{'='*80}")
    print(f"PORTFOLIO ACTION PLAN — {datetime.now():%Y-%m-%d}")
    print(f"{'='*80}")
    print(f"Total: ${summary['total_value']:,.0f} | Cash: ${summary['cash']:,.0f} ({summary['cash_pct']:.1f}%)")
    print(f"Positions: {summary['num_positions']} | Est Monthly: {summary['estimated_monthly_return']:+.1f}%")
    print()

    if recommendations["sell"]:
        print("SELL:")
        for p in recommendations["sell"]:
            print(f"  {p['ticker']:<8} ${p['current_price']:>10,.2f}  P&L: {p['pnl_pct']:+.1f}%  | {p['reasons'][0]}")

    if recommendations["trim"]:
        print("\nTRIM:")
        for p in recommendations["trim"]:
            print(f"  {p['ticker']:<8} ${p['current_price']:>10,.2f}  P&L: {p['pnl_pct']:+.1f}%  | {p['reasons'][0]}")

    if recommendations["add"]:
        print("\nADD:")
        for p in recommendations["add"]:
            print(f"  {p['ticker']:<8} ${p['current_price']:>10,.2f}  P&L: {p['pnl_pct']:+.1f}%  | {p['reasons'][0]}")

    if recommendations["new_buy"]:
        print("\nNEW BUY:")
        for n in recommendations["new_buy"][:5]:
            price_str = f"${n['current_price']:,.2f}" if n.get("current_price") else "N/A"
            print(f"  {n['ticker']:<8} {price_str:>10}  Score: {n['score']}/100  | {n['reasons'][0] if n['reasons'] else ''}")

    print(f"\n{'='*80}")
    print("DISCLAIMER: Automated analysis — NOT financial advice.\n")


def main():
    parser = argparse.ArgumentParser(description="Portfolio Action Plan")
    parser.add_argument("--no-email", action="store_true", help="Skip email delivery")
    parser.add_argument("--paper", action="store_true", help="Use paper trading account")
    args = parser.parse_args()

    run(send_email=not args.no_email, paper=args.paper)


if __name__ == "__main__":
    main()

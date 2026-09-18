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
from research_agents.options_advisor import (
    OptionsAdvisor, OPTIONS_UNIVERSE, OPTIONS_ETFS,
)
from research_agents.options_report import OptionsReportGenerator
from research_agents.email_sender import EmailSender
from research_agents.moomoo_quotes import MoomooOptionQuotes
from research_agents.macro_calendar import upcoming_macro_events
from research_agents.config import (
    OPTIONS_EMAIL_RECIPIENT,
    OPTIONS_USE_MOOMOO_REALTIME,
    OPTIONS_MIN_IV_LEVEL,
    OPTIONS_WEEKLY_TARGET,
    OPTIONS_MAX_RECOMMENDATIONS,
    OPTIONS_PREFILTER_TOP_N,
)
from research_agents.watchlist import QUICK_SCAN

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_options_daily")

# The large Russell 1000 scan hits some illiquid or recently-delisted symbols
# that yfinance logs as a noisy ERROR line each. Those names are simply skipped
# (the scan continues on valid names), so quiet yfinance's own logger.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


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

    # Step 0: Current stock holdings (for covered-call writes). Best-effort —
    # if OpenD is down we simply generate no covered calls this run.
    holdings = {}
    if OPTIONS_USE_MOOMOO_REALTIME:
        try:
            from research_agents.position_manager import OptionPositionAdvisor
            _pos = OptionPositionAdvisor()
            if _pos.connect():
                holdings = _pos.fetch_stock_holdings()
                _pos.close()
        except Exception as e:
            logger.warning(f"  Holdings fetch skipped: {e}")
    if holdings:
        logger.info(
            f"  Holdings for covered calls: "
            + ", ".join(f"{t}({h['shares']}sh)" for t, h in list(holdings.items())[:12])
        )
        # Always analyze held names (even outside the universe / pre-filter).
        watchlist = list(dict.fromkeys(watchlist + list(holdings.keys())))

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

    # Step 2b: Liquidity pre-filter — rank by dollar volume and keep the top N
    # so the expensive option-chain analysis only runs on liquid names.
    scan_list = watchlist
    if OPTIONS_PREFILTER_TOP_N and 0 < OPTIONS_PREFILTER_TOP_N < len(watchlist):
        scan_list = advisor.prefilter_by_dollar_volume(
            price_data, watchlist, OPTIONS_PREFILTER_TOP_N,
            always_keep=OPTIONS_ETFS + list(holdings.keys()),
        )
        logger.info(
            f"  Liquidity pre-filter: {len(watchlist)} -> {len(scan_list)} "
            f"names kept by average dollar volume (top {OPTIONS_PREFILTER_TOP_N})"
        )

    # Step 3: Options Analysis (Stage 1 screen — yfinance chains)
    logger.info("Step 3/5: Scanning option chains and scoring premium opportunities...")
    options_results = advisor.analyze_options(
        price_data, tickers=scan_list, holdings=holdings,
    )

    # IV LEVEL SCREEN — per spec, only CONSIDER names with ATM IV > threshold.
    iv_pass = [r for r in options_results if r.get("iv_level_pass")]
    logger.info(
        f"  Analyzed {len(options_results)} tickers; "
        f"{len(iv_pass)} passed the IV > {OPTIONS_MIN_IV_LEVEL*100:.0f}% level screen"
    )
    if iv_pass:
        logger.info(
            "  High-IV names: "
            + ", ".join(
                f"{r['ticker']}({r['atm_iv']*100:.0f}%)" for r in iv_pass[:12]
            )
        )
    # The email considers names that cleared the IV screen, plus any held name
    # carrying a covered call (income on shares, generated regardless of the
    # IV screen). Everything else is dropped from here on.
    def _has_covered_call(r):
        return any(
            t.get("strategy") == "COVERED_CALL"
            for t in (r.get("trades") or []) + (r.get("weekly_trades") or [])
        )
    held_cc = [
        r for r in options_results
        if not r.get("iv_level_pass") and _has_covered_call(r)
    ]
    if held_cc:
        logger.info(f"  Plus {len(held_cc)} held name(s) with covered-call writes.")
    options_results = iv_pass + held_cc

    # Step 3a: Stage 2 — confirm ACTUAL premium on MooMoo real-time book and
    # apply the high-probability gate. Runs at US market open (9:30 ET).
    gate_summary = {"realtime_available": False, "candidates": 0,
                    "confirmed": 0, "high_prob": 0, "as_of": None}
    realtime = None
    if OPTIONS_USE_MOOMOO_REALTIME and options_results:
        logger.info(
            "Step 3a: Confirming premiums on MooMoo real-time data "
            "(OpenD) + applying high-probability gate..."
        )
        realtime = MoomooOptionQuotes()
        realtime.connect()  # graceful: falls back to yfinance if OpenD down
        try:
            gate_summary = advisor.confirm_and_gate(options_results, realtime=realtime)
        finally:
            realtime.close()
        logger.info(
            f"  Real-time: {gate_summary['realtime_available']} | "
            f"candidates {gate_summary['candidates']} | "
            f"confirmed {gate_summary['confirmed']} | "
            f"HIGH-PROB {gate_summary['high_prob']}"
            + (f" | quotes as of {gate_summary['as_of']}"
               if gate_summary.get("as_of") else "")
        )
    elif not options_results:
        logger.info("Step 3a: No names cleared the IV screen today — skipping real-time confirm.")

    top_opps = advisor.get_top_opportunities(options_results, n=OPTIONS_MAX_RECOMMENDATIONS)
    if top_opps:
        logger.info(
            f"  Top opportunity: {top_opps[0]['ticker']} "
            f"(score {top_opps[0]['premium_score']}/100)"
        )

    # Step 3b: Build two-part weekly portfolio toward $4K target.
    #   Part 1 = high-conviction gated trades; Part 2 = confirmed near-misses
    #   added only to reach the $4,000 target.
    logger.info("Step 3b: Building two-part weekly portfolio (target $4,000)...")
    portfolio = advisor.build_two_part_portfolio(
        options_results,
        target=OPTIONS_WEEKLY_TARGET,
        max_contracts=30,
        max_per_ticker=5,
        max_trades=OPTIONS_MAX_RECOMMENDATIONS,
    )
    logger.info(
        f"  Portfolio: {portfolio['total_contracts']} contracts, "
        f"${portfolio['total_premium']:,.0f} premium "
        f"({portfolio['pct_of_target']:.0f}% of ${OPTIONS_WEEKLY_TARGET:,.0f}) "
        f"— Part 1 (high-conviction) ${portfolio['core_premium']:,.0f}, "
        f"Part 2 (fillers) ${portfolio['fill_premium']:,.0f}"
    )

    # Step 3b.1: Trader sentiment — news tone for the recommended shortlist,
    # blended with options positioning and hold quality already on each result.
    # Annotation and ranking only; nothing is blocked.
    rec_tickers = {t["ticker"] for t in portfolio.get("trades", [])}
    rec_tickers |= {o["ticker"] for o in top_opps}
    if rec_tickers:
        logger.info(
            f"Step 3b.1: Reading news + positioning for "
            f"{len(rec_tickers)} recommended name(s)..."
        )
        advisor.enrich_sentiment(options_results, rec_tickers)
        by_ticker = {r["ticker"]: r for r in options_results}
        for t in portfolio.get("trades", []):
            r = by_ticker.get(t["ticker"])
            if not r:
                continue
            hq = r.get("hold_quality") or {}
            ns = r.get("news_sentiment") or {}
            t["trader_bias"] = r.get("trader_bias")
            t["hold_quality_label"] = hq.get("label")
            t["news_label"] = ns.get("label")
            tag = f"Bias {r.get('trader_bias', '?')}"
            if t["strategy"] == "CASH_SECURED_PUT" and hq.get("label"):
                tag += f", Hold {hq['label']}"
                # Expert caution: selling puts into weak tone/quality.
                if hq.get("label") == "Weak" or ns.get("label") == "Bearish":
                    tag += " ⚠"
            t["remark"] = f"{t.get('remark', '')} · {tag}".strip(" ·")

    # Step 3d: Pull OPEN option positions and generate defensive advice
    positions = None
    if OPTIONS_USE_MOOMOO_REALTIME:
        logger.info("Step 3d: Fetching open option positions for defensive advice...")
        try:
            from research_agents.position_manager import OptionPositionAdvisor
            pos_adv = OptionPositionAdvisor()
            if pos_adv.connect():
                positions = pos_adv.advise()
                pos_adv.close()
                logger.info(
                    f"  {len(positions)} open option position(s): "
                    + ", ".join(
                        f"{p['side']} {p['contracts']}x {p['underlying']} "
                        f"${p['strike']:.0f}{p['type'][0]} [{p['assessment']['verdict']}]"
                        for p in positions
                    )
                )
            else:
                logger.warning("  Could not connect for positions — skipping.")
        except Exception as e:
            logger.warning(f"  Position advisory skipped: {e}")

    # Step 3c: Backtest the core strategy so the email shows how it has
    # actually performed (approximate model — see options_backtester docs)
    backtest_summary = None
    try:
        from research_agents.options_backtester import OptionsBacktester
        logger.info("Step 3c: Backtesting put credit spread strategy (SPY)...")
        bt = OptionsBacktester("SPY")
        bt_df = bt.load_data("8y")
        bt_results = [bt.run(bt_df), bt.run(bt_df, manage=True)]
        backtest_summary = OptionsBacktester.format_summary(bt_results)
        logger.info(f"\n{backtest_summary}")
    except Exception as e:
        logger.warning(f"  Backtest skipped: {e}")

    # Step 4: Generate Report
    logger.info("Step 4/5: Generating options advisory report...")
    macro_events = upcoming_macro_events(within_days=30)
    html = report_gen.generate(
        vix_context=vix_context,
        options_results=options_results,
        top_opportunities=top_opps,
        portfolio=portfolio,
        backtest_summary=backtest_summary,
        gate_summary=gate_summary,
        macro_events=macro_events,
        iv_min_level=OPTIONS_MIN_IV_LEVEL,
        positions=positions,
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
        for opp in top_opps[:OPTIONS_MAX_RECOMMENDATIONS]:
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
            # Trader read: news tone + options positioning + hold quality
            pos = opp.get("options_positioning") or {}
            hq = opp.get("hold_quality") or {}
            ns = opp.get("news_sentiment") or {}
            read_bits = [f"Bias: {opp.get('trader_bias') or pos.get('label', 'Neutral')}"]
            if pos.get("note"):
                read_bits.append(f"Options {pos.get('label','')} ({pos['note']})")
            if hq.get("label"):
                read_bits.append(f"Hold {hq['label']}")
            if ns.get("label") and ns.get("n"):
                read_bits.append(f"News {ns['label']} ({ns['n']})")
            print(f"    🧭 {' | '.join(read_bits)}")
            if ns.get("headlines"):
                h0 = ns["headlines"][0]
                print(f"    📰 {h0['title'][:90]}")

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

"""
options_report.py — Options Premium Advisory Report Generator.

Generates an HTML email report for premium selling opportunities.
Sections:
  - Market Volatility Overview (VIX context)
  - Top Premium Selling Opportunities (scored cards)
  - Specific Trade Ideas (strikes, premiums, risk/reward)
  - IV Heatmap (all scanned tickers)

DISCLAIMER: Research signals only — not financial advice.
Options involve risk of substantial loss.
"""

import os
import logging
from datetime import datetime

from research_agents.config import REPORT_DIR, OPTIONS_MIN_POP

logger = logging.getLogger(__name__)


class OptionsReportGenerator:
    """Generates HTML options advisory reports."""

    def generate(
        self,
        vix_context: dict,
        options_results: list[dict],
        top_opportunities: list[dict],
        portfolio: dict = None,
        backtest_summary: str = None,
        gate_summary: dict = None,
        macro_events: list[dict] = None,
        iv_min_level: float = 0.60,
        positions: list = None,
    ) -> str:
        """Generate a complete HTML options advisory report.

        Returns the HTML string.
        """
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        time_str = datetime.now().strftime("%H:%M:%S")

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Options Premium Advisory — {date_str}</title>
<style>
  body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f6fa; color: #2c3e50; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #2d1b69 50%, #6a1b9a 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
  .header h1 {{ margin: 0 0 5px 0; font-size: 24px; }}
  .header .date {{ opacity: 0.8; font-size: 14px; }}
  .disclaimer {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 12px 16px; font-size: 12px; color: #856404; margin-bottom: 20px; }}
  .section {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .section h2 {{ margin-top: 0; color: #1a1a2e; border-bottom: 2px solid #e8e8e8; padding-bottom: 10px; font-size: 18px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f8f9fa; padding: 10px 8px; text-align: left; font-weight: 600; color: #555; border-bottom: 2px solid #dee2e6; }}
  td {{ padding: 8px; border-bottom: 1px solid #f0f0f0; }}
  tr:hover {{ background: #f8f9fa; }}
  .positive {{ color: #00c853; font-weight: 600; }}
  .negative {{ color: #f44336; font-weight: 600; }}
  .neutral {{ color: #757575; }}
  .vix-strip {{ display: flex; align-items: center; gap: 24px; flex-wrap: wrap; font-size: 14px; }}
  .vix-strip .vix-val {{ font-size: 28px; font-weight: bold; }}
  .vix-strip .vix-label {{ font-size: 11px; color: #888; }}
  .regime-badge {{ padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
  .regime-HIGH_VOL {{ background: #f44336; color: white; }}
  .regime-ELEVATED {{ background: #ff9800; color: white; }}
  .regime-NORMAL {{ background: #4caf50; color: white; }}
  .regime-LOW_VOL {{ background: #90a4ae; color: white; }}
  .ocard {{ background: linear-gradient(135deg, #f3e5f5 0%, #e8eaf6 100%); border-left: 5px solid #6a1b9a; border-radius: 8px; padding: 16px; margin: 12px 0; }}
  .ocard .ocard-head {{ font-size: 17px; font-weight: bold; color: #1a1a2e; }}
  .ocard .ocard-metrics {{ font-size: 13px; color: #555; margin: 6px 0; }}
  .ocard .ocard-metrics .high {{ color: #2e7d32; font-weight: 600; }}
  .ocard .ocard-metrics .warn {{ color: #c62828; font-weight: 600; }}
  .oscore {{ background: #6a1b9a; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; }}
  .ocard-insights {{ margin: 8px 0; padding: 0 0 0 16px; font-size: 12.5px; line-height: 1.5; }}
  .ocard-insights li {{ margin: 4px 0; color: #4a148c; }}
  .trade-card {{ background: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px 14px; margin: 8px 0 8px 20px; }}
  .trade-card .trade-head {{ font-size: 13px; font-weight: bold; }}
  .trade-card .trade-detail {{ font-size: 12px; color: #555; margin-top: 4px; }}
  .trade-card .trade-rationale {{ font-size: 12px; color: #666; font-style: italic; margin-top: 4px; }}
  .strat-badge {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; color: white; }}
  .strat-CASH_SECURED_PUT {{ background: #4caf50; }}
  .strat-CREDIT_PUT_SPREAD {{ background: #1565c0; }}
  .strat-IRON_CONDOR {{ background: #6a1b9a; }}
  .strat-EVENT_WARNING {{ background: #e53935; }}
  .strat-IRON_BUTTERFLY {{ background: #8e24aa; }}
  .strat-BEAR_CALL_SPREAD {{ background: #c62828; }}
  .strat-JADE_LIZARD {{ background: #00695c; }}
  .iv-high {{ background: #c8e6c9; }}
  .iv-mid {{ background: #fff9c4; }}
  .iv-low {{ background: #ffcdd2; }}
  .strat-box {{ background: linear-gradient(135deg, #e8eaf6 0%, #ede7f6 100%); border: 1px solid #9575cd; border-radius: 6px; padding: 10px 14px; margin: 8px 0; }}
  .strat-box .strat-headline {{ font-size: 14px; font-weight: bold; color: #4a148c; }}
  .strat-box .strat-alt {{ font-size: 12px; color: #666; margin-top: 2px; }}
  .strat-box .strat-rationale {{ font-size: 12px; color: #555; margin-top: 4px; font-style: italic; }}
  .strat-list {{ margin: 6px 0 0 0; padding: 0 0 0 16px; }}
  .strat-list li {{ font-size: 12px; color: #333; margin: 4px 0; }}
  .strat-list .strat-name {{ font-weight: 600; color: #311b92; }}
  .strat-list .strat-desc {{ color: #555; }}
  .dir-badge {{ padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; color: white; margin-left: 6px; }}
  .dir-SELL_PREMIUM {{ background: #2e7d32; }}
  .dir-BUY_PREMIUM {{ background: #1565c0; }}
  .dir-NEUTRAL {{ background: #757575; }}
  .dir-WAIT {{ background: #e65100; }}
  .risk-badge {{ font-size: 10px; padding: 1px 5px; border-radius: 3px; margin-left: 4px; }}
  .risk-LOW {{ background: #c8e6c9; color: #2e7d32; }}
  .risk-MODERATE {{ background: #fff9c4; color: #f57f17; }}
  .risk-HIGH {{ background: #ffcdd2; color: #c62828; }}
  .event-row {{ font-size: 12.5px; color: #444; margin: 4px 0 2px 0; }}
  .event-badge {{ padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; color: white; }}
  .event-HIGH {{ background: #e53935; }}
  .event-MEDIUM {{ background: #ff9800; }}
  .event-LOW {{ background: #78909c; }}
  .footer {{ text-align: center; color: #999; font-size: 11px; margin-top: 20px; padding: 20px; }}
  .portfolio-section {{ background: linear-gradient(135deg, #f1f8e9 0%, #e8f5e9 100%); border: 2px solid #2e7d32; border-radius: 12px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .portfolio-section h2 {{ margin-top: 0; color: #1b5e20; border-bottom: 2px solid #2e7d32; padding-bottom: 10px; font-size: 18px; }}
  .portfolio-kpi {{ display: flex; align-items: flex-start; gap: 28px; flex-wrap: wrap; margin-bottom: 14px; }}
  .portfolio-kpi .kpi {{ }}
  .portfolio-kpi .kpi-label {{ font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }}
  .portfolio-kpi .kpi-val {{ font-size: 22px; font-weight: bold; }}
  .portfolio-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  .portfolio-table th {{ background: #c8e6c9; padding: 8px 6px; text-align: left; font-weight: 600; color: #1b5e20; border-bottom: 2px solid #2e7d32; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .portfolio-table td {{ padding: 7px 6px; border-bottom: 1px solid #c8e6c9; }}
  .portfolio-table tr:hover {{ background: #e8f5e9; }}
  .portfolio-total {{ background: #c8e6c9; font-weight: bold; border-top: 2px solid #2e7d32; }}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>Options Premium Advisory</h1>
  <div class="date">{date_str} | Generated at {time_str} | Premium Selling Opportunities</div>
</div>

<div class="disclaimer">
  <strong>DISCLAIMER:</strong> This report provides options research signals only.
  It does NOT constitute financial or investment advice.
  <strong>Options involve risk of substantial loss.</strong>
  All trading decisions are your own responsibility.
</div>
"""
        # Data provenance + screening methodology banner
        html += self._methodology_banner(
            gate_summary, options_results, iv_min_level,
        )

        # Defend existing capital first — open option positions advisory
        html += self._positions_section(positions)

        # Weekly Trade Portfolio (top of report)
        if portfolio and portfolio.get("trades"):
            html += self._portfolio_section(portfolio)
        else:
            html += self._no_trades_banner(gate_summary, iv_min_level)

        # Upcoming macro / economic calendar
        if macro_events:
            html += self._macro_section(macro_events)

        # VIX Overview
        html += self._vix_section(vix_context)

        # Top opportunities
        if top_opportunities:
            html += self._opportunities_section(top_opportunities)

        # IV Heatmap
        if options_results:
            html += self._iv_heatmap_section(options_results)

        # Strategy Backtest (optional)
        if backtest_summary:
            html += (
                '<div class="section"><h2>Strategy Backtest — '
                'Put Credit Spreads</h2>'
                '<p style="font-size:12px;color:#666;">Simulated weekly '
                '30-delta put credit spreads, Black-Scholes priced with the '
                'real IV index. Approximate by construction; past performance '
                'does not guarantee future results.</p>'
                '<pre style="font-size:11px;line-height:1.5;overflow-x:auto;'
                'background:#f8f9fa;border:1px solid #e8e8e8;border-radius:8px;'
                'padding:14px;">'
                f"{backtest_summary}</pre></div>"
            )

        # Footer
        html += f"""
<div class="footer">
  Generated by Trading AI Options Advisory | {date_str} {time_str}<br>
  Research signals only — not financial advice. Options involve risk of loss.
</div>

</div>
</body>
</html>"""

        # Save
        os.makedirs(REPORT_DIR, exist_ok=True)
        filename = f"options_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(REPORT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"Options report saved to {filepath}")

        return html

    # ------------------------------------------------------------------ #
    # Sections
    # ------------------------------------------------------------------ #

    def _methodology_banner(
        self, gate_summary: dict, options_results: list[dict],
        iv_min_level: float,
    ) -> str:
        """Explain the screen + prove the premium provenance (MooMoo/real-time)."""
        gs = gate_summary or {}
        rt = gs.get("realtime_available")
        as_of = gs.get("as_of")
        n_names = len(options_results or [])

        if rt:
            src_bg, src_fg, src_border = "#e8f5e9", "#1b5e20", "#2e7d32"
            src_icon = "&#x1F7E2;"  # green circle
            src_txt = (
                f"<strong>Premiums confirmed on MooMoo real-time data</strong>"
                + (f" &mdash; quotes as of <strong>{as_of} ET</strong>" if as_of else "")
                + f". {gs.get('confirmed', 0)} of {gs.get('candidates', 0)} "
                f"candidate legs priced on the live book."
            )
        else:
            src_bg, src_fg, src_border = "#fff3e0", "#e65100", "#fb8c00"
            src_icon = "&#x1F7E0;"  # orange
            src_txt = (
                "<strong>MooMoo OpenD was unreachable at run time</strong> &mdash; "
                "premiums below are yfinance <em>indicative</em> quotes, "
                "NOT real-time confirmed. Start OpenD before the open to get "
                "actual fills. No trade is marked high-probability without "
                "real-time confirmation."
            )

        return f"""
<div class="section" style="border-left:5px solid {src_border};">
  <h2>How these picks were selected</h2>
  <div style="font-size:12.5px; line-height:1.7; color:#444;">
    <div style="background:{src_bg}; color:{src_fg}; border-radius:8px; padding:10px 14px; margin-bottom:10px;">
      {src_icon} {src_txt}
    </div>
    <strong>1. IV screen &mdash;</strong> only names with ATM implied volatility
    <strong>&gt; {iv_min_level*100:.0f}%</strong> (absolute level) are considered.
    <strong>{n_names}</strong> name{'s' if n_names != 1 else ''} passed today.<br>
    <strong>2. Real-time premium &mdash;</strong> the actual bid/ask of every leg
    is pulled from MooMoo at the US open to compute the true net credit.<br>
    <strong>3. High-probability gate &mdash;</strong> a trade is only recommended
    if its POP (on the real premium) is <strong>&ge; {OPTIONS_MIN_POP:.0f}%</strong>, IV exceeds
    realized vol, the chain is liquid, and no earnings land before expiry.<br>
    <strong>4. Event overlay &mdash;</strong> upcoming company, sector, and US
    macro catalysts (FOMC/CPI/jobs) are checked against each expiry.
  </div>
</div>
"""

    def _no_trades_banner(self, gate_summary: dict, iv_min_level: float) -> str:
        """Shown when nothing clears the high-probability gate."""
        gs = gate_summary or {}
        n = gs.get("candidates", 0)
        return f"""
<div class="portfolio-section" style="border-color:#f57f17;">
  <h2 style="color:#e65100; border-color:#f57f17;">No high-probability trades today</h2>
  <div style="font-size:13px; color:#555; line-height:1.7;">
    Nothing cleared the full screen today: <strong>ATM IV &gt; {iv_min_level*100:.0f}%</strong>
    &rarr; real-time premium confirmation &rarr; <strong>POP &ge; {OPTIONS_MIN_POP:.0f}%</strong> with
    IV&gt;HV, liquid strikes, and no binary event before expiry.
    {f'{n} candidate trade(s) were evaluated but none passed the probability gate.' if n else 'No names passed the IV level screen.'}
    <br><br>
    This is by design &mdash; the advisory only recommends when the odds are
    genuinely in your favor. A quiet day is a valid signal to hold cash.
  </div>
</div>
"""

    def _positions_section(self, positions: list) -> str:
        """Defensive advisory for the trader's OPEN option positions."""
        if positions is None:
            return ""  # not fetched (RT off / OpenD down) — stay silent
        if not positions:
            return (
                '<div class="section"><h2>🛡️ Manage Your Open Option Trades</h2>'
                '<p style="font-size:13px;color:#555;">No open option positions '
                'found in your MooMoo account. Nothing to defend today.</p></div>'
            )

        verdict_style = {
            "CLOSE / DEFEND NOW": ("#c62828", "#ffebee"),
            "CLOSE — SALVAGE": ("#c62828", "#ffebee"),
            "DEFEND — ROLL / HEDGE": ("#e65100", "#fff3e0"),
            "TAKE PROFIT": ("#2e7d32", "#e8f5e9"),
            "HOLD & MONITOR": ("#f57f17", "#fff8e1"),
            "HOLD": ("#546e7a", "#eceff1"),
        }

        cards = ""
        for p in positions:
            a = p.get("assessment", {})
            v = a.get("verdict", "HOLD")
            vfg, vbg = verdict_style.get(v, ("#546e7a", "#eceff1"))
            upl = p.get("unrealized_pl", 0.0)
            upl_color = "#2e7d32" if upl >= 0 else "#c62828"
            spot = p.get("spot")
            iv = p.get("iv")
            delta = p.get("delta")
            cushion = a.get("cushion_pct")
            captured = a.get("captured_pct")

            metric_bits = [
                f"Spot: <strong>${spot:,.2f}</strong>" if spot else "",
                f"Entry: ${p.get('entry_price',0):.2f}",
                f"Now: ${p.get('cur_price',0):.2f}",
                (f"Unreal. P&amp;L: <strong style='color:{upl_color};'>"
                 f"${upl:,.0f} ({p.get('pl_ratio',0):.0f}%)</strong>"),
                f"IV: {iv*100:.0f}%" if iv else "",
                f"Δ: {delta:.2f}" if delta is not None else "",
                f"Cushion: {cushion:.1f}% OTM" if cushion is not None else "",
                f"BE: ${a['breakeven']:.2f}" if a.get("breakeven") else "",
                f"{p.get('dte','?')} DTE",
            ]
            metrics = " &nbsp;|&nbsp; ".join(m for m in metric_bits if m)

            flags = a.get("flags") or []
            flag_html = ""
            if flags:
                flag_html = "".join(
                    f'<span style="background:#c62828; color:#fff; padding:1px 6px; '
                    f'border-radius:3px; font-size:10px; margin-right:5px;">'
                    f'&#x26A0;&#xFE0F; {f}</span>' for f in flags
                )

            actions = a.get("actions") or []
            act_html = "".join(f"<li>{act}</li>" for act in actions)

            note = a.get("note")
            note_html = (
                f'<div style="font-size:11px; color:#6a1b9a; margin-top:5px;">'
                f'ℹ️ {note}</div>' if note else ""
            )

            cards += f"""
          <div style="border:1px solid #e0e0e0; border-left:5px solid {vfg}; border-radius:8px; padding:14px 16px; margin:12px 0; background:#fafafa;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <div style="font-size:15px; font-weight:700; color:#1a1a2e;">
                {p['side']} {p['contracts']}&times; {p['underlying']} ${p['strike']:.0f} {p['type']}
                <span style="font-size:12px; color:#888; font-weight:400;">exp {p['expiry']}</span>
              </div>
              <span style="background:{vbg}; color:{vfg}; padding:3px 12px; border-radius:14px; font-size:13px; font-weight:700;">
                {v}
              </span>
            </div>
            <div style="font-size:12px; color:#444; margin:8px 0;">{metrics}</div>
            {f'<div style="margin:6px 0;">{flag_html}</div>' if flag_html else ''}
            <div style="font-size:12.5px; color:#333; font-weight:600; margin-top:6px;">Recommended action:</div>
            <ul style="margin:4px 0 0 0; padding-left:20px; font-size:12.5px; line-height:1.6; color:#333;">{act_html}</ul>
            {note_html}
          </div>"""

        return f"""
<div class="section" style="border-left:5px solid #6a1b9a;">
  <h2>🛡️ Manage Your Open Option Trades</h2>
  <p style="font-size:12px; color:#666; margin-top:0;">
    Live positions pulled from your MooMoo account with real-time quotes.
    Each carries a defensive recommendation to protect against losses &mdash;
    take profit, close early, roll, or add a hedge. Advisory only; no orders
    are placed for you.
  </p>
  {cards}
</div>
"""

    def _macro_section(self, macro_events: list[dict]) -> str:
        """Upcoming US macro/economic catalysts (market-wide context)."""
        rows = ""
        for e in macro_events[:8]:
            impact = e.get("impact", "MEDIUM")
            approx = " (approx)" if e.get("approx") else ""
            rows += f"""
    <tr>
      <td style="white-space:nowrap;"><strong>{e['date']}</strong>
        <span style="color:#888; font-size:11px;">({e['days_away']}d){approx}</span></td>
      <td><span class="event-badge event-{impact}">{impact}</span></td>
      <td>{e['event']}</td>
      <td style="font-size:11.5px; color:#666;">{e.get('note','')}</td>
    </tr>"""
        return f"""
<div class="section">
  <h2>Upcoming Market &amp; Economic Catalysts</h2>
  <p style="font-size:12px; color:#666; margin-top:0;">
    Scheduled events that can move the whole tape &mdash; weigh these against
    any expiry that straddles them. FOMC dates are exact; monthly releases are
    approximate.
  </p>
  <table>
    <tr><th>Date</th><th>Impact</th><th>Event</th><th>Why it matters</th></tr>
    {rows}
  </table>
</div>
"""

    _PTABLE_HEADER = """
  <table class="portfolio-table">
    <tr>
      <th style="width:28px;">#</th>
      <th>Ticker</th>
      <th>Risk</th>
      <th>Strategy</th>
      <th>Trade to Execute</th>
      <th style="text-align:center;">Qty</th>
      <th style="text-align:right;">Prem/Ct</th>
      <th style="text-align:right;">Total Prem</th>
      <th style="text-align:right;">Running&nbsp;Total</th>
      <th style="text-align:right;">Max&nbsp;Loss</th>
      <th style="text-align:center;">R/R</th>
      <th style="text-align:center;">POP</th>
      <th>Remark</th>
    </tr>
"""

    def _portfolio_rows(self, trades, start_index: int, start_running: float):
        """Render <tr> rows for a list of portfolio trades.

        Returns (rows_html, next_index, running_total).
        """
        html = ""
        running_total = start_running
        i = start_index
        tier_badge_map = {
            "conservative": ("🛡️", "#e8f5e9", "#2e7d32"),
            "moderate": ("⚖️", "#fff8e1", "#f57f17"),
            "aggressive": ("⚡", "#ffebee", "#c62828"),
        }
        for t in trades:
            running_total += t["total_premium"]
            strat = t["strategy"]
            trade_rr = (
                f"1:{t['max_loss_per_contract'] / t['premium_per_contract']:.1f}"
                if t["premium_per_contract"] > 0 else "N/A"
            )
            tier = t.get("risk_tier", "moderate")
            tier_icon, tier_bg, tier_fg = tier_badge_map.get(
                tier, ("", "#f5f5f5", "#555")
            )
            em_pct = t.get("expected_move_pct")
            daily_pct = t.get("daily_move_pct")
            events = t.get("events_before_expiry", [])
            move_line = ""
            if daily_pct:
                move_line += f"ATR: {daily_pct:.1f}%/d"
            if em_pct:
                move_line += f" · ±{em_pct:.1f}%/{t.get('dte', '?')}d"
            event_badges = ""
            if events:
                evt_colors = {
                    "Earnings Report": "#c62828",
                    "FOMC Decision": "#1565c0",
                    "Ex-Dividend": "#6a1b9a",
                }
                for evt in events[:2]:
                    ec = evt_colors.get(evt, "#555")
                    short = evt.replace(" Report", "").replace(" Decision", "")
                    event_badges += (
                        f'<span style="display:inline-block; padding:1px 4px; '
                        f'border-radius:3px; font-size:8px; background:{ec}; '
                        f'color:#fff; margin-top:2px;">{short}</span> '
                    )
            html += f"""
    <tr style="background:{tier_bg}40;">
      <td style="font-weight:600; color:#555;">{i}</td>
      <td>
        <strong>{t['ticker']}</strong><br>
        <span style="font-size:10.5px; color:#888;">${t['current_price']:,.2f}</span>
        {'<br><span style="font-size:9px; color:#1565c0;">' + move_line + '</span>' if move_line else ''}
        {'<br>' + event_badges if event_badges else ''}
      </td>
      <td style="text-align:center;">
        <span style="display:inline-block; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600; background:{tier_bg}; color:{tier_fg};">
          {tier_icon} {tier.title()}
        </span>
      </td>
      <td><span class="strat-badge strat-{strat}">{t['strategy_display']}</span></td>
      <td style="font-size:11.5px;">{t['action']}</td>
      <td style="text-align:center; font-weight:700;">{t['contracts']}</td>
      <td style="text-align:right;">${t['premium_per_contract']:,.0f}</td>
      <td style="text-align:right; font-weight:600; color:#2e7d32;">
        ${t['total_premium']:,.0f}
      </td>
      <td style="text-align:right; font-weight:600;">
        ${running_total:,.0f}
      </td>
      <td style="text-align:right; color:#c62828;">${t['total_max_loss']:,.0f}</td>
      <td style="text-align:center; font-size:11px;">{trade_rr}</td>
      <td style="text-align:center; font-size:11px; font-weight:600; color:{'#2e7d32' if (t.get('pop') or 0) >= OPTIONS_MIN_POP else '#f57f17' if (t.get('pop') or 0) >= OPTIONS_MIN_POP - 10 else '#c62828'};">
        {f"{t['pop']:.0f}%" if t.get('pop') else '—'}
      </td>
      <td style="font-size:11px; color:#555;">{t.get('remark','')}</td>
    </tr>"""
            i += 1
        return html, i, running_total

    def _portfolio_section(self, portfolio: dict) -> str:
        """Weekly trade portfolio summary — appears at the top of the report.

        Renders two parts: Part 1 (high-conviction, gated) and Part 2
        (target fillers), toward the weekly premium target.
        """
        if not portfolio or not portfolio.get("trades"):
            return ""

        trades = portfolio["trades"]
        core_trades = portfolio.get(
            "core_trades", [t for t in trades if t.get("part") != "fill"]
        )
        fill_trades = portfolio.get(
            "fill_trades", [t for t in trades if t.get("part") == "fill"]
        )
        core_prem = portfolio.get(
            "core_premium", sum(t["total_premium"] for t in core_trades)
        )
        fill_prem = portfolio.get(
            "fill_premium", sum(t["total_premium"] for t in fill_trades)
        )
        total_prem = portfolio["total_premium"]
        total_contracts = portfolio["total_contracts"]
        target = portfolio["target"]
        pct = portfolio["pct_of_target"]
        core_pct = portfolio.get("core_pct_of_target",
                                 round(core_prem / target * 100, 1) if target else 0)
        total_max_loss = portfolio.get("total_max_loss", 0)
        max_contracts = portfolio.get("max_contracts", 40)
        fill_min_pop = portfolio.get("fill_min_pop", max(OPTIONS_MIN_POP - 15.0, 0.0))

        # Color for target achievement
        if pct >= 100:
            target_color = "#2e7d32"
            target_icon = "&#x2705;"
        elif pct >= 75:
            target_color = "#f57f17"
            target_icon = "&#x1F7E1;"
        else:
            target_color = "#c62828"
            target_icon = "&#x1F534;"

        portfolio_rr = (
            f"1:{total_max_loss / total_prem:.1f}" if total_prem > 0 else "N/A"
        )

        html = f"""
<div class="portfolio-section">
  <h2>{target_icon} Weekly Trade Portfolio &mdash; Target: ${target:,.0f}/week</h2>

  <div class="portfolio-kpi">
    <div class="kpi">
      <div class="kpi-label">Total Premium</div>
      <div class="kpi-val" style="color: {target_color};">${total_prem:,.0f}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">% of Target</div>
      <div class="kpi-val">{pct:.0f}%</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Contracts</div>
      <div class="kpi-val">{total_contracts} / {max_contracts}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Total Max Risk</div>
      <div class="kpi-val" style="color: #c62828;">${total_max_loss:,.0f}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Portfolio R/R</div>
      <div class="kpi-val">{portfolio_rr}</div>
    </div>
  </div>

  <div style="display:flex; gap:24px; flex-wrap:wrap; font-size:12px; margin:4px 0 14px; padding:8px 12px; background:#ffffff90; border-radius:8px;">
    <span>&#x2705; <strong>Part 1 — High-conviction:</strong>
      <strong style="color:#1b5e20;">${core_prem:,.0f}</strong> ({core_pct:.0f}% of target)</span>
    <span>&#x2691; <strong>Part 2 — Target fillers:</strong>
      <strong style="color:#e65100;">${fill_prem:,.0f}</strong>
      ({(pct - core_pct):.0f}% of target)</span>
  </div>
"""
        running = 0.0
        idx = 1

        # ---- Part 1: high-conviction ----
        if core_trades:
            rows, idx, running = self._portfolio_rows(core_trades, idx, running)
            html += f"""
  <div style="font-size:13px; font-weight:700; color:#1b5e20; margin:6px 0 2px;">
    Part 1 &mdash; High-Conviction &nbsp;<span style="font-weight:400; color:#555; font-size:11px;">
    (POP&nbsp;&ge;&nbsp;{OPTIONS_MIN_POP:.0f}%, real-time confirmed, IV&gt;HV, no binary event)</span>
  </div>
  {self._PTABLE_HEADER}{rows}
    <tr class="portfolio-total">
      <td colspan="7" style="text-align:right; padding-right:12px;">Part 1 subtotal</td>
      <td style="text-align:right; color:#1b5e20;">${core_prem:,.0f}</td>
      <td colspan="5"></td>
    </tr>
  </table>
"""

        # ---- Part 2: target fillers ----
        if fill_trades:
            rows, idx, running = self._portfolio_rows(fill_trades, idx, running)
            html += f"""
  <div style="font-size:13px; font-weight:700; color:#e65100; margin:14px 0 2px;">
    Part 2 &mdash; Target Fillers &nbsp;<span style="font-weight:400; color:#555; font-size:11px;">
    (confirmed real-time premium, POP {fill_min_pop:.0f}&ndash;{OPTIONS_MIN_POP:.0f}% &mdash; added to reach the ${target:,.0f} target; lower conviction)</span>
  </div>
  {self._PTABLE_HEADER}{rows}
    <tr class="portfolio-total">
      <td colspan="7" style="text-align:right; padding-right:12px;">Part 2 subtotal</td>
      <td style="text-align:right; color:#e65100;">${fill_prem:,.0f}</td>
      <td colspan="5"></td>
    </tr>
  </table>
"""

        html += f"""
  <div style="margin-top:12px; font-size:14px; font-weight:700; color:#1b5e20; text-align:right;">
    Combined premium: ${total_prem:,.0f} &nbsp;/&nbsp; ${target:,.0f} target
    ({pct:.0f}%) &nbsp;|&nbsp; {total_contracts} contracts &nbsp;|&nbsp;
    Max risk <span style="color:#c62828;">${total_max_loss:,.0f}</span>
  </div>

  <div style="margin-top:10px; font-size:11px; color:#555; border-top:1px solid #a5d6a7; padding-top:8px;">
    &#x2705; <strong>Part 1</strong> trades cleared the full high-probability gate
    (POP&nbsp;&ge;&nbsp;{OPTIONS_MIN_POP:.0f}% on <strong>MooMoo real-time premium</strong>, IV&gt;HV,
    liquid strikes, no binary event before expiry).
    &#x2691; <strong>Part 2</strong> trades are real-time-priced near-misses
    (POP&nbsp;{fill_min_pop:.0f}&ndash;{OPTIONS_MIN_POP:.0f}%) added only to reach the ${target:,.0f}
    weekly target &mdash; treat them as lower conviction and size accordingly.
    Premium is the confirmed net credit; actual fills may vary. Max
    {max_contracts} contracts for margin. <strong>NOT financial advice.</strong>
  </div>
</div>
"""
        return html

    def _vix_section(self, ctx: dict) -> str:
        """Compact VIX / volatility regime strip."""
        if not ctx:
            return ""

        regime = ctx.get("regime", "NORMAL")
        html = '<div class="section" style="padding:16px 24px;">'
        html += '<div class="vix-strip">'
        html += (
            f'<div><div class="vix-label">VIX</div>'
            f'<div class="vix-val">{ctx.get("vix", "—")}</div></div>'
        )
        html += (
            f'<div><div class="vix-label">20-Day Avg</div>'
            f'<div style="font-size:18px; font-weight:600;">'
            f'{ctx.get("vix_sma_20", "—")}</div></div>'
        )
        html += (
            f'<div><div class="vix-label">52W Range</div>'
            f'<div style="font-size:14px;">'
            f'{ctx.get("vix_52w_low", "—")} – {ctx.get("vix_52w_high", "—")}</div></div>'
        )
        html += (
            f'<div><div class="vix-label">Percentile</div>'
            f'<div style="font-size:18px; font-weight:600;">'
            f'{ctx.get("vix_percentile", "—")}%</div></div>'
        )
        html += (
            f'<div><span class="regime-badge regime-{regime}">'
            f'{regime.replace("_", " ")}</span></div>'
        )
        html += "</div>"
        html += (
            f'<div style="font-size:13px; color:#555; margin-top:8px;">'
            f'{ctx.get("regime_desc", "")}</div>'
        )
        html += "</div>"
        return html

    def _opportunities_section(self, opps: list[dict]) -> str:
        """Top premium selling opportunity cards with trade ideas."""
        html = '<div class="section">'
        html += '<h2>Top Premium Selling Opportunities</h2>'
        html += (
            '<p style="font-size:13px; color:#666; margin-bottom:14px;">'
            "Stocks/indices where implied volatility is elevated relative to "
            "realized volatility — options are overpriced, making premium "
            "selling strategies (puts, spreads, condors) attractive.</p>"
        )

        for opp in opps[:15]:
            iv_str = f"{opp['atm_iv']*100:.1f}%" if opp.get("atm_iv") else "N/A"
            hv_str = f"{opp['hv_20']*100:.1f}%" if opp.get("hv_20") else "N/A"
            prem_str = ""
            if opp.get("iv_premium") is not None:
                p = opp["iv_premium"] * 100
                css = "high" if p > 0 else "warn"
                prem_str = f'<span class="{css}">IV−HV: {p:+.1f}pp</span>'

            pctile_str = f"IV%ile: {opp['iv_percentile']:.0f}%" if opp.get("iv_percentile") is not None else ""
            rank_str = f"IV Rank: {opp['iv_rank']:.0f}%" if opp.get("iv_rank") is not None else ""
            move_str = f"Implied Move: {opp['implied_move_pct']:.1f}%" if opp.get("implied_move_pct") else ""
            oi_total = (opp.get("total_call_oi", 0) or 0) + (opp.get("total_put_oi", 0) or 0)
            oi_str = f"OI: {oi_total:,}" if oi_total else ""

            metrics = " | ".join(
                m for m in [
                    f"IV: {iv_str}",
                    f"HV(20d): {hv_str}",
                    prem_str,
                    pctile_str,
                    rank_str,
                    move_str,
                    oi_str,
                ] if m
            )

            html += f"""
            <div class="ocard">
              <div class="ocard-head">
                {opp['ticker']} — {opp.get('name', opp['ticker'])}
                <span class="oscore">Score: {opp['premium_score']}/100</span>
                <span style="font-size:13px; color:#555; margin-left:8px;">
                  ${opp['current_price']:,.2f}
                </span>
              </div>
              <div class="ocard-metrics">{metrics}</div>"""

            # Trader read: news tone + options positioning + hold quality
            pos = opp.get("options_positioning") or {}
            hq = opp.get("hold_quality") or {}
            ns = opp.get("news_sentiment") or {}
            bias = opp.get("trader_bias") or pos.get("label") or "Neutral"
            bias_color = {
                "Bullish": "#2e7d32", "Lean Bullish": "#558b2f",
                "Neutral": "#757575", "Lean Bearish": "#ef6c00",
                "Bearish": "#c62828",
            }.get(bias, "#757575")
            read_parts = [
                f'<strong style="color:{bias_color};">Trader bias: {bias}</strong>'
            ]
            if pos.get("note"):
                read_parts.append(f'Options: {pos.get("label", "")} ({pos["note"]})')
            if hq.get("label"):
                sc = f' ({hq["score"]})' if hq.get("score") is not None else ""
                read_parts.append(f'Hold quality: {hq["label"]}{sc}')
            if ns.get("label") and ns.get("n"):
                read_parts.append(f'News: {ns["label"]} ({ns.get("n", 0)} headlines)')
            html += (
                '<div style="font-size:11.5px; color:#333; margin:4px 0;">&#x1F9ED; '
                + " | ".join(read_parts) + "</div>"
            )
            heads = ns.get("headlines") or []
            if heads:
                html += '<div style="font-size:10.5px; color:#777; margin:2px 0 4px;">'
                for h in heads[:2]:
                    title = str(h.get("title", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    age = f' ({h["age_days"]:.0f}d ago)' if h.get("age_days") is not None else ""
                    html += f'&#x1F4F0; {title}{age}<br>'
                html += "</div>"

            # Sector / segment catalyst context
            if opp.get("sector_note"):
                sector_lbl = opp.get("sector") or "Sector"
                html += (
                    f'<div style="font-size:11.5px; color:#4a148c; margin:2px 0 4px 0;">'
                    f'🏭 <strong>{sector_lbl}:</strong> {opp["sector_note"]}</div>'
                )

            # Strategy suggestion box (always present)
            ss = opp.get("strategy_suggestion") or {}
            if ss:
                direction = ss.get("direction", "NEUTRAL")
                html += f"""
              <div class="strat-box">
                <div class="strat-headline">
                  🎯 {ss.get('primary', 'N/A')}
                  <span class="dir-badge dir-{direction}">{direction.replace('_', ' ')}</span>
                </div>"""
                if ss.get("secondary"):
                    html += f'<div class="strat-alt">Alt: {ss["secondary"]}</div>'
                if ss.get("rationale"):
                    html += f'<div class="strat-rationale">{ss["rationale"]}</div>'
                if ss.get("event_note"):
                    html += (
                        f'<div style="font-size:11.5px; color:#c62828; '
                        f'font-weight:600; margin-top:3px;">'
                        f'⚠️ {ss["event_note"]}</div>'
                    )
                # Strategy list
                strats = ss.get("strategies") or []
                if strats:
                    html += '<ul class="strat-list">'
                    for s in strats[:4]:
                        risk = s.get("risk_level", "MODERATE")
                        html += (
                            f'<li><span class="strat-name">{s["name"]}</span>'
                            f' <span class="risk-badge risk-{risk}">{risk}</span>'
                            f' — <span class="strat-desc">{s["description"]}</span></li>'
                        )
                    html += '</ul>'
                html += '</div>'

            # Price range row
            pr = opp.get("price_ranges") or {}
            if pr:
                range_parts = []
                for label, key in [("1W", "range_1w"), ("2W", "range_2w"), ("1M", "range_1m")]:
                    rng = pr.get(key)
                    if rng:
                        pct = rng["spread_pct"]
                        css = "high" if pct >= 8 else ("warn" if pct >= 15 else "")
                        range_parts.append(
                            f'<span style="margin-right:16px;">'
                            f'<strong>{label}:</strong> '
                            f'${rng["low"]:,.2f} – ${rng["high"]:,.2f} '
                            f'(<span class="{css}">{pct:.1f}%</span>)'
                            f'</span>'
                        )
                if range_parts:
                    html += (
                        '<div style="font-size:12.5px; color:#444; margin:4px 0 2px 0;">'
                        '📊 <strong>Price Range:</strong> '
                        + "".join(range_parts)
                        + '</div>'
                    )

            # Upcoming events
            events = opp.get("upcoming_events") or []
            if events:
                html += '<div class="event-row">📅 <strong>Upcoming Events:</strong></div>'
                for ev in events[:3]:
                    impact = ev.get("impact", "MEDIUM")
                    move_part = ""
                    if ev.get("est_move"):
                        move_part = f' (est. ±{ev["est_move"]:.1f}%)'
                    html += (
                        f'<div style="font-size:12px; color:#333; margin:2px 0 2px 20px;">'
                        f'<span class="event-badge event-{impact}">{impact}</span> '
                        f'<strong>{ev["event"]}</strong> — {ev["date"]} '
                        f'({ev["days_away"]}d away){move_part}'
                        f'<div style="font-size:11.5px; color:#666; margin:1px 0 0 0;">'
                        f'{ev["note"]}</div></div>'
                    )

            # Insights
            if opp.get("insights"):
                html += '<ul class="ocard-insights">'
                for ins in opp["insights"][:4]:
                    html += f"<li>{ins}</li>"
                html += "</ul>"

            # Trade recommendations
            for trade in opp.get("trades", [])[:3]:
                strat = trade.get("strategy", "")
                if strat == "EVENT_WARNING":
                    # Warning-only card — no premium/loss metrics
                    html += f"""
                <div class="trade-card" style="border-left: 3px solid #e53935;">
                  <div class="trade-head">
                    <span class="strat-badge strat-{strat}">{trade.get('strategy_display','')}</span>
                    {trade.get('action','')}
                  </div>
                  <div class="trade-rationale">{trade.get('rationale','')}</div>
                </div>"""
                else:
                    # Provenance + probability badges
                    src = trade.get("premium_source", "")
                    confirmed = trade.get("confirmed")
                    high_prob = trade.get("high_prob")
                    pop = trade.get("pop")
                    if confirmed:
                        src_badge = (
                            '<span style="background:#e8f5e9;color:#1b5e20;'
                            'padding:1px 6px;border-radius:4px;font-size:10px;'
                            'font-weight:600;">&#x1F7E2; MooMoo real-time'
                            + (f" &middot; {trade.get('as_of')}" if trade.get('as_of') else "")
                            + '</span>'
                        )
                    else:
                        src_badge = (
                            '<span style="background:#fff3e0;color:#e65100;'
                            'padding:1px 6px;border-radius:4px;font-size:10px;'
                            f'font-weight:600;">&#x1F7E0; {src or "indicative"}</span>'
                        )
                    if high_prob:
                        hp_badge = (
                            '<span style="background:#2e7d32;color:#fff;'
                            'padding:1px 6px;border-radius:4px;font-size:10px;'
                            'font-weight:700;margin-left:4px;">&#x2705; HIGH-PROBABILITY</span>'
                        )
                    else:
                        reasons = trade.get("gate_reasons") or []
                        why = (" — " + "; ".join(reasons)) if reasons else ""
                        hp_badge = (
                            '<span style="background:#eceff1;color:#546e7a;'
                            'padding:1px 6px;border-radius:4px;font-size:10px;'
                            f'font-weight:600;margin-left:4px;" title="{why}">Not gated{why}</span>'
                        )
                    pop_str = (
                        f'| POP: <strong style="color:{"#2e7d32" if (pop or 0) >= OPTIONS_MIN_POP else "#f57f17"};">'
                        f'{pop:.0f}%</strong>' if pop is not None else ""
                    )
                    # Macro/sector caution for this expiry
                    macro_hi = trade.get("macro_high_impact") or []
                    macro_line = ""
                    if macro_hi:
                        names = ", ".join(e["event"] for e in macro_hi[:3])
                        macro_line = (
                            f'<div style="font-size:11px;color:#c62828;margin-top:3px;">'
                            f'&#x26A0;&#xFE0F; Event risk before expiry: {names}</div>'
                        )
                    html += f"""
                <div class="trade-card">
                  <div class="trade-head">
                    <span class="strat-badge strat-{strat}">{trade.get('strategy_display','')}</span>
                    {trade.get('action','')}
                  </div>
                  <div style="margin:4px 0;">{src_badge}{hp_badge}</div>
                  <div class="trade-detail">
                    Premium: <strong>${trade.get('premium',0):.2f}</strong>/share
                    | Max Profit: ${trade.get('max_profit',0):,.0f}
                    | Max Loss: ${trade.get('max_loss',0):,.0f}
                    | Breakeven: ${trade.get('breakeven', trade.get('breakeven_low') or 0):,.2f}
                    {pop_str}
                    {f"| R/R: {trade['risk_reward']}" if trade.get('risk_reward') else ""}
                  </div>
                  {macro_line}
                  <div class="trade-rationale">{trade.get('rationale','')}</div>
                </div>"""

            html += "</div>"

        html += "</div>"
        return html

    def _iv_heatmap_section(self, results: list[dict]) -> str:
        """Table of all scanned tickers with IV metrics."""
        html = '<div class="section">'
        html += '<h2>IV Heatmap — All Scanned Tickers</h2>'
        html += """<table>
        <tr>
          <th>Ticker</th><th>Price</th><th>ATM IV</th><th>HV(20d)</th>
          <th>IV-HV</th><th>IV %ile</th><th>IV Rank</th>
          <th>P/C OI</th><th>Impl. Move</th><th>Score</th>
        </tr>"""

        # Sort by premium score
        sorted_r = sorted(results, key=lambda x: x.get("premium_score", 0), reverse=True)
        for r in sorted_r:
            iv = r.get("atm_iv")
            hv = r.get("hv_20")
            prem = r.get("iv_premium")

            iv_str = f"{iv*100:.1f}%" if iv else "—"
            hv_str = f"{hv*100:.1f}%" if hv else "—"

            # Color-code IV premium
            if prem is not None:
                if prem > 0.10:
                    prem_css = "iv-high"
                elif prem > 0:
                    prem_css = "iv-mid"
                else:
                    prem_css = "iv-low"
                prem_str = f"{prem*100:+.1f}pp"
            else:
                prem_css = ""
                prem_str = "—"

            pctile = r.get("iv_percentile")
            pctile_str = f"{pctile:.0f}%" if pctile is not None else "—"
            rank = r.get("iv_rank")
            rank_str = f"{rank:.0f}%" if rank is not None else "—"
            pc = r.get("pc_oi_ratio")
            pc_str = f"{pc:.2f}" if pc else "—"
            move = r.get("implied_move_pct")
            move_str = f"{move:.1f}%" if move else "—"
            score = r.get("premium_score", 0)

            html += f"""<tr>
              <td><strong>{r['ticker']}</strong></td>
              <td>${r['current_price']:,.2f}</td>
              <td>{iv_str}</td>
              <td>{hv_str}</td>
              <td class="{prem_css}" style="font-weight:600;">{prem_str}</td>
              <td>{pctile_str}</td>
              <td>{rank_str}</td>
              <td>{pc_str}</td>
              <td>{move_str}</td>
              <td><strong>{score}</strong></td>
            </tr>"""

        html += "</table></div>"
        return html

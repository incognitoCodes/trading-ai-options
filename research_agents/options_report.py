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

from research_agents.config import REPORT_DIR

logger = logging.getLogger(__name__)


class OptionsReportGenerator:
    """Generates HTML options advisory reports."""

    def generate(
        self,
        vix_context: dict,
        options_results: list[dict],
        top_opportunities: list[dict],
        portfolio: dict = None,
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
        # Weekly Trade Portfolio (top of report)
        if portfolio:
            html += self._portfolio_section(portfolio)

        # VIX Overview
        html += self._vix_section(vix_context)

        # Top opportunities
        if top_opportunities:
            html += self._opportunities_section(top_opportunities)

        # IV Heatmap
        if options_results:
            html += self._iv_heatmap_section(options_results)

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

    def _portfolio_section(self, portfolio: dict) -> str:
        """Weekly trade portfolio summary — appears at the top of the report."""
        if not portfolio or not portfolio.get("trades"):
            return ""

        trades = portfolio["trades"]
        total_prem = portfolio["total_premium"]
        total_contracts = portfolio["total_contracts"]
        target = portfolio["target"]
        pct = portfolio["pct_of_target"]
        total_max_loss = portfolio.get("total_max_loss", 0)
        max_contracts = portfolio.get("max_contracts", 40)

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

        # Portfolio-level R/R
        portfolio_rr = (
            f"1:{total_max_loss / total_prem:.1f}"
            if total_prem > 0 else "N/A"
        )

        # Tier breakdown
        tier_data = portfolio.get("tier_breakdown", {})
        agg_prem = tier_data.get("aggressive", 0)
        mod_prem = tier_data.get("moderate", 0)
        con_prem = tier_data.get("conservative", 0)
        agg_pct = round(agg_prem / total_prem * 100) if total_prem > 0 else 0
        mod_pct = round(mod_prem / total_prem * 100) if total_prem > 0 else 0
        con_pct = 100 - agg_pct - mod_pct if total_prem > 0 else 0

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

  <!-- Risk Tier Breakdown Bar -->
  <div style="margin:12px 0 16px; padding:0 4px;">
    <div style="font-size:11px; font-weight:600; color:#444; margin-bottom:6px;">
      Risk Allocation
    </div>
    <div style="display:flex; height:22px; border-radius:6px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.15);">
      <div style="width:{con_pct}%; background:#2e7d32; color:#fff; font-size:10px; display:flex; align-items:center; justify-content:center; min-width:{20 if con_pct > 0 else 0}px;">
        {f'🛡️ {con_pct}%' if con_pct > 8 else ''}
      </div>
      <div style="width:{mod_pct}%; background:#f57f17; color:#fff; font-size:10px; display:flex; align-items:center; justify-content:center; min-width:{20 if mod_pct > 0 else 0}px;">
        {f'⚖️ {mod_pct}%' if mod_pct > 8 else ''}
      </div>
      <div style="width:{agg_pct}%; background:#c62828; color:#fff; font-size:10px; display:flex; align-items:center; justify-content:center; min-width:{20 if agg_pct > 0 else 0}px;">
        {f'⚡ {agg_pct}%' if agg_pct > 8 else ''}
      </div>
    </div>
    <div style="display:flex; justify-content:space-between; font-size:10px; color:#666; margin-top:4px;">
      <span>🛡️ Conservative ${con_prem:,.0f}</span>
      <span>⚖️ Moderate ${mod_prem:,.0f}</span>
      <span>⚡ Aggressive ${agg_prem:,.0f}</span>
    </div>
  </div>

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
        running_total = 0.0
        for i, t in enumerate(trades, 1):
            running_total += t["total_premium"]
            strat = t["strategy"]
            trade_rr = (
                f"1:{t['max_loss_per_contract'] / t['premium_per_contract']:.1f}"
                if t["premium_per_contract"] > 0 else "N/A"
            )

            tier = t.get("risk_tier", "moderate")
            tier_badge_map = {
                "conservative": ("🛡️", "#e8f5e9", "#2e7d32"),
                "moderate": ("⚖️", "#fff8e1", "#f57f17"),
                "aggressive": ("⚡", "#ffebee", "#c62828"),
            }
            tier_icon, tier_bg, tier_fg = tier_badge_map.get(
                tier, ("", "#f5f5f5", "#555")
            )

            # Movement / event context
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
      <td style="text-align:center; font-size:11px; font-weight:600; color:{'#2e7d32' if (t.get('pop') or 0) >= 70 else '#f57f17' if (t.get('pop') or 0) >= 60 else '#c62828'};">
        {f"{t['pop']:.0f}%" if t.get('pop') else '—'}
      </td>
      <td style="font-size:11px; color:#555;">{t['remark']}</td>
    </tr>"""

        html += f"""
    <tr class="portfolio-total">
      <td colspan="5" style="text-align:right; font-size:13px; padding-right:12px; border-top:2px solid #2e7d32;">
        TOTAL
      </td>
      <td style="text-align:center; font-size:13px;">{total_contracts}</td>
      <td></td>
      <td style="text-align:right; font-size:14px; color:#1b5e20;">
        ${total_prem:,.0f}
      </td>
      <td></td>
      <td style="text-align:right; font-size:13px; color:#c62828;">
        ${total_max_loss:,.0f}
      </td>
      <td style="text-align:center; font-size:11px;">{portfolio_rr}</td>
      <td></td>
    </tr>
  </table>

  <div style="margin-top:10px; font-size:11px; color:#555; border-top:1px solid #a5d6a7; padding-top:8px;">
    &#x26A0;&#xFE0F; Execute all trades simultaneously for portfolio-level
    risk management. Premium quoted at current bid &mdash; actual fills may
    vary. Max {max_contracts} contracts to stay within margin limits.
    <strong>This is NOT financial advice.</strong>
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
                    <span class="strat-badge strat-{strat}">{trade['strategy_display']}</span>
                    {trade['action']}
                  </div>
                  <div class="trade-rationale">{trade['rationale']}</div>
                </div>"""
                else:
                    html += f"""
                <div class="trade-card">
                  <div class="trade-head">
                    <span class="strat-badge strat-{strat}">{trade['strategy_display']}</span>
                    {trade['action']}
                  </div>
                  <div class="trade-detail">
                    Premium: <strong>${trade['premium']:.2f}</strong>/share
                    | Max Profit: ${trade['max_profit']:,.0f}
                    | Max Loss: ${trade['max_loss']:,.0f}
                    | Breakeven: ${trade.get('breakeven', 0):,.2f}
                    {f"| Risk/Reward: {trade['risk_reward']}" if trade.get('risk_reward') else ""}
                  </div>
                  <div class="trade-rationale">{trade['rationale']}</div>
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

"""
portfolio_report.py — Portfolio Action Plan Report Generator.

Generates a JP Morgan-style personalized portfolio advisory report
with HOLD / TRIM / SELL / ADD / NEW BUY recommendations.

Sent as a separate email from the market research report.
"""

import os
import logging
from datetime import datetime

from research_agents.config import REPORT_DIR

logger = logging.getLogger(__name__)


class PortfolioReportGenerator:
    """Generates institutional-grade portfolio action plan reports."""

    def generate(self, recommendations: dict) -> str:
        """Generate a complete portfolio action plan HTML report."""
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        time_str = datetime.now().strftime("%H:%M:%S")
        summary = recommendations.get("portfolio_summary", {})

        html = self._build_header(date_str, time_str)
        html += self._disclaimer()
        html += self._portfolio_overview(summary)
        html += self._risk_alerts(recommendations.get("risk_alerts", []))

        # Action sections
        sell = recommendations.get("sell", [])
        trim = recommendations.get("trim", [])
        add = recommendations.get("add", [])
        hold = recommendations.get("hold", [])
        new_buy = recommendations.get("new_buy", [])

        if sell:
            html += self._action_section("SELL \u2014 Exit These Positions", sell, "sell")
        if trim:
            html += self._action_section("TRIM \u2014 Reduce Exposure", trim, "trim")
        if add:
            html += self._action_section("ADD \u2014 Increase Position", add, "add")
        if new_buy:
            html += self._new_buy_section(new_buy)
        if hold:
            html += self._action_section("HOLD \u2014 Maintain Position", hold, "hold")

        html += self._sector_allocation(summary.get("sector_exposure", {}), summary.get("total_value", 0))
        html += self._build_footer(date_str, time_str)

        # Save
        os.makedirs(REPORT_DIR, exist_ok=True)
        filename = f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(REPORT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"Portfolio report saved to {filepath}")
        return html

    def _build_header(self, date_str, time_str):
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Portfolio Action Plan \u2014 {date_str}</title>
<style>
  :root {{
    --primary: #003A70;
    --primary-light: #00508F;
    --primary-dark: #002347;
    --accent: #C4A35A;
    --accent-light: #F5E6C8;
    --success: #1B7F37;
    --danger: #C62828;
    --warning: #E65100;
    --text: #1A1A2E;
    --text-secondary: #555;
    --text-muted: #888;
    --bg: #F7F8FA;
    --card-bg: #FFFFFF;
    --border: #E0E4E8;
    --border-light: #F0F2F5;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; -webkit-font-smoothing: antialiased; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 0 16px; }}
  .report-header {{
    background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 60%, #388E3C 100%);
    color: white; padding: 32px 40px;
    border-bottom: 4px solid var(--accent);
  }}
  .report-header .brand {{ font-size: 11px; letter-spacing: 3px; text-transform: uppercase; color: var(--accent); font-family: 'Helvetica Neue', Arial, sans-serif; margin-bottom: 8px; }}
  .report-header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 4px; }}
  .report-header .subtitle {{ font-size: 14px; opacity: 0.85; font-style: italic; }}
  .report-header .meta {{ font-size: 12px; opacity: 0.7; margin-top: 8px; font-family: 'Helvetica Neue', Arial, sans-serif; }}

  .section {{ background: var(--card-bg); border: 1px solid var(--border-light); border-radius: 14px; margin: 18px auto; max-width: 1100px; overflow: hidden; box-shadow: 0 2px 12px rgba(16,24,40,0.06); }}
  .section-header {{ background: linear-gradient(135deg, var(--primary-dark), var(--primary)); border-left: 4px solid var(--accent); padding: 14px 24px; font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 14px; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; color: white; }}
  .section-header.sell {{ background: var(--danger); }}
  .section-header.trim {{ background: var(--warning); }}
  .section-header.add {{ background: var(--success); }}
  .section-header.hold {{ background: var(--primary); }}
  .section-header.new-buy {{ background: linear-gradient(90deg, var(--primary), var(--success)); }}
  .section-header.overview {{ background: var(--primary); }}
  .section-header.risk {{ background: #B71C1C; }}
  .section-body {{ padding: 20px 24px; }}

  table {{ width: 100%; border-collapse: collapse; font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 12px; }}
  th {{ background: #F0F2F5; padding: 10px 8px; text-align: left; font-weight: 600; color: var(--primary); border-bottom: 2px solid var(--primary); font-size: 10px; letter-spacing: 0.5px; text-transform: uppercase; white-space: nowrap; }}
  td {{ padding: 8px; border-bottom: 1px solid var(--border-light); vertical-align: top; }}
  tr:hover {{ background: #FAFBFC; }}

  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: 700; font-family: 'Helvetica Neue', Arial, sans-serif; letter-spacing: 0.3px; text-transform: uppercase; }}
  .badge-sell {{ background: #FFEBEE; color: #B71C1C; border: 1px solid #FFCDD2; }}
  .badge-trim {{ background: #FFF3E0; color: #E65100; border: 1px solid #FFE0B2; }}
  .badge-add {{ background: #E8F5E9; color: #1B5E20; border: 1px solid #C8E6C9; }}
  .badge-hold {{ background: #E3F2FD; color: #0D47A1; border: 1px solid #BBDEFB; }}
  .badge-new {{ background: #E8F5E9; color: #1B5E20; border: 1px solid #A5D6A7; }}

  .positive {{ color: var(--success); font-weight: 600; }}
  .negative {{ color: var(--danger); font-weight: 600; }}
  .muted {{ color: var(--text-muted); }}

  .overview-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
  .overview-card {{ border: 1px solid var(--border-light); border-radius: 12px; padding: 14px; box-shadow: 0 1px 6px rgba(16,24,40,0.05); text-align: center; }}
  .overview-card .label {{ font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); font-family: 'Helvetica Neue', Arial, sans-serif; margin-bottom: 4px; }}
  .overview-card .value {{ font-size: 22px; font-weight: 700; font-family: 'Helvetica Neue', Arial, sans-serif; }}
  .overview-card .sub {{ font-size: 11px; color: var(--text-secondary); margin-top: 4px; }}

  .idea-card {{ border: 1px solid var(--border-light); border-radius: 12px; padding: 16px 20px; margin: 14px 0; background: white; box-shadow: 0 2px 10px rgba(16,24,40,0.06); }}
  .idea-card.sell {{ border-left: 5px solid var(--danger); }}
  .idea-card.trim {{ border-left: 5px solid var(--warning); }}
  .idea-card.add {{ border-left: 5px solid var(--success); }}
  .idea-card.hold {{ border-left: 5px solid var(--primary); }}
  .idea-card.new-buy {{ border-left: 5px solid var(--success); background: #FAFFF9; }}

  .idea-header {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }}
  .ticker {{ font-size: 20px; font-weight: 700; color: var(--primary); font-family: 'Helvetica Neue', Arial, sans-serif; }}
  .idea-name {{ font-size: 14px; color: var(--text-secondary); }}
  .idea-price {{ font-size: 16px; font-weight: 600; font-family: 'Helvetica Neue', Arial, sans-serif; }}

  .metrics-row {{ display: flex; gap: 20px; flex-wrap: wrap; font-size: 12px; font-family: 'Helvetica Neue', Arial, sans-serif; color: var(--text-secondary); margin: 8px 0; padding: 8px 0; border-top: 1px solid var(--border-light); border-bottom: 1px solid var(--border-light); }}
  .metric {{ white-space: nowrap; }}
  .metric-label {{ color: var(--text-muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .metric-value {{ font-weight: 600; color: var(--text); }}

  .reasons {{ margin: 8px 0; padding: 0 0 0 16px; font-size: 13px; line-height: 1.7; }}
  .reasons li {{ margin: 3px 0; }}
  .reasons li.bull {{ color: var(--success); }}
  .reasons li.bear {{ color: var(--danger); }}

  .action-box {{ background: #F5F6F8; border-radius: 4px; padding: 10px 14px; margin-top: 10px; font-size: 13px; font-family: 'Helvetica Neue', Arial, sans-serif; font-weight: 600; }}

  .alert-card {{ padding: 12px 16px; border-radius: 4px; margin: 8px 0; font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 13px; }}
  .alert-high {{ background: #FFEBEE; border-left: 4px solid #C62828; }}
  .alert-medium {{ background: #FFF3E0; border-left: 4px solid #E65100; }}
  .alert-low {{ background: #E3F2FD; border-left: 4px solid #1565C0; }}

  .sector-bar-container {{ margin: 6px 0; }}
  .sector-bar-row {{ display: flex; align-items: center; margin: 4px 0; font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 13px; }}
  .sector-bar-label {{ width: 200px; }}
  .sector-bar-track {{ flex: 1; height: 20px; background: #F0F2F5; border-radius: 3px; overflow: hidden; }}
  .sector-bar-fill {{ height: 100%; border-radius: 3px; }}
  .sector-bar-val {{ width: 60px; text-align: right; font-weight: 600; margin-left: 8px; }}

  .disclaimer {{ background: #FFF8E1; border: 1px solid #FFE082; border-radius: 4px; padding: 12px 20px; font-size: 11px; color: #5D4037; margin: 16px auto; max-width: 1100px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
  .report-footer {{ text-align: center; padding: 24px; color: var(--text-muted); font-size: 11px; border-top: 2px solid var(--success); margin-top: 24px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
  .report-footer .brand {{ color: #2E7D32; font-weight: 700; letter-spacing: 1px; }}
  .sans {{ font-family: 'Helvetica Neue', Arial, sans-serif; }}
  .text-sm {{ font-size: 12px; }}
</style>
</head>
<body>
<div class="report-header">
  <div class="container">
    <div class="brand">Trading AI Research \u2022 Portfolio Advisory</div>
    <h1>Portfolio Action Plan</h1>
    <div class="subtitle">Personalized Recommendations \u2014 Target: 3%+ Monthly Growth</div>
    <div class="meta">{date_str} | Generated {time_str} SGT | MooMoo SG Portfolio</div>
  </div>
</div>
"""

    def _disclaimer(self):
        return """
<div class="disclaimer">
  <strong>IMPORTANT:</strong> This is an automated portfolio analysis based on technical and fundamental signals.
  It does NOT constitute financial advice. All investment decisions are your sole responsibility.
  Always conduct your own due diligence before acting on any recommendation.
</div>
"""

    def _portfolio_overview(self, summary: dict) -> str:
        total = float(summary.get("total_value", 0) or 0)
        cash = float(summary.get("cash", 0) or 0)
        cash_pct = float(summary.get("cash_pct", 0) or 0)
        mkt_val = float(summary.get("market_value", 0) or 0)
        ur_pnl = float(summary.get("unrealized_pnl", 0) or 0)
        r_pnl = float(summary.get("realized_pnl", 0) or 0)
        num_pos = summary.get("num_positions", 0)
        est_monthly = summary.get("estimated_monthly_return", 0)
        on_track = summary.get("on_track_for_target", False)

        pnl_css = "positive" if ur_pnl >= 0 else "negative"
        track_css = "positive" if on_track else "negative"
        track_text = "ON TRACK" if on_track else "BELOW TARGET"

        return f"""
<div class="section container">
  <div class="section-header overview">Portfolio Overview</div>
  <div class="section-body">
    <div class="overview-grid">
      <div class="overview-card">
        <div class="label">Total Value</div>
        <div class="value">${total:,.0f}</div>
      </div>
      <div class="overview-card">
        <div class="label">Market Value</div>
        <div class="value">${mkt_val:,.0f}</div>
      </div>
      <div class="overview-card">
        <div class="label">Cash</div>
        <div class="value">${cash:,.0f}</div>
        <div class="sub">{cash_pct:.1f}% of portfolio</div>
      </div>
      <div class="overview-card">
        <div class="label">Unrealized P&L</div>
        <div class="value {pnl_css}">${ur_pnl:+,.0f}</div>
      </div>
      <div class="overview-card">
        <div class="label">Realized P&L</div>
        <div class="value {"positive" if r_pnl >= 0 else "negative"}">${r_pnl:+,.0f}</div>
      </div>
      <div class="overview-card">
        <div class="label">Positions</div>
        <div class="value">{num_pos}</div>
      </div>
      <div class="overview-card">
        <div class="label">Est. Monthly Return</div>
        <div class="value {track_css}">{est_monthly:+.1f}%</div>
        <div class="sub {track_css}">{track_text} (3%+ target)</div>
      </div>
    </div>
  </div>
</div>
"""

    def _risk_alerts(self, alerts: list) -> str:
        if not alerts:
            return ""

        html = """
<div class="section container">
  <div class="section-header risk">Risk Alerts</div>
  <div class="section-body">
"""
        for alert in alerts:
            severity = alert.get("severity", "MEDIUM").lower()
            html += f"""
    <div class="alert-card alert-{severity}">
      <strong>{alert.get('type', 'ALERT')}:</strong> {alert.get('message', '')}
    </div>"""

        html += "</div></div>"
        return html

    def _action_section(self, title: str, positions: list, action_type: str) -> str:
        header_css = action_type
        badge_css = f"badge-{action_type}"

        html = f"""
<div class="section container">
  <div class="section-header {header_css}">{title}</div>
  <div class="section-body">
"""
        for pos in positions:
            pnl = pos.get("pnl_pct", 0)
            pnl_css = "positive" if pnl >= 0 else "negative"
            current = pos.get("current_price", 0)
            cost = pos.get("cost_price", 0)
            qty = pos.get("qty", 0)
            weight = pos.get("weight_pct", 0)
            mkt_val = pos.get("market_value", 0)
            rsi = pos.get("rsi")
            rsi_str = f"{rsi:.0f}" if rsi else "\u2014"
            target = pos.get("analyst_target")
            upside = pos.get("upside_pct")
            quality = pos.get("fund_quality", "N/A")

            html += f"""
    <div class="idea-card {action_type}">
      <div class="idea-header">
        <span class="ticker">{pos['ticker']}</span>
        <span class="idea-name">{pos.get('name', '')}</span>
        <span class="idea-price">${current:,.2f}</span>
        <span class="badge {badge_css}">{pos.get('action', action_type.upper())}</span>
      </div>
      <div class="metrics-row">
        <div class="metric"><span class="metric-label">Qty</span><br><span class="metric-value">{qty:.0f}</span></div>
        <div class="metric"><span class="metric-label">Cost</span><br><span class="metric-value">${cost:,.2f}</span></div>
        <div class="metric"><span class="metric-label">Mkt Value</span><br><span class="metric-value">${mkt_val:,.0f}</span></div>
        <div class="metric"><span class="metric-label">P&L</span><br><span class="metric-value {pnl_css}">{pnl:+.1f}%</span></div>
        <div class="metric"><span class="metric-label">Weight</span><br><span class="metric-value">{weight:.1f}%</span></div>
        <div class="metric"><span class="metric-label">RSI</span><br><span class="metric-value">{rsi_str}</span></div>
        <div class="metric"><span class="metric-label">Quality</span><br><span class="metric-value">{quality}</span></div>
        {f'<div class="metric"><span class="metric-label">Target</span><br><span class="metric-value">${target:.0f}</span></div>' if target else ''}
        {f'<div class="metric"><span class="metric-label">Upside</span><br><span class="metric-value {"positive" if upside and upside > 0 else "negative"}">{upside:+.0f}%</span></div>' if upside is not None else ''}
      </div>"""

            reasons = pos.get("reasons", [])
            if reasons:
                html += '<ul class="reasons">'
                for r in reasons[:4]:
                    css = "bull" if action_type in ("add", "hold") else "bear" if action_type in ("sell",) else ""
                    html += f'<li class="{css}">{r}</li>'
                html += '</ul>'

            detail = pos.get("action_detail", "")
            if detail:
                html += f'<div class="action-box">\u27A4 {detail}</div>'

            html += '</div>'

        html += "</div></div>"
        return html

    def _new_buy_section(self, new_buys: list) -> str:
        html = """
<div class="section container">
  <div class="section-header new-buy">NEW BUY \u2014 Initiate Position</div>
  <div class="section-body">
    <p class="text-sm sans" style="color:var(--text-secondary); margin-bottom:16px;">
      High-conviction ideas not currently in your portfolio. These stocks exhibit
      strong fundamentals, favorable technicals, or macro-driven dislocations
      that create attractive entry points for new positions.
    </p>
"""
        for nb in new_buys[:10]:
            current = nb.get("current_price")
            price_str = f"${current:,.2f}" if current else "N/A"
            source = nb.get("source", "")
            source_label = "Dip Buy" if source == "DIP_BUY" else "Thematic"
            score = nb.get("score", 0)
            target = nb.get("analyst_target")
            upside = nb.get("upside_pct")
            quality = nb.get("fund_quality", "N/A")
            rev_g = nb.get("revenue_growth")
            earn_g = nb.get("earnings_growth")
            pct_high = nb.get("pct_from_52w_high")
            nb_rsi = nb.get("rsi")
            nb_rsi_str = f"{nb_rsi:.0f}" if nb_rsi else "\u2014"
            rev_g_str = f'<div class="metric"><span class="metric-label">Rev Growth</span><br><span class="metric-value">{rev_g*100:+.0f}%</span></div>' if rev_g is not None else ''
            earn_g_str = f'<div class="metric"><span class="metric-label">EPS Growth</span><br><span class="metric-value">{earn_g*100:+.0f}%</span></div>' if earn_g is not None else ''
            target_str = f'<div class="metric"><span class="metric-label">Target</span><br><span class="metric-value">${target:.0f}</span></div>' if target else ''
            upside_str = f'<div class="metric"><span class="metric-label">Upside</span><br><span class="metric-value positive">{upside:+.0f}%</span></div>' if upside and upside > 0 else ''
            high_str = f'<div class="metric"><span class="metric-label">From 52W High</span><br><span class="metric-value negative">{pct_high:+.0f}%</span></div>' if pct_high else ''

            html += f"""
    <div class="idea-card new-buy">
      <div class="idea-header">
        <span class="ticker">{nb['ticker']}</span>
        <span class="idea-name">{nb.get('name', '')}</span>
        <span class="idea-price">{price_str}</span>
        <span class="badge badge-new">NEW BUY</span>
        <span class="sans text-sm muted">Score: {score}/100 | {source_label}</span>
      </div>
      <div class="metrics-row">
        <div class="metric"><span class="metric-label">Quality</span><br><span class="metric-value">{quality}</span></div>
        {rev_g_str}
        {earn_g_str}
        {target_str}
        {upside_str}
        {high_str}
        <div class="metric"><span class="metric-label">RSI</span><br><span class="metric-value">{nb_rsi_str}</span></div>
      </div>"""

            reasons = nb.get("reasons", [])
            risks = nb.get("risk_factors", [])
            if reasons or risks:
                html += '<ul class="reasons">'
                for r in reasons[:3]:
                    html += f'<li class="bull">+ {r}</li>'
                for r in risks[:2]:
                    html += f'<li class="bear">- {r}</li>'
                html += '</ul>'

            html += '</div>'

        html += "</div></div>"
        return html

    def _sector_allocation(self, sector_exposure: dict, total_value: float) -> str:
        if not sector_exposure:
            return ""

        html = """
<div class="section container">
  <div class="section-header overview">Sector Allocation</div>
  <div class="section-body">
    <div class="sector-bar-container">
"""
        max_pct = max(sector_exposure.values()) if sector_exposure else 1
        colors = [
            "#003A70", "#1B7F37", "#C4A35A", "#E65100", "#C62828",
            "#6A1B9A", "#00838F", "#4E342E", "#37474F", "#1565C0", "#558B2F",
        ]

        for i, (sector, pct) in enumerate(sorted(sector_exposure.items(), key=lambda x: x[1], reverse=True)):
            bar_width = (pct / max_pct * 100) if max_pct > 0 else 0
            color = colors[i % len(colors)]
            html += f"""
      <div class="sector-bar-row">
        <div class="sector-bar-label"><strong>{sector}</strong></div>
        <div class="sector-bar-track">
          <div class="sector-bar-fill" style="width:{bar_width}%; background:{color};"></div>
        </div>
        <div class="sector-bar-val">{pct:.1f}%</div>
      </div>"""

        html += "</div></div></div>"
        return html

    def _build_footer(self, date_str, time_str):
        return f"""
<div class="report-footer">
  <div class="brand">TRADING AI \u2022 PORTFOLIO ADVISORY</div>
  <div style="margin-top:6px;">
    {date_str} | {time_str} SGT | MooMoo SG Portfolio<br>
    Automated portfolio analysis \u2014 NOT financial advice.<br>
    Target: 3%+ monthly growth | All decisions are your own responsibility.
  </div>
</div>
</body>
</html>"""

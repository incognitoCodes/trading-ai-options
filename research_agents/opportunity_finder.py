"""
opportunity_finder.py — Sector Catalyst & Multi-Bagger Opportunity Agent.

Identifies stocks with potential to double or triple based on:
  1. MACRO DEMAND THEMES — maps secular tailwinds (AI, energy transition,
     aging population, reshoring, cybersecurity, etc.) to beneficiary stocks
  2. REVENUE ACCELERATION — spots companies where growth is accelerating
     (like MU going from ~$100 to ~$400 on AI memory demand)
  3. SUPPLY/DEMAND IMBALANCE — industries with capacity constraints
     or demand outstripping supply
  4. RELATIVE UNDERVALUATION — stocks still cheap relative to the
     growth opportunity they're positioned for
  5. INSTITUTIONAL MOMENTUM — rising analyst targets, estimate revisions

The MU example: Memory chip demand surged 4x due to AI training needing
massive HBM (High Bandwidth Memory). MU was the key US-listed HBM supplier.
This agent looks for SIMILAR patterns across ALL sectors.

DISCLAIMER: Research only — not financial advice. Multi-bagger potential
is speculative and involves significant risk.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MACRO DEMAND THEMES — each theme maps to beneficiary industries/tickers
# These are updated periodically to reflect evolving catalysts
# ---------------------------------------------------------------------------
DEMAND_THEMES = {
    "AI_INFRASTRUCTURE": {
        "name": "AI Infrastructure & Compute",
        "description": (
            "Explosive demand for AI training and inference is driving unprecedented "
            "need for GPUs, HBM memory, custom silicon, data center power, cooling, "
            "and networking. This is the broadest secular theme since cloud computing."
        ),
        "demand_drivers": [
            "AI model training requiring exponentially more compute",
            "Enterprise AI adoption driving inference demand",
            "HBM memory shortage (HBM3E/HBM4) for AI accelerators",
            "Data center power demand exceeding grid capacity",
            "Custom ASIC chips for hyperscaler workloads",
        ],
        "tickers": {
            "NVDA": "Dominant GPU supplier for AI training — controls 80%+ of AI accelerator market",
            "AVGO": "Custom AI chip (XPU) for Google/Meta + networking (Memory ASIC, Tomahawk switches)",
            "MU":   "Only US-listed HBM manufacturer — HBM demand growing 5x for AI; was $100→$400 on this theme",
            "AMD":  "AI GPU challenger (MI300X) + EPYC server CPUs gaining data center share",
            "MRVL": "Custom AI silicon (ASIC) for Amazon/Microsoft + data center networking DPUs",
            "ANET": "AI data center networking switches — directly tied to GPU cluster deployments",
            "DELL": "AI server assembly — #2 behind HPE in AI-optimized servers",
            "SMCI": "AI server racks — fastest-growing AI server assembler (liquid-cooled GPU racks)",
            "TSM":  "Manufactures ALL leading-edge AI chips (NVDA, AVGO, AMD) — unavoidable chokepoint",
            "QCOM": "AI-on-device chips for smartphones/PCs — on-device inference is next wave",
            "ARM":  "IP licensor for ALL mobile/AI chips — royalty model scales with every chip shipped",
        },
        "supply_constraints": [
            "TSMC advanced node capacity (3nm, 2nm) fully booked through 2026",
            "HBM production limited to 3 suppliers globally (SK Hynix, Samsung, Micron)",
            "CoWoS advanced packaging bottleneck for AI GPU assembly",
            "Data center power availability limiting new builds",
        ],
    },
    "AI_SOFTWARE": {
        "name": "AI Software & Platforms",
        "description": (
            "Enterprise AI software spending is in early innings. Companies providing "
            "the platforms, tools, and applications for AI adoption are seeing "
            "hypergrowth similar to early cloud adoption (2012-2018)."
        ),
        "demand_drivers": [
            "Enterprise AI copilot adoption across all industries",
            "AI-native SaaS replacing traditional software",
            "Data infrastructure for AI/ML pipelines",
            "AI security and governance becoming mandatory",
        ],
        "tickers": {
            "MSFT":  "Azure AI + Copilot across Office/GitHub/etc — largest enterprise AI distribution",
            "CRM":   "Einstein AI copilot embedded in #1 CRM platform — AI upsell to 150K+ customers",
            "NOW":   "ServiceNow AI agents for IT/HR/CS — AI drives 30%+ net new ACV growth",
            "PLTR":  "AI/ML platform for government + enterprise — AIP platform accelerating commercial growth",
            "PANW":  "AI-powered cybersecurity — platformization driving 50%+ NGS ARR growth",
            "CRWD":  "AI-native endpoint security — Charlotte AI assistant + Falcon platform stickiness",
            "SNOW":  "Data cloud for AI — Cortex AI layer turns data warehouse into AI engine",
            "DDOG":  "AI observability — monitoring AI infrastructure is a new massive workload",
            "ADBE":  "Firefly generative AI in Creative Cloud — AI drives pricing power + new TAM",
            "ORCL":  "OCI cloud + database AI — GenAI driving cloud infrastructure acceleration",
        },
        "supply_constraints": [
            "Shortage of AI/ML engineering talent",
            "GPU cloud capacity constraining AI SaaS scaling",
        ],
    },
    "ENERGY_TRANSITION": {
        "name": "Energy Transition & Power Demand",
        "description": (
            "Dual demand shock: AI data centers need massive power + global electrification "
            "(EVs, heat pumps, industrial). Grid infrastructure severely underbuilt. "
            "Utilities, nuclear, and grid equipment makers are multi-year beneficiaries."
        ),
        "demand_drivers": [
            "AI data centers adding 50-100GW of power demand by 2030",
            "Nuclear energy renaissance — SMRs and plant restarts",
            "Grid modernization — $2T+ investment needed in US alone",
            "EV charging infrastructure buildout",
            "Industrial reshoring increasing power demand",
        ],
        "tickers": {
            "CEG":  "Constellation Energy — largest US nuclear fleet; signing AI data center power PPAs at 3x market rates",
            "VST":  "Vistra Energy — nuclear + natural gas power; direct AI power demand beneficiary in Texas",
            "GEV":  "GE Vernova — gas turbines + grid equipment; order backlog surging on data center + grid demand",
            "ETN":  "Eaton Corp — electrical equipment for data centers, grid, EV charging; power management leader",
            "FSLR": "First Solar — only US-made solar panels; IRA subsidies + tariff protection = pricing power",
            "PWR":  "Quanta Services — builds power grid infrastructure; multi-decade backlog growth",
            "NEE":  "NextEra Energy — largest US renewable energy developer; regulated + growth combo",
            "APD":  "Air Products — hydrogen infrastructure; green hydrogen is decade-long growth theme",
            "LIN":  "Linde — industrial gases for semiconductor fabs + clean energy; steady compounder",
        },
        "supply_constraints": [
            "Grid transformer lead times stretched to 3-4 years",
            "Nuclear plant restart requires 2-3 year regulatory timeline",
            "Electrical equipment manufacturers at full capacity",
            "Skilled labor shortage for grid construction",
        ],
    },
    "DEFENSE_RESHORING": {
        "name": "Defense Spending & Industrial Reshoring",
        "description": (
            "Geopolitical tensions driving largest defense spending increase since Cold War. "
            "Simultaneously, US/EU reshoring critical manufacturing (chips, pharma, energy). "
            "Multi-year order backlogs provide unusual visibility."
        ),
        "demand_drivers": [
            "NATO defense spending rising to 3%+ of GDP",
            "US CHIPS Act driving domestic semiconductor fabs",
            "Supply chain security — nearshoring critical manufacturing",
            "Munitions restocking after Ukraine drawdowns",
            "Space/satellite defense becoming priority",
        ],
        "tickers": {
            "LMT":  "Lockheed Martin — F-35, missiles, space; largest defense backlog in history",
            "RTX":  "RTX Corp — Patriot missiles, Pratt & Whitney engines; multi-year engine ramp",
            "GD":   "General Dynamics — Gulfstream + submarines + IT; defense + business jet cycle",
            "GE":   "GE Aerospace — jet engine aftermarket monopoly; LEAP engine installed base growing 20%/yr",
            "HWM":  "Howmet Aerospace — sole-source jet engine parts; pricing power + capacity constraints",
            "CAT":  "Caterpillar — infrastructure + reshoring construction equipment; pricing power in tight market",
            "URI":  "United Rentals — equipment rental for megaprojects (fabs, data centers, LNG); secular share gains",
            "AME":  "AMETEK — precision instruments for defense/aerospace; high-margin niche monopolies",
            "TDG":  "TransDigm — sole-source aerospace parts; 40%+ EBITDA margins, pricing power moat",
        },
        "supply_constraints": [
            "Defense industrial base at capacity — 2-3 year lead times",
            "Skilled manufacturing labor shortage",
            "Titanium and rare earth supply constraints",
            "Semiconductor fab construction takes 3-5 years",
        ],
    },
    "HEALTHCARE_INNOVATION": {
        "name": "Healthcare Innovation & Aging Demographics",
        "description": (
            "GLP-1 obesity drugs are a $100B+ market opportunity. AI drug discovery "
            "is accelerating pipelines. Aging Baby Boomers driving surgical robotics, "
            "diagnostics, and medical device demand. Biotech valuations at decade lows."
        ),
        "demand_drivers": [
            "GLP-1 obesity/diabetes drugs — largest pharma opportunity since statins",
            "AI-accelerated drug discovery cutting development timelines",
            "Aging population driving surgical volumes and diagnostics",
            "Gene therapy / cell therapy entering commercial era",
            "Medical device innovation cycle (robotic surgery, continuous monitoring)",
        ],
        "tickers": {
            "LLY":  "Eli Lilly — Mounjaro/Zepbound (GLP-1 leader); $100B+ peak sales potential across obesity/diabetes/NASH",
            "ISRG": "Intuitive Surgical — da Vinci robotic surgery monopoly; procedure growth + new Ion lung platform",
            "VRTX": "Vertex Pharma — CF monopoly + pain drug (suzetrigine) could be first non-opioid blockbuster",
            "REGN": "Regeneron — Dupixent growing 20%+ + Eylea durability; best pipeline in large biotech",
            "BSX":  "Boston Scientific — med-tech momentum; electrophysiology + structural heart growth accelerating",
            "DXCM": "DexCom — continuous glucose monitors; GLP-1 drugs EXPAND CGM market (more diagnosed patients)",
            "SYK":  "Stryker — surgical robots (Mako) + implants; aging population = decade-long tailwind",
            "IDXX": "IDEXX Labs — veterinary diagnostics monopoly; pet spending is recession-resistant",
            "TMO":  "Thermo Fisher — life science tools; AI drug discovery drives instrument demand",
        },
        "supply_constraints": [
            "GLP-1 manufacturing capacity severely constrained (fill-finish bottleneck)",
            "Surgical robot installation limited by hospital capex cycles",
            "Clinical trial enrollment bottlenecks for gene therapies",
        ],
    },
    "CYBERSECURITY": {
        "name": "Cybersecurity — Zero Trust & AI Threats",
        "description": (
            "AI-powered cyberattacks + regulatory mandates driving 15-20% annual "
            "cybersecurity spending growth. Consolidation to platform vendors. "
            "This is a must-have, not nice-to-have — spending is non-discretionary."
        ),
        "demand_drivers": [
            "AI-generated attacks increasing sophistication exponentially",
            "Regulatory mandates (SEC, NIS2, DORA) requiring security spend",
            "Cloud migration expanding attack surface",
            "Zero-trust architecture becoming standard",
            "Cyber insurance requirements driving vendor adoption",
        ],
        "tickers": {
            "PANW": "Palo Alto Networks — platformization leader; NGS ARR growing 50%+ as customers consolidate vendors",
            "CRWD": "CrowdStrike — #1 endpoint security; Falcon platform expanding into SIEM, cloud, identity",
            "FTNT": "Fortinet — firewall + SASE leader; best margins in cybersecurity; OT security growth",
            "ZS":   "Zscaler — zero-trust cloud security leader; replacing legacy VPNs in enterprises",
        },
        "supply_constraints": [
            "Cybersecurity talent shortage — 3.5M unfilled positions globally",
            "Legacy vendor lock-in slowing migration (but accelerating)",
        ],
    },
    "FINANCIAL_INFRASTRUCTURE": {
        "name": "Financial Infrastructure & Payments Modernization",
        "description": (
            "Digital payments, real-time settlement, and financial data/analytics "
            "are structural growth stories. These are toll-booth businesses with "
            "high margins and network effects."
        ),
        "demand_drivers": [
            "Cash-to-digital payment conversion (still only 40% digital globally)",
            "Cross-border payment modernization",
            "Real-time payments infrastructure (FedNow, etc.)",
            "Financial data and analytics for AI/compliance",
            "Embedded finance / fintech infrastructure",
        ],
        "tickers": {
            "V":    "Visa — global payment network duopoly; 3B+ cards, growing cross-border + value-added services",
            "MA":   "Mastercard — payment network + data/analytics; multi-rail strategy (ACH, crypto, B2B)",
            "SPGI": "S&P Global — financial data monopoly; ratings + indices + analytics; 80%+ recurring revenue",
            "MCO":  "Moody's — credit ratings duopoly + analytics; debt issuance cycle turning positive",
            "ICE":  "ICE — NYSE + futures + mortgage tech; data/analytics business growing 10%+",
            "CME":  "CME Group — derivatives exchange monopoly; volatility = more trading = more revenue",
            "FICO": "Fair Isaac — credit scoring monopoly; pricing power + software platform growth",
        },
        "supply_constraints": [
            "Regulatory barriers to entry create natural monopolies",
            "Network effects make displacement nearly impossible",
        ],
    },
}


class OpportunityFinder:
    """Identifies multi-bagger opportunities based on sector demand catalysts."""

    def analyze_opportunities(
        self,
        technical_results: list[dict],
        fundamental_results: list[dict],
    ) -> list[dict]:
        """Score each theme's tickers on multi-bagger potential.

        Combines:
          - Demand theme strength (qualitative)
          - Revenue/earnings growth acceleration (quantitative)
          - Valuation relative to growth (PEG, fwd P/E)
          - Technical momentum
          - Analyst upside
          - Supply constraint severity

        Returns a list of opportunity dicts sorted by potential score.
        """
        # Build lookups
        tech_lookup = {t["ticker"]: t for t in technical_results if t}
        fund_lookup = {f["ticker"]: f for f in fundamental_results if f}

        opportunities = []

        for theme_key, theme in DEMAND_THEMES.items():
            for ticker, thesis in theme["tickers"].items():
                tech = tech_lookup.get(ticker, {})
                fund = fund_lookup.get(ticker, {})

                if not tech and not fund:
                    # Ticker might not be in S&P 500 watchlist — still include with thesis
                    opportunities.append({
                        "ticker": ticker,
                        "theme": theme["name"],
                        "theme_key": theme_key,
                        "thesis": thesis,
                        "opportunity_score": 50,  # Base score for theme inclusion
                        "current_price": None,
                        "insights": [thesis, f"Part of {theme['name']} demand theme"],
                        "demand_drivers": theme["demand_drivers"][:2],
                        "supply_constraints": theme["supply_constraints"][:1] if theme["supply_constraints"] else [],
                        "multibagger_signals": [],
                        "risk_factors": [],
                    })
                    continue

                score = 0
                signals = []
                risks = []

                # --- Revenue Growth Acceleration (most important for multi-baggers) ---
                rev_growth = fund.get("revenue_growth")
                earn_growth = fund.get("earnings_growth")
                if rev_growth is not None:
                    if rev_growth > 0.30:
                        score += 25
                        signals.append(f"Revenue growing {rev_growth*100:.0f}% — hypergrowth territory")
                    elif rev_growth > 0.15:
                        score += 18
                        signals.append(f"Revenue growing {rev_growth*100:.0f}% — strong growth")
                    elif rev_growth > 0.05:
                        score += 10
                        signals.append(f"Revenue growing {rev_growth*100:.0f}% — moderate growth")
                    elif rev_growth < 0:
                        score -= 10
                        risks.append(f"Revenue declining {rev_growth*100:.0f}% — demand thesis not yet visible in numbers")

                if earn_growth is not None and earn_growth > 0.30:
                    score += 15
                    signals.append(f"Earnings surging {earn_growth*100:.0f}% — operating leverage kicking in")

                # --- Valuation relative to growth ---
                peg = fund.get("peg_ratio")
                pe_fwd = fund.get("pe_forward")
                if peg is not None and peg > 0:
                    if peg < 1.0:
                        score += 15
                        signals.append(f"PEG ratio {peg:.1f} — growth significantly underpriced")
                    elif peg < 1.5:
                        score += 8
                        signals.append(f"PEG ratio {peg:.1f} — reasonably valued for growth")
                    elif peg > 3.0:
                        score -= 5
                        risks.append(f"PEG ratio {peg:.1f} — growth already priced in")

                if pe_fwd is not None:
                    if pe_fwd < 20 and rev_growth and rev_growth > 0.15:
                        score += 10
                        signals.append(f"Forward P/E only {pe_fwd:.0f}x despite {rev_growth*100:.0f}% growth — still cheap")

                # --- Technical momentum ---
                ret_1y = tech.get("return_1y")
                ret_3m = tech.get("return_3m")
                trend = tech.get("trend", "")
                if ret_1y is not None:
                    if ret_1y > 100:
                        score += 10
                        signals.append(f"Up {ret_1y:.0f}% in 1 year — strong institutional demand (like MU's AI run)")
                    elif ret_1y > 50:
                        score += 7
                        signals.append(f"Up {ret_1y:.0f}% in 1 year — significant momentum")
                    elif ret_1y < -20:
                        # Could be opportunity or value trap
                        if rev_growth and rev_growth > 0.10:
                            score += 5
                            signals.append(f"Down {abs(ret_1y):.0f}% YTD despite growth — potential mean-reversion opportunity")
                        else:
                            risks.append(f"Down {abs(ret_1y):.0f}% in 1 year — check if fundamentals justify the decline")

                if "STRONG_UPTREND" in trend:
                    score += 5

                # --- Analyst sentiment ---
                target_mean = fund.get("target_mean")
                current_price = tech.get("current_price") or fund.get("current_price")
                analyst_rating = fund.get("analyst_rating")
                if target_mean and current_price and current_price > 0:
                    upside = ((target_mean - current_price) / current_price) * 100
                    if upside > 30:
                        score += 12
                        signals.append(f"Analyst target ${target_mean:.0f} implies {upside:.0f}% upside — street catching up to the story")
                    elif upside > 15:
                        score += 7
                        signals.append(f"Analyst target ${target_mean:.0f} implies {upside:.0f}% upside")
                    elif upside < -10:
                        risks.append(f"Trading {abs(upside):.0f}% above analyst target — priced for perfection")

                # --- Profit margins (operating leverage = multi-bagger fuel) ---
                profit_margin = fund.get("profit_margin")
                if profit_margin is not None:
                    if profit_margin > 0.30:
                        score += 5
                        signals.append(f"High profit margin ({profit_margin*100:.0f}%) — strong pricing power and operating leverage")
                    elif profit_margin < 0:
                        risks.append("Currently unprofitable — thesis depends on future scale")

                # --- Market cap context ---
                mcap = fund.get("market_cap", 0)
                if mcap > 0:
                    if mcap < 20e9:
                        score += 5  # Smaller cap = more room to run
                        signals.append("Sub-$20B market cap — more room for multiple expansion")
                    elif mcap < 50e9:
                        score += 3
                    elif mcap > 500e9:
                        score -= 3
                        risks.append(f"Mega-cap (${mcap/1e9:.0f}B) — harder to double from here, but still benefits from theme")

                # Composite opportunity
                opp = {
                    "ticker": ticker,
                    "theme": theme["name"],
                    "theme_key": theme_key,
                    "thesis": thesis,
                    "opportunity_score": max(0, min(100, score)),
                    "current_price": current_price,
                    "pe_forward": pe_fwd,
                    "revenue_growth": rev_growth,
                    "earnings_growth": earn_growth,
                    "return_1y": ret_1y,
                    "return_3m": ret_3m,
                    "trend": trend,
                    "analyst_target": target_mean,
                    "market_cap": mcap,
                    "insights": [thesis] + signals,
                    "demand_drivers": theme["demand_drivers"][:3],
                    "supply_constraints": theme["supply_constraints"][:2] if theme["supply_constraints"] else [],
                    "multibagger_signals": signals,
                    "risk_factors": risks,
                    "signal": tech.get("signal", "N/A"),
                    "tech_score": tech.get("composite_score", 0),
                    "fund_quality": fund.get("quality", "N/A"),
                }
                opportunities.append(opp)

        # Sort by opportunity score descending
        opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)

        # Deduplicate (a ticker might appear in multiple themes — keep highest)
        seen = set()
        unique = []
        for opp in opportunities:
            if opp["ticker"] not in seen:
                seen.add(opp["ticker"])
                unique.append(opp)

        return unique

    def get_top_opportunities(self, opportunities: list[dict], n: int = 15) -> list[dict]:
        """Return the top N opportunities by score."""
        return opportunities[:n]

    def get_theme_summary(self) -> list[dict]:
        """Return a summary of all demand themes for the report."""
        summaries = []
        for key, theme in DEMAND_THEMES.items():
            summaries.append({
                "key": key,
                "name": theme["name"],
                "description": theme["description"],
                "num_stocks": len(theme["tickers"]),
                "tickers": list(theme["tickers"].keys()),
                "top_drivers": theme["demand_drivers"][:3],
                "top_constraints": theme["supply_constraints"][:2] if theme["supply_constraints"] else [],
            })
        return summaries

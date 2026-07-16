#!/usr/bin/env python3
"""Debug R/R ratios for weekly trades."""
import yfinance as yf
from research_agents.options_advisor import OptionsAdvisor

print("Starting debug...", flush=True)
advisor = OptionsAdvisor()
tickers = ["NVDA", "QQQ", "MSFT", "AVGO", "CRWD"]
price_data = {}
for t in tickers:
    try:
        df = yf.Ticker(t).history(period="1y", auto_adjust=True)
        if not df.empty:
            price_data[t] = df
    except Exception as e:
        print(f"  Error for {t}: {e}", flush=True)

print(f"Analyzing {len(price_data)} tickers...", flush=True)
results = advisor.analyze_options(price_data, tickers)  # correct order!
print(f"Got {len(results)} results", flush=True)

for r in results:
    wt = r.get("weekly_trades", [])
    tk = r["ticker"]
    dm = r.get("daily_move_pct", "?")
    price = r.get("current_price", 0)
    print(f"\n{tk} price=${price:.2f} score={r['premium_score']} ATR_daily={dm}%:", flush=True)
    if not wt:
        print("  (no weekly trades)", flush=True)
    for t in wt:
        mp = t.get("max_profit", 0)
        ml = t.get("max_loss", 0)
        ratio = ml / mp if mp > 0 else 999
        pop = t.get("pop", "?")
        flag = "PASS(2x)" if ml <= mp * 2 else "FAIL"
        strike = t.get("strike", 0)
        strike_long = t.get("strike_long", "")
        sc_sell = t.get("strike_call_sell", "")
        sc_buy = t.get("strike_call_buy", t.get("strike_call_buy", ""))
        # OTM pct from current price
        otm_pct = abs(strike - price) / price * 100 if price > 0 and strike > 0 else 0
        strike_info = f"K={strike:.0f}" if strike else ""
        if strike_long:
            strike_info += f"/{strike_long:.0f}"
        if sc_sell:
            strike_info += f" | C={sc_sell:.0f}"
        if sc_buy:
            strike_info += f"/{sc_buy:.0f}"
        print(
            f"  {t['strategy_display']:<20} "
            f"{strike_info:<28} "
            f"OTM={otm_pct:.1f}%  "
            f"prem=${t['premium']:.2f}  "
            f"MP=${mp:,.0f}  ML=${ml:,.0f}  "
            f"ML/MP={ratio:.2f}  POP={pop}%  {flag}",
            flush=True,
        )

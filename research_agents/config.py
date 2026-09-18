"""
config.py — Configuration for the research agents system.

Set your email credentials and preferences here.
For Gmail, you need an App Password (not your regular password):
  1. Go to myaccount.google.com -> Security -> 2-Step Verification
  2. At the bottom, click "App passwords"
  3. Generate a new app password for "Mail"
  4. Use that 16-character password below
"""

import os

# ---------------------------------------------------------------------------
# Email Settings
# ---------------------------------------------------------------------------
# Recipients are read from RESEARCH_EMAIL_RECIPIENTS (comma-separated) so no
# personal address is baked into the source. Leave it unset and email is skipped.
EMAIL_RECIPIENTS = [
    a.strip() for a in os.environ.get("RESEARCH_EMAIL_RECIPIENTS", "").split(",") if a.strip()
]
EMAIL_SENDER = os.environ.get("RESEARCH_EMAIL_SENDER", "")
EMAIL_PASSWORD = os.environ.get("RESEARCH_EMAIL_PASSWORD", "")  # Gmail App Password
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ---------------------------------------------------------------------------
# Analysis Settings
# ---------------------------------------------------------------------------
# Lookback periods for data collection
PRICE_HISTORY_PERIOD = "1y"       # 1 year of daily data for analysis
SHORT_HISTORY_PERIOD = "3mo"      # 3 months for short-term signals
INTRADAY_PERIOD = "5d"            # 5 days of intraday for momentum

# Technical indicator parameters
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
SMA_SHORT = 20
SMA_MEDIUM = 50
SMA_LONG = 200
EMA_FAST = 9
EMA_SLOW = 21
ATR_PERIOD = 14
STOCH_PERIOD = 14
VOLUME_AVG_PERIOD = 20

# ---------------------------------------------------------------------------
# Scoring Thresholds
# ---------------------------------------------------------------------------
# Technical signal composite score thresholds
STRONG_BUY_THRESHOLD = 5
BUY_THRESHOLD = 3
HOLD_UPPER = 2
HOLD_LOWER = -2
SELL_THRESHOLD = -3
STRONG_SELL_THRESHOLD = -5

# Fundamental score thresholds (out of 100)
FUND_EXCELLENT = 80
FUND_GOOD = 60
FUND_FAIR = 40
FUND_POOR = 20

# ---------------------------------------------------------------------------
# Report Settings
# ---------------------------------------------------------------------------
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
MAX_TOP_PICKS = 10       # Max stocks in "Top Buy Signals" section
MAX_SELL_SIGNALS = 10    # Max stocks in "Sell Signals" section

# ---------------------------------------------------------------------------
# News Settings
# ---------------------------------------------------------------------------
NEWS_SOURCES_RSS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
]
FINVIZ_BASE_URL = "https://finviz.com/quote.ashx?t={ticker}"
MAX_NEWS_PER_TICKER = 5

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
API_DELAY_SECONDS = 0.3  # Delay between API calls to avoid throttling
BATCH_SIZE = 10           # Process tickers in batches of this size

# ---------------------------------------------------------------------------
# Options Advisory Settings
# ---------------------------------------------------------------------------
OPTIONS_EMAIL_RECIPIENT = os.environ.get("OPTIONS_EMAIL_RECIPIENT", "")  # Private advisory
OPTIONS_DTE_WEEKLY = (2, 9)       # Weekly options for portfolio trades
OPTIONS_DTE_NEAR = (5, 14)        # Near-term expiry window (days)
OPTIONS_DTE_MID = (14, 35)        # Mid-term / theta sweet spot
OPTIONS_DTE_FAR = (35, 60)        # Far-term for term structure
OPTIONS_MIN_OPEN_INTEREST = 100   # Min OI to consider a contract liquid
OPTIONS_MIN_PREMIUM_SCORE = 30    # Min score to include in report
HV_WINDOW_SHORT = 10              # 10-day realized vol
HV_WINDOW_STANDARD = 20           # 20-day realized vol
HV_WINDOW_LONG = 60               # 60-day realized vol

# ---------------------------------------------------------------------------
# Options Advisory — High-conviction screen (per Abhijit's spec)
# ---------------------------------------------------------------------------
# Only consider names whose ATM implied volatility LEVEL clears this bar.
# Absolute annualized IV as a decimal (0.60 = 60%). This screen keeps the
# focus on higher-vol names with richer raw premium while still surfacing
# candidates on most days.
OPTIONS_MIN_IV_LEVEL = float(os.environ.get("OPTIONS_MIN_IV_LEVEL", "0.60"))

# A trade is only RECOMMENDED if its probability of profit (computed on the
# real MooMoo premium) clears this bar, plus liquidity and no binary
# (earnings) event before expiry. Probability gate.
OPTIONS_MIN_POP = float(os.environ.get("OPTIONS_MIN_POP", "50.0"))

# Worst-leg bid/ask spread (as % of mid) allowed for a trade to count as
# liquid enough to recommend. Wider = the fill you actually get is uncertain.
OPTIONS_MAX_BID_ASK_PCT = float(os.environ.get("OPTIONS_MAX_BID_ASK_PCT", "0.18"))

# Weekly premium-income target for the two-part portfolio (Part 1 high-conviction
# + Part 2 target fillers combine toward this).
OPTIONS_WEEKLY_TARGET = float(os.environ.get("OPTIONS_WEEKLY_TARGET", "4000"))

# Which stock universe the options advisory scans:
#   "russell1000" (default, ~1,000 names), "sp500" (~500), or "blue_chips"
#   (~115 mega/large caps). A bigger universe surfaces more candidates but
#   takes proportionally longer to scan and is more likely to hit data-source
#   rate limits.
OPTIONS_UNIVERSE_NAME = os.environ.get("OPTIONS_UNIVERSE_NAME", "russell1000").lower()

# Cap on how many trade ideas the advisory surfaces. Both the weekly portfolio
# (actionable recommendations) and the top-opportunities list are limited to
# this many, best first.
OPTIONS_MAX_RECOMMENDATIONS = int(os.environ.get("OPTIONS_MAX_RECOMMENDATIONS", "10"))

# Liquidity pre-filter. Before the expensive option-chain analysis, rank the
# universe by average dollar volume (a cheap, already-downloaded proxy for
# option liquidity) and keep only the top N names (index ETFs are always kept).
# This skips the option-chain fetch on names that would fail the liquidity gate
# anyway. Set to 0 to disable and analyze the whole universe.
OPTIONS_PREFILTER_TOP_N = int(os.environ.get("OPTIONS_PREFILTER_TOP_N", "300"))

# Pull ACTUAL premium from MooMoo OpenD real-time data (two-stage: yfinance
# screens the universe, MooMoo confirms the shortlist at US market open).
# Set to "0" to disable and fall back to yfinance premiums (clearly labeled).
OPTIONS_USE_MOOMOO_REALTIME = os.environ.get("OPTIONS_USE_MOOMOO_REALTIME", "1") != "0"
OPEND_HOST = os.environ.get("OPEND_HOST", "127.0.0.1")
OPEND_PORT = int(os.environ.get("OPEND_PORT", "11111"))

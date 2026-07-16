# Trading AI — Options

An options trading and research system for the MooMoo/Futu platform. It combines
an interactive execution CLI (spreads, iron condors/butterflies, naked options,
payoff simulation) with a set of research agents that generate a daily options
premium advisory and a portfolio action plan.

> **Safety:** trading defaults to **paper/simulate**. Real-money trading is only
> enabled when `TRADING_ENV=REAL` is set *and* you confirm the live-mode prompt in
> the CLI. Nothing here places a live order by default.

## What's inside

| Area | Modules |
|------|---------|
| Interactive CLI | `main.py`, `cli/` |
| Broker / execution | `api/`, `broker/` |
| Strategies | `strategies/` (vertical spread, iron condor, iron butterfly, naked option) |
| Payoff / Greeks simulation | `simulation/` |
| Options research | `research_agents/run_options_daily.py`, `options_advisor.py`, `options_report.py` |
| Portfolio advisory | `research_agents/run_portfolio_daily.py`, `portfolio_advisor.py`, `portfolio_report.py` |
| Self-healing pipeline runner | `run_with_guard.py` |

The stock-only research pipeline lives in a separate repository.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

You also need MooMoo's **OpenD** gateway running locally (default `127.0.0.1:11111`)
and logged into your account.

## Configuration

All secrets and personal settings are read from environment variables (a local
`.env` file is loaded automatically and is git-ignored). None are committed.

| Variable | Purpose |
|----------|---------|
| `TRADING_ENV` | `SIMULATE` (default) or `REAL` |
| `MOOMOO_TRADE_PWD` | Trade-unlock password, required only for `REAL` |
| `RESEARCH_EMAIL_SENDER` | Gmail address used to send reports |
| `RESEARCH_EMAIL_PASSWORD` | Gmail **App Password** (not your login password) |
| `RESEARCH_EMAIL_RECIPIENTS` | Comma-separated recipients for research emails |
| `OPTIONS_EMAIL_RECIPIENT` | Recipient for the options advisory |

Example `.env`:

```
TRADING_ENV=SIMULATE
MOOMOO_TRADE_PWD=
RESEARCH_EMAIL_SENDER=you@gmail.com
RESEARCH_EMAIL_PASSWORD=your_app_password
RESEARCH_EMAIL_RECIPIENTS=you@gmail.com
OPTIONS_EMAIL_RECIPIENT=you@gmail.com
```

## Usage

```bash
python main.py                                   # interactive trading CLI
python -m research_agents.run_options_daily      # options premium advisory
python -m research_agents.run_portfolio_daily    # portfolio action plan
python run_with_guard.py options                 # run a pipeline with auto-retry
```

## Backtesting

```bash
python -m research_agents.options_backtester                  # SPY: raw + managed
python -m research_agents.options_backtester --underlying QQQ
python -m research_agents.options_backtester --compare        # full filter grid
```

Backtests the strategy the advisor recommends most: short put credit
spreads (30-delta, ~45 DTE, 5% width), sold weekly. Because free
historical option chains don't exist, spreads are priced with
Black-Scholes at entry using the real IV index (^VIX for SPY, ^VXN for
QQQ) plus a 10% skew adjustment, settled at intrinsic value on the
actual underlying price, with a 10% credit haircut for slippage.
Approximate by construction — treat results as directional, not exact.

Results over Jul 2019 – Jul 2026 (validated on an in-sample /
out-of-sample split; the ranking below held in both halves):

| Variant | Trades | Win% | CAGR | Sharpe | Max DD |
|---|---|---|---|---|---|
| SPY hold-to-expiry | 346 | 88.4% | +32.2% | 2.41 | -35.0% |
| SPY managed (50% profit / 3x stop) | 346 | 89.6% | +14.8% | 1.28 | -20.5% |
| QQQ hold-to-expiry | 346 | 87.3% | +36.0% | 2.46 | -50.7% |
| QQQ managed | 346 | 89.0% | +15.9% | 1.26 | -34.1% |

Findings worth knowing: entry filters (IV-percentile gate, SMA200 trend
gate) consistently *reduced* returns in both sample windows and are off
by default. Hold-to-expiry harvests the most premium but eats the 2020
crash in full; management roughly halves the drawdown for roughly half
the CAGR. There is no configuration that keeps the return and skips the
tail risk — that trade-off is the strategy.

## Disclaimer

This is personal software for educational use. It is not investment advice. Options
trading carries substantial risk of loss. Use paper trading until you fully
understand the behavior, and review all code before enabling `REAL` mode.

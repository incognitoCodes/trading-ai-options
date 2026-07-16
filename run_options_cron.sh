#!/bin/bash
# Wrapper script for cron — options premium advisory
# Uses the venv python by full path to avoid macOS "Operation not permitted" on activate.
# Resolves paths relative to this script so it works from any checkout location.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
"$DIR/venv/bin/python" -m research_agents.run_options_daily

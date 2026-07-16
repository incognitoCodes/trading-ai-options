"""
main.py — Entry point for the MooMoo Options Trading System.

Run this file to launch the interactive CLI:
    python main.py

Prerequisites:
    1. Install dependencies:   pip install -r requirements.txt
    2. Download and run MooMoo OpenD gateway (port 11111 by default)
    3. Log into OpenD with your MooMoo account

Configuration:
    Edit config.py to change gateway settings, trading mode, etc.
    Default is PAPER TRADING (safe, no real money).
"""

import sys
import os

# Set matplotlib backend BEFORE anything else imports it
import matplotlib
matplotlib.use("Agg")

# Ensure the project root is on the Python path so all imports work
# regardless of where the script is run from.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Load environment variables from .env file (password, etc.)
_env_file = os.path.join(PROJECT_ROOT, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

from cli.menu import main_menu


def main():
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Exiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()

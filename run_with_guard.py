#!/usr/bin/env python3
"""
run_with_guard.py — Self-healing wrapper for all Trading_AI pipelines.

Catches import errors (numpy corruption, etc.), auto-repairs the venv,
retries the pipeline, and sends a failure alert email if all else fails.

Usage (called by launchd agents):
  python run_with_guard.py stock [--quick]
  python run_with_guard.py stock-full
  python run_with_guard.py portfolio [--paper]
  python run_with_guard.py options
"""

import subprocess
import sys
import os
import time
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# The venv lives OUTSIDE iCloud-synced ~/Documents. iCloud periodically offloads
# and makes conflict-copies of compiled .so files (numpy/scipy/curl_cffi), which
# corrupts any venv kept inside the project folder. Keeping it under ~/.venvs
# (never synced) is the durable fix. Override with TRADING_AI_VENV if needed.
VENV_DIR = os.environ.get(
    "TRADING_AI_VENV", os.path.expanduser("~/.venvs/trading_ai")
)
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")
REQUIREMENTS_LOCK = os.path.join(PROJECT_ROOT, "requirements.lock")
LOG_DIR = os.path.join(PROJECT_ROOT, "reports")
ALERT_LOG = os.path.join(LOG_DIR, "guard_alerts.log")

MAX_RETRIES = 2
VENV_REBUILD_TIMEOUT = 900  # 15 min — scipy/matplotlib/pandas wheels are large; too-short a timeout kills pip mid-extraction and corrupts the venv

# Pipeline definitions: name -> (module, extra_args)
PIPELINES = {
    "stock":      ("research_agents.run_daily", []),         # Full S&P 500 + NASDAQ-100 + ETFs
    "stock-quick":("research_agents.run_daily", ["--quick"]),# NASDAQ-100+ for quick updates
    "portfolio":  ("research_agents.run_portfolio_daily", []),
    "options":    ("research_agents.run_options_daily", []),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GUARD] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("guard")


def load_env():
    """Load .env file into environment."""
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def send_alert_email(pipeline_name: str, error_msg: str):
    """Send a failure alert email so you know something broke."""
    load_env()
    password = os.environ.get("RESEARCH_EMAIL_PASSWORD", "")
    sender = os.environ.get("RESEARCH_EMAIL_SENDER", "")
    recipient = os.environ.get("RESEARCH_EMAIL_RECIPIENT", sender)
    if not password or not sender or not recipient:
        log.error("Email not configured (need RESEARCH_EMAIL_SENDER/PASSWORD/RECIPIENT) — cannot send alert")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = f"\u26a0\ufe0f Trading AI FAILED — {pipeline_name} — {now}"

    # Truncate error to last 2000 chars for email
    error_tail = error_msg[-2000:] if len(error_msg) > 2000 else error_msg

    body = f"""Trading AI pipeline "{pipeline_name}" failed at {now}.

Attempted {MAX_RETRIES + 1} times including a venv rebuild.

--- Last Error ---
{error_tail}

--- Action Required ---
SSH into your machine or open Terminal and run:
  cd {PROJECT_ROOT}
  {VENV_PYTHON} -m {PIPELINES.get(pipeline_name, ('???',))[0]}

If that fails, rebuild the venv (kept OUTSIDE iCloud to avoid corruption):
  rm -rf {VENV_DIR}
  /usr/local/bin/python3.11 -m venv {VENV_DIR}
  {VENV_DIR}/bin/pip install -r requirements.lock
"""

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
            s.starttls()
            s.login(sender, password)
            s.sendmail(sender, [recipient], msg.as_string())
        log.info("Alert email sent")
    except Exception as e:
        log.error(f"Failed to send alert email: {e}")

    # Also log to file
    with open(ALERT_LOG, "a") as f:
        f.write(f"\n{'='*60}\n{now} — {pipeline_name} FAILED\n{error_tail}\n")


def run_pipeline(module: str, extra_args: list) -> tuple[int, str]:
    """Run a pipeline module. Returns (exit_code, stderr)."""
    cmd = [VENV_PYTHON, "-m", module] + extra_args
    log.info(f"Running: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min hard timeout
    )

    # Combine stdout and stderr for logging
    output = result.stdout + "\n" + result.stderr
    if result.returncode != 0:
        log.error(f"Pipeline failed (exit {result.returncode})")
        log.error(output[-500:])
    else:
        log.info("Pipeline succeeded")

    return result.returncode, output


def find_base_python():
    """Locate a Python interpreter OUTSIDE the venv to rebuild it with.

    Never use sys.executable: when launchd runs this guard with the venv's own
    python, sys.executable's PATH lies inside VENV_DIR. `rm -rf venv` deletes
    that path (the python3.11 symlink) regardless of where it resolves to, so
    recreating the venv with it fails — leaving NO venv at all. We must use an
    interpreter whose *path* is physically outside VENV_DIR. realpath() is the
    wrong check here precisely because the venv python is a symlink that
    resolves to a base interpreter outside the venv.
    """
    venv_prefix = os.path.abspath(VENV_DIR) + os.sep
    candidates = [
        "/usr/local/bin/python3.11",
        "/opt/homebrew/bin/python3.11",
        "/usr/local/bin/python3",
        "/opt/homebrew/bin/python3",
        "/usr/bin/python3",
    ]
    for p in candidates:
        if (os.path.exists(p) and os.access(p, os.X_OK)
                and not os.path.abspath(p).startswith(venv_prefix)):
            return p
    return None


def rebuild_venv():
    """Nuke and rebuild the venv from pinned requirements."""
    log.info("=== REBUILDING VENV ===")

    if not os.path.exists(REQUIREMENTS_LOCK):
        log.error(f"No {REQUIREMENTS_LOCK} found — cannot auto-rebuild")
        return False

    base_python = find_base_python()
    if not base_python:
        log.error("No base python found outside the venv — cannot auto-rebuild")
        return False
    log.info(f"Using base python: {base_python}")

    try:
        # Remove corrupted venv. (A running process keeps executing even if its
        # own interpreter binary is unlinked, so this is safe mid-run.)
        if os.path.exists(VENV_DIR):
            subprocess.run(["rm", "-rf", VENV_DIR], check=True, timeout=60)

        # Create fresh venv with the external base python
        subprocess.run(
            [base_python, "-m", "venv", VENV_DIR],
            check=True, timeout=60,
        )

        # Install pinned deps
        pip = os.path.join(VENV_DIR, "bin", "pip")
        result = subprocess.run(
            [pip, "install", "--no-cache-dir", "-r", REQUIREMENTS_LOCK],
            capture_output=True, text=True,
            timeout=VENV_REBUILD_TIMEOUT,
        )
        if result.returncode != 0:
            log.error(f"pip install failed: {result.stderr[-500:]}")
            return False

        log.info("Venv rebuilt successfully")
        return True

    except Exception as e:
        log.error(f"Venv rebuild failed: {e}")
        return False


def is_import_error(output: str) -> bool:
    """Check if the failure is a broken import (venv corruption)."""
    markers = [
        "ModuleNotFoundError",
        "ImportError",
        "No module named",
        "_multiarray_umath",
        "cannot import name",
        "DLL load failed",
        "undefined symbol",
    ]
    return any(m in output for m in markers)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <{'|'.join(PIPELINES.keys())}> [extra args...]")
        sys.exit(1)

    pipeline_name = sys.argv[1]
    extra_cli_args = sys.argv[2:]

    if pipeline_name not in PIPELINES:
        print(f"Unknown pipeline: {pipeline_name}")
        print(f"Available: {', '.join(PIPELINES.keys())}")
        sys.exit(1)

    module, default_args = PIPELINES[pipeline_name]
    args = extra_cli_args if extra_cli_args else default_args

    os.makedirs(LOG_DIR, exist_ok=True)

    # --- Attempt 1: Just run it ---
    exit_code, output = run_pipeline(module, args)
    if exit_code == 0:
        return

    # --- Attempt 2: If import error, rebuild venv and retry ---
    if is_import_error(output):
        log.info("Detected import/module error — attempting venv rebuild...")
        if rebuild_venv():
            log.info("Retrying pipeline after venv rebuild...")
            exit_code, output = run_pipeline(module, args)
            if exit_code == 0:
                return
            log.error("Pipeline still failing after venv rebuild")
        else:
            log.error("Venv rebuild failed")
    else:
        # Non-import error — retry once in case it was transient (network, etc.)
        log.info("Non-import error — retrying in 30s...")
        time.sleep(30)
        exit_code, output = run_pipeline(module, args)
        if exit_code == 0:
            return

    # --- All retries exhausted — send alert ---
    log.error("ALL RETRIES EXHAUSTED — sending alert email")
    send_alert_email(pipeline_name, output)
    sys.exit(1)


if __name__ == "__main__":
    main()

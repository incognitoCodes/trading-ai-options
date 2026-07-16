"""
email_sender.py — Email Delivery Agent with retry logic.

Sends HTML research reports via Gmail SMTP with automatic retries
and exponential backoff to ensure delivery.

Setup:
  1. Enable 2-Step Verification on your Google Account
  2. Go to myaccount.google.com -> Security -> App passwords
  3. Generate a new app password for "Mail"
  4. Set RESEARCH_EMAIL_PASSWORD env variable (or in .env)
"""

import smtplib
import logging
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from research_agents.config import (
    EMAIL_RECIPIENTS,
    EMAIL_SENDER,
    EMAIL_PASSWORD,
    SMTP_SERVER,
    SMTP_PORT,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 30  # seconds


class EmailSender:
    """Sends HTML reports via email with retry logic."""

    def send_report(
        self,
        html_content: str,
        subject: str = None,
        recipients: list[str] = None,
    ) -> bool:
        """Send an HTML email report with automatic retries.

        Retries up to MAX_RETRIES times with exponential backoff
        on transient failures (network, SMTP server issues).
        Returns True if sent to at least one recipient.
        """
        if not EMAIL_PASSWORD:
            logger.warning(
                "Email password not set. Set RESEARCH_EMAIL_PASSWORD env var. "
                "Report saved to file but not emailed."
            )
            return False

        to_addrs = recipients or EMAIL_RECIPIENTS
        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]

        if not subject:
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            subject = f"Global Markets Daily \u2014 {date_str}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = ", ".join(to_addrs)

        # Plain text fallback
        plain_text = (
            "Your daily research report is attached as HTML. "
            "Please view this email in an HTML-capable client."
        )
        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                    server.sendmail(EMAIL_SENDER, to_addrs, msg.as_string())
                logger.info(f"Report emailed to {', '.join(to_addrs)} (attempt {attempt})")
                return True

            except smtplib.SMTPAuthenticationError:
                logger.error(
                    "SMTP authentication failed. Check your App Password. "
                    "Make sure 2-Step Verification is enabled and you're using "
                    "an App Password, not your regular Gmail password."
                )
                return False  # Don't retry auth failures

            except smtplib.SMTPRecipientsRefused as e:
                logger.error(f"All recipients refused: {e}")
                return False  # Don't retry recipient issues

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        f"Email attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                        f"Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"Email delivery failed after {MAX_RETRIES} attempts. "
                        f"Last error: {last_error}"
                    )

        return False

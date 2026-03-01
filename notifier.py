"""Telegram notification module for NEAR AI marketplace bot.

Sends alerts when bids are won, delivered, or paid.
"""

import logging
import os

import requests

log = logging.getLogger("autobidder")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram(text: str) -> bool:
    """Send a message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.debug("Telegram not configured, skipping notification")
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return False


def notify_bid_won(title: str, amount: str, job_id: str, tags: list = None):
    """Notify that a bid was won and needs delivery."""
    tag_str = ", ".join(tags) if tags else "none"
    text = (
        f"🏆 *BID WON*\n\n"
        f"*{title}*\n"
        f"💰 {amount} NEAR\n"
        f"🏷 {tag_str}\n"
        f"🔑 `{job_id[:12]}...`\n\n"
        f"⏳ Awaiting delivery — run deliver command in Claude Code"
    )
    _send_telegram(text)


def notify_delivered(title: str, amount: str, gist_url: str):
    """Notify that a deliverable was submitted."""
    text = (
        f"📦 *DELIVERED*\n\n"
        f"*{title}*\n"
        f"💰 {amount} NEAR\n"
        f"🔗 [Gist]({gist_url})"
    )
    _send_telegram(text)


def notify_paid(title: str, amount: str):
    """Notify that payment was received."""
    text = (
        f"💸 *PAID*\n\n"
        f"*{title}*\n"
        f"💰 +{amount} NEAR received!"
    )
    _send_telegram(text)

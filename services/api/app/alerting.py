"""Ops alerting for the AI spend rollups: Slack webhook + email dispatch.

Both channels are **fail-open** — alerting must never break the nightly
rollup job. Every function returns ``True``/``False`` for "dispatched" and
logs failures loudly instead of raising. Channels with empty configuration
(``SLACK_ALERT_WEBHOOK_URL`` / ``ALERT_EMAIL_TO``) are skipped silently-ish
(debug log), so an environment with no alerting configured pays nothing.

Slack uses a tiny httpx POST of the incoming-webhook ``{"text": ...}`` shape
— no slack-sdk dependency.
"""

from __future__ import annotations

import httpx
import structlog

from app.config import ALERT_EMAIL_TO, SLACK_ALERT_WEBHOOK_URL
from app.email import send_event_email

logger = structlog.get_logger("api.alerting")

_SLACK_TIMEOUT_SECONDS = 5.0


async def send_slack_alert(text: str, webhook_url: str | None = None) -> bool:
    """POST one plain-text alert to the Slack incoming webhook. Never raises."""
    url = (webhook_url if webhook_url is not None else SLACK_ALERT_WEBHOOK_URL).strip()
    if not url:
        logger.debug("slack_alert_skipped", reason="no_webhook_configured")
        return False
    try:
        async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json={"text": text})
        if response.status_code >= 400:
            logger.warning(
                "slack_alert_failed",
                status_code=response.status_code,
                body=response.text[:200],
            )
            return False
        logger.info("slack_alert_dispatched")
        return True
    except Exception as exc:
        logger.warning(
            "slack_alert_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return False


async def send_alert(subject: str, text: str) -> dict[str, bool]:
    """Dispatch one ops alert to every configured channel. Never raises.

    Returns a per-channel dispatch map, e.g. ``{"email": True, "slack":
    False}``; a channel is only present when it is configured.
    """
    results: dict[str, bool] = {}
    if ALERT_EMAIL_TO:
        delivered = await send_event_email(
            to_email=ALERT_EMAIL_TO,
            subject=subject,
            html_body=f"<p>{text}</p>",
            text_body=text,
            event="ai_ops_alert",
            template="ai_ops_alert",
            context={"alert_subject": subject},
        )
        results["email"] = delivered
    if SLACK_ALERT_WEBHOOK_URL:
        results["slack"] = await send_slack_alert(f"*{subject}*\n{text}")
    if not results:
        logger.warning("alert_no_channels", subject=subject)
    return results


async def fetch_usd_gbp_rate() -> float | None:
    """Fetch the current USD→GBP rate from a free endpoint. Never raises.

    Uses the open exchangerate.host latest endpoint with a short timeout;
    returns ``None`` on any failure so the caller keeps the last-known rate.
    """
    url = "https://api.exchangerate.host/latest?base=USD&symbols=GBP"
    try:
        async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            logger.warning("fx_refresh_failed", status_code=response.status_code)
            return None
        data = response.json()
        rate = data.get("rates", {}).get("GBP")
        if rate is None:
            logger.warning("fx_refresh_failed", reason="no_gbp_in_response")
            return None
        return float(rate)
    except Exception as exc:
        logger.warning(
            "fx_refresh_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return None


__all__ = ["fetch_usd_gbp_rate", "send_alert", "send_slack_alert"]

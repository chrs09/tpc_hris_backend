"""Posts messages to Slack via an Incoming Webhook -- currently used
only to alert #production-errors when the API throws an unhandled
exception (see the global exception handler in app/main.py). Kept
generic (just a webhook URL + text) so any future alert can reuse it.
"""

import logging

import requests

from app.core.config import Settings

logger = logging.getLogger("slack")


def send_slack_alert(webhook_url: str | None, text: str) -> bool:
    """Posts a plain-text message to a Slack Incoming Webhook. Returns
    True on success, False on any failure (missing config, network
    error, Slack rejecting the payload, etc.) -- this must never raise,
    since it's called from inside error-handling paths and a broken
    Slack integration should never itself crash the request it's
    trying to report on."""

    if not webhook_url:
        logger.warning("Slack alert not sent (no webhook URL configured): %s", text)
        return False

    try:
        response = requests.post(
            webhook_url,
            json={"text": text},
            timeout=5,
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to post Slack alert")
        return False


def send_error_alert(method: str, url: str, exc: Exception, traceback_text: str) -> bool:
    """The specific alert posted for an unhandled server error (always a
    500) -- kept as its own function so the message formatting lives in
    one place instead of being built inline in the exception handler."""

    # Slack truncates/renders very long messages awkwardly -- cap the
    # traceback so one giant stack trace doesn't dominate the channel.
    trimmed_traceback = traceback_text[-2500:]

    text = (
        f":rotating_light: *Unhandled server error (500)*\n"
        f"*Request:* `{method} {url}`\n"
        f"*Error:* `{type(exc).__name__}: {exc}`\n"
        f"```{trimmed_traceback}```"
    )

    return send_slack_alert(Settings.SLACK_ERRORS_WEBHOOK_URL, text)


def send_response_alert(method: str, url: str, status_code: int, detail) -> bool:
    """The alert posted for a request that finished with a "watched"
    client-error status (400, 422 -- see ALERT_STATUS_CODES in
    app/main.py) rather than an unhandled crash. No traceback here since
    there isn't one -- these are FastAPI/Pydantic validation failures or
    an endpoint deliberately raising HTTPException, not a Python
    exception bubbling up."""

    # `detail` can be a plain string (HTTPException) or a list of
    # Pydantic error dicts (RequestValidationError) -- stringify either
    # way and cap the length for the same reason as the traceback above.
    detail_text = str(detail)[:1500]

    text = (
        f":warning: *Request failed ({status_code})*\n"
        f"*Request:* `{method} {url}`\n"
        f"*Detail:* ```{detail_text}```"
    )

    return send_slack_alert(Settings.SLACK_ERRORS_WEBHOOK_URL, text)

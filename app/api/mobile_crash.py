# app/api/mobile_crash.py
#
# Lets the mobile app (tytan_mobile) self-report a crash to Slack. A
# native "keeps stopping" crash is almost always a fatal, uncaught JS
# exception in a release build (React Native force-closes the app on
# one instead of showing a red error screen) -- the mobile app installs
# a global JS error handler (see src/utils/crashReporter.ts) that POSTs
# here right before the app closes. No auth required: the crash may
# happen before login ever succeeds, or with an expired/corrupt token,
# so this can't depend on a valid Bearer token being available.
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import Settings
from app.services.slack_service import send_slack_alert

router = APIRouter(prefix="/mobile", tags=["Mobile"])


class CrashReport(BaseModel):
    message: str
    stack: str | None = None
    is_fatal: bool | None = None
    screen: str | None = None
    app_version: str | None = None
    platform: str | None = None
    username: str | None = None


@router.post("/crash-report")
def report_crash(payload: CrashReport):
    trimmed_stack = (payload.stack or "")[-2500:]

    text = (
        f":boom: *Mobile app crash* ({'fatal' if payload.is_fatal else 'non-fatal'})\n"
        f"*User:* {payload.username or 'unknown/not logged in'}\n"
        f"*Platform:* {payload.platform or 'unknown'}"
        f"{f' (app v{payload.app_version})' if payload.app_version else ''}\n"
        f"*Screen:* {payload.screen or 'unknown'}\n"
        f"*Error:* `{payload.message}`\n"
        + (f"```{trimmed_stack}```" if trimmed_stack else "")
    )

    sent = send_slack_alert(Settings.SLACK_ERRORS_WEBHOOK_URL, text)

    # Always 200 -- this is best-effort reporting on the way out the
    # door for a crashing app; the client isn't waiting around to retry.
    return {"reported": sent}

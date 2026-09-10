"""Outgoing email via SMTP (Gmail by default -- see app/core/config.py
and .env for the SMTP_* settings and how to generate a Gmail App
Password). Currently only used to send applicants their generated
employment/onboarding form link, but written generically so any future
feature can send email through the same function.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import Settings

logger = logging.getLogger("email")


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Sends one HTML email. Returns True on success, False on any
    failure (missing config, network/auth error, etc.) -- callers should
    treat email as best-effort and never let a failed send block the
    action that triggered it (e.g. generating a form link should still
    succeed even if the email didn't go out; HR can resend/share the
    link manually)."""

    if not Settings.SMTP_USERNAME or not Settings.SMTP_PASSWORD:
        # Not configured yet (e.g. SMTP_PASSWORD left blank in .env) --
        # log and skip rather than raising, so the rest of the app keeps
        # working while email is being set up.
        logger.warning(
            "Email not sent to %s (\"%s\") -- SMTP_USERNAME/SMTP_PASSWORD "
            "not configured in .env.",
            to_email,
            subject,
        )
        return False

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{Settings.SMTP_FROM_NAME} <{Settings.SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message.attach(MIMEText(html_body, "html"))

    try:
        # STARTTLS on port 587 is what Gmail (and most providers) expect
        # -- a plain, unencrypted connection is upgraded to TLS before
        # login/send.
        with smtplib.SMTP(Settings.SMTP_HOST, Settings.SMTP_PORT) as server:
            server.starttls()
            server.login(Settings.SMTP_USERNAME, Settings.SMTP_PASSWORD)
            server.sendmail(Settings.SMTP_FROM_EMAIL, [to_email], message.as_string())
        return True
    except Exception:
        logger.exception("Failed to send email to %s (\"%s\")", to_email, subject)
        return False


def send_employment_form_email(
    to_email: str, applicant_name: str, form_url: str, expires_at
) -> bool:
    """The specific email sent when HR generates an applicant's
    employment/onboarding form -- kept as its own function so the HTML
    template lives in one place instead of being built inline at the
    call site in app/api/admin/applicants.py."""

    subject = "Your Employment Form is Ready - Tytan Prime Corporation"
    expires_text = expires_at.strftime("%B %d, %Y") if expires_at else "soon"

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto;">
        <h2 style="color: #0F172A;">Hello {applicant_name},</h2>
        <p style="color: #334155; font-size: 14px; line-height: 1.6;">
            Congratulations! Your application has been reviewed. Please
            complete your employment form using the link below so we can
            continue processing your onboarding.
        </p>
        <p style="text-align: center; margin: 24px 0;">
            <a href="{form_url}"
               style="background-color: #2563EB; color: #FFFFFF; padding: 12px 24px;
                      border-radius: 8px; text-decoration: none; font-weight: bold;
                      display: inline-block;">
                Complete Employment Form
            </a>
        </p>
        <p style="color: #64748B; font-size: 12px;">
            This link expires on {expires_text}. If the button above
            doesn't work, copy and paste this URL into your browser:
            <br />{form_url}
        </p>
        <p style="color: #64748B; font-size: 12px; margin-top: 24px;">
            If you weren't expecting this email, you can safely ignore it.
        </p>
    </div>
    """

    return send_email(to_email, subject, html_body)

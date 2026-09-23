from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

# Anchors relative paths (UPLOAD_FOLDER's default) to this project's own
# location on disk, rather than to whatever directory the process happens
# to be launched from. Two uvicorn processes started from different
# working directories (e.g. one from this project's own folder, another
# from a different root a dev server happens to be launched from) used to
# each resolve the "uploads" default to a different physical folder --
# same database, two disjoint sets of files on disk, so whichever process
# actually handled a given upload determined whether it could later be
# found again by whichever process handled the view request.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings:
    # ===============================
    # APP
    # ===============================
    APP_NAME = os.getenv("APP_NAME", "FastAPI Application")
    ENV = os.getenv("ENV", "development")

    # ===============================
    # FRONTEND
    # ===============================
    FRONTEND_URL = os.getenv(
        "FRONTEND_URL",
        "http://localhost:5173"
    )

    # ===============================
    # EXPO / EAS (tytan_mobile build sync)
    # ===============================
    # Personal/robot access token from expo.dev -> account settings ->
    # Access Tokens. Only needed for the "Sync from EAS" button on the
    # Mobile App Version settings page -- everything else in this app
    # works without it.
    EXPO_ACCESS_TOKEN = os.getenv("EXPO_ACCESS_TOKEN")
    EXPO_PROJECT_ID = os.getenv(
        "EXPO_PROJECT_ID", "3fe48054-860c-47ff-a5ec-971d404a8ee0"
    )

    # ===============================
    # FILE STORAGE
    # ===============================
    FILE_STORAGE = os.getenv("FILE_STORAGE", "local")

    # Absolute by default (see PROJECT_ROOT above) so every process finds
    # the same physical folder no matter what directory it was launched
    # from. Still overridable via .env for a deployment that genuinely
    # wants a different location (e.g. a mounted volume).
    UPLOAD_FOLDER = os.getenv(
        "UPLOAD_FOLDER",
        str(PROJECT_ROOT / "uploads"),
    )

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    AZURE_CONTAINER = os.getenv(
        "AZURE_CONTAINER",
        "tpc_files"
    )

    # ===============================
    # AWS S3
    # ===============================
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
    AWS_REGION = os.getenv("AWS_REGION")

    # ===============================
    # API
    # ===============================
    API_BASE_URL = os.getenv(
        "API_BASE_URL",
        "http://localhost:8000"
    )

    # ===============================
    # DATABASE
    # ===============================
    DATABASE_URL = os.getenv("DATABASE_URL")

    # ===============================
    # SECURITY
    # ===============================
    SECRET_KEY = os.getenv("SECRET_KEY")

    ALGORITHM = os.getenv(
        "ALGORITHM",
        "HS256"
    )

    ACCESS_TOKEN_EXPIRE_MINUTES = int(
        os.getenv(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            2160
        )
    )

    REFRESH_TOKEN_EXPIRE_DAYS = int(
        os.getenv(
            "REFRESH_TOKEN_EXPIRE_DAYS",
            30
        )
    )

    # ===============================
    # EMAIL (SMTP)
    # ===============================
    # Used by app/services/email_service.py to send the generated
    # applicant onboarding/employment form link. SMTP_PASSWORD must be a
    # Gmail "App Password" (not the account's normal login password) when
    # SMTP_HOST is Gmail -- see .env for how to generate one.
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Tytan Prime Corporation HR")

    # ===============================
    # SLACK ALERTS
    # ===============================
    # Incoming Webhook for #production-errors -- posted to whenever the
    # API throws an unhandled exception or returns an error status (see
    # the exception handlers in app/main.py / app/services/slack_service.py).
    SLACK_ERRORS_WEBHOOK_URL = os.getenv("SLACK_ERRORS_WEBHOOK_URL")

    # Incoming Webhook for #server-monitoring -- NOT called by this
    # backend. It's meant to be pasted into an external uptime pinger
    # (UptimeRobot, Better Uptime, etc.) configured to hit GET /api/health
    # and alert this webhook when the server stops responding. Kept here
    # only for reference/documentation, not read anywhere in code.
    SLACK_UPTIME_WEBHOOK_URL = os.getenv("SLACK_UPTIME_WEBHOOK_URL")

    # ===============================
    # CORS
    # ===============================
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            ""
        ).split(",")
        if origin.strip()
    ]


settings = Settings()
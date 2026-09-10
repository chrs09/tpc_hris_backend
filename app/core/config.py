from dotenv import load_dotenv
import os

load_dotenv()


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
    # FILE STORAGE
    # ===============================
    FILE_STORAGE = os.getenv("FILE_STORAGE", "local")

    # Keep uploads inside the backend project.
    # This works on both local development
    # and the office server.
    UPLOAD_FOLDER = os.getenv(
        "UPLOAD_FOLDER",
        "uploads"
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
    # API throws an unhandled exception (see the global exception
    # handler in app/main.py / app/services/slack_service.py).
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
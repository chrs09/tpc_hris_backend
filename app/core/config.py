from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    # APP
    APP_NAME = os.getenv("APP_NAME", "FastAPI Application")
    ENV = os.getenv("ENV", "development")

    # FRONTEND
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # FILE STORAGE
    FILE_STORAGE = os.getenv("FILE_STORAGE", "local")
    AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    AZURE_CONTAINER = os.getenv("AZURE_CONTAINER", "tpc_files")

    # AWS S3
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")
    AWS_REGION = os.getenv("AWS_REGION")

    API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

    # DATABASE
    DATABASE_URL = os.getenv("DATABASE_URL")

    # SECURITY
    SECRET_KEY = os.getenv("SECRET_KEY")
    ALGORITHM = os.getenv("ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")


settings = Settings()

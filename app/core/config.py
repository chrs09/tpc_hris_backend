from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    # APP
    APP_NAME = os.getenv("APP_NAME", "FastAPI Application")
    ENV = os.getenv("ENV", "development")

    # FILE STORAGE
    FILE_STORAGE = os.getenv("FILE_STORAGE", "local")
    AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    AZURE_CONTAINER = os.getenv("AZURE_CONTAINER", "tpc_files")

    # DATABASE
    DATABASE_URL = os.getenv("DATABASE_URL")

    # SECURITY
    SECRET_KEY = os.getenv("SECRET_KEY")
    ALGORITHM = os.getenv("ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")


settings = Settings()

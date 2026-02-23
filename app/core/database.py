from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
import os

DATABASE_URL = settings.DATABASE_URL

# Enable SSL only when running in Azure
if os.getenv("WEBSITE_HOSTNAME"):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"ssl": {"fake_flag_to_enable_tls": True}},
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

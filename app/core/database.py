from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
import os

DATABASE_URL = settings.DATABASE_URL

# Connection pool. The default (5 + 10 overflow) ran out under load --
# every open page polls several alert bells -- and requests then failed
# with "QueuePool limit ... reached". 20 + 20 = 40 matches FastAPI's 40
# worker threads and stays well under MySQL's default 151 connections
# (if the server ever runs several workers, lower these per worker).
# pool_recycle drops connections idle past MySQL's timeout.
POOL_OPTIONS = {
    "pool_pre_ping": True,
    "pool_size": int(os.getenv("DB_POOL_SIZE", "20")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
    "pool_timeout": 30,
    "pool_recycle": 1800,
}

# Enable SSL only when running in Azure
if os.getenv("WEBSITE_HOSTNAME"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"ssl": {"fake_flag_to_enable_tls": True}},
        **POOL_OPTIONS,
    )
else:
    engine = create_engine(DATABASE_URL, **POOL_OPTIONS)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

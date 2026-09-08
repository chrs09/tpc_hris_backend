from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class AppSetting(Base):
    """Generic key/value store for small, single-value application settings
    that should be admin-editable in the database instead of a hardcoded
    constant in code (e.g. a feature toggle, or which switch a background
    calculation should use).

    Not for structured/business records with many fields or many rows of
    the same shape -- those belong in their own dedicated table. This is
    only for standalone settings like `wallet_settlement_source` below.
    """

    __tablename__ = "tpc_app_settings"

    id = Column(Integer, primary_key=True, index=True)

    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(255), nullable=False)

    description = Column(Text, nullable=True)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

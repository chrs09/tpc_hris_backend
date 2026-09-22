from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class MobileAppVersion(Base):
    """Latest published tytan_mobile version per platform, editable by
    superadmin -- one row per `platform` (only "android" for now, since
    that's the only channel being sideloaded outside Google Play).

    The app checks this on launch and compares against its own running
    version (expo-constants) to prompt testers to update, since a
    directly-distributed APK has no store-driven update mechanism of its
    own. `min_supported_version` is a harder floor than `latest_version`
    -- below it the app should treat the prompt as non-dismissible
    (blocking), whereas being merely behind `latest_version` is a
    dismissible "update available" nudge.
    """

    __tablename__ = "tpc_mobile_app_versions"

    id = Column(Integer, primary_key=True, index=True)

    platform = Column(String(20), nullable=False, unique=True, index=True)

    latest_version = Column(String(20), nullable=False)
    min_supported_version = Column(String(20), nullable=False)

    apk_url = Column(Text, nullable=False)
    release_notes = Column(Text, nullable=True)

    updated_by_user_id = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    updated_by = relationship("User", foreign_keys=[updated_by_user_id])

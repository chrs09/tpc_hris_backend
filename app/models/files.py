from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.core.database import Base


class File(Base):
    __tablename__ = "tpc_files"

    __table_args__ = (
        Index("idx_entity_lookup", "entity_type", "entity_id"),
        Index("idx_document_lookup", "entity_type", "entity_id", "document_type"),
    )

    id = Column(Integer, primary_key=True, index=True)

    entity_type = Column(String(50), nullable=False)   # "employee", "trip"
    entity_id = Column(Integer, nullable=False)

    document_type = Column(String(50), nullable=False) # "RESUME", "PROFILE_IMAGE"

    file_url = Column(String(500), nullable=False)

    uploaded_by = Column(Integer, ForeignKey("tpc_users.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())

    # __table_args__ = (Index("idx_entity_lookup", "entity_type", "entity_id"),)

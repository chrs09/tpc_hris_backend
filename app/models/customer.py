from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Customer(Base):
    """A customer account on the Customer Chart (Customers -> Customer
    Chart): a tree under the company like the Org Chart -- a customer can
    have sub-customers (parent_id). Each one has its own tiers
    (CustomerTier), and every location (Store) belongs to one tier, so to
    one customer. Trip Dispatch starts from the customer -> tier; the
    tier says where the trip's rate comes from (app/services/customer_tiers.py)."""

    __tablename__ = "tpc_customers"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(150), nullable=False, index=True)
    contact_person = Column(String(150), nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(150), nullable=True)
    address = Column(String(255), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    # Customer Chart: the customer above (None = directly under the company).
    parent_id = Column(Integer, ForeignKey("tpc_customers.id"), nullable=True, index=True)
    # Short code shown on trips / reports (e.g. "CCBPI").
    code = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)

    tiers = relationship(
        "CustomerTier",
        back_populates="customer",
        order_by="CustomerTier.sort_order",
    )


# Where a tier's trip rate comes from.
RATE_SOURCE_LANE = "lane"  # Driver Rates lane rule: truck type + origin -> location
RATE_SOURCE_TRIP_PROFILE = "trip_profile"  # the location's trip profile (DP, KD, ...)
RATE_SOURCES = (RATE_SOURCE_LANE, RATE_SOURCE_TRIP_PROFILE)


class CustomerTier(Base):
    """A service tier a customer has (T1, T1.5, T2 ... -- fully dynamic):
    its own list of locations (Store.customer_tier_id) and where the trip
    rate comes from (rate_source). E.g. Coca-Cola -> T1 = plant / DC
    lanes paid by lane rate; T2 = outlet deliveries paid by trip profile."""

    __tablename__ = "tpc_customer_tiers"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("tpc_customers.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    rate_source = Column(String(20), nullable=False, default=RATE_SOURCE_TRIP_PROFILE)
    # JSON list of tpc_truck_types ids allowed on this tier; empty = any.
    truck_type_ids = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    customer = relationship("Customer", back_populates="tiers")

import enum


class TripStatus(str, enum.Enum):
    ASSIGNED = "ASSIGNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class StopStatus(str, enum.Enum):
    PENDING = "PENDING"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    SKIPPED = "SKIPPED"


class GPSActionType(str, enum.Enum):
    TRACK = "TRACK"
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"

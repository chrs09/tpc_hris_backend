"""Date filter for trip lists (Trip Approvals, a driver's own trips).

Either a trip-pay cutoff -- "2026-11-1" = Nov 1-15, "2026-11-2" =
Nov 16-30, the same periods as the driver's wallet
(trip_payroll_service.period_bounds) -- or a PH date range
("YYYY-MM-DD", either end optional). Matched on the trip's start time,
the field the wallet's cutoffs use.
"""

from datetime import datetime, timedelta

from fastapi import HTTPException

from app.models.trips import Trip
from app.services.trip_payroll_service import parse_cutoff_value, period_bounds
from app.utils.timezone import ph_to_utc


def _day(value: str, label: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label} date.")


def filter_trip_dates(query, cutoff: str | None = None, date_from: str | None = None, date_to: str | None = None):
    if cutoff:
        try:
            start_utc, end_utc, _, _ = period_bounds(parse_cutoff_value(cutoff))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cutoff.")
        return query.filter(Trip.start_time >= start_utc, Trip.start_time <= end_utc)
    if date_from:
        query = query.filter(Trip.start_time >= ph_to_utc(_day(date_from, "from")))
    if date_to:
        # Through the end of that day (PH).
        query = query.filter(Trip.start_time < ph_to_utc(_day(date_to, "to") + timedelta(days=1)))
    return query

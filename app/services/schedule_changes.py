"""Approved schedule changes: the expected time in / out of one date
(app/models/schedule_change.py), on top of the regular work schedule.

Times are PH wall-clock. The backend's schedule readers (missed time in
alerts, overtime) use the template time as PH, so an approved change
replaces it directly; the web payroll / attendance pages convert it to
the template's stored form (see tpc_hris_frontend
utils/payroll/attendance/scheduleOverrides.js).
"""

from datetime import date, time

from sqlalchemy.orm import Session

from app.models.schedule_change import ScheduleChangeRequest


def approved_changes(
    db: Session, employee_ids, start: date, end: date
) -> dict[tuple[int, date], tuple[time, time]]:
    """{(employee_id, date): (time_in, time_out)} approved in start..end."""
    query = db.query(ScheduleChangeRequest).filter(
        ScheduleChangeRequest.status == "approved",
        ScheduleChangeRequest.schedule_date >= start,
        ScheduleChangeRequest.schedule_date <= end,
    )
    if employee_ids is not None:
        ids = list(employee_ids)
        if not ids:
            return {}
        query = query.filter(ScheduleChangeRequest.employee_id.in_(ids))
    return {(c.employee_id, c.schedule_date): (c.time_in, c.time_out) for c in query}


def approved_change(db: Session, employee_id: int | None, day: date) -> tuple[time, time] | None:
    if not employee_id:
        return None
    return approved_changes(db, [employee_id], day, day).get((employee_id, day))

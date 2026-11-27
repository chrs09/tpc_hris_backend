"""How a trip was carried out, for the badge on Trip Details:

- "manual"  -- entered by hand in Trip Manual Entries;
- "bypass"  -- the driver app was used, but at least one step was done by
               the office for the driver (Trip Bypass);
- "app"     -- every step came from the driver's phone.

Both come from TripBypassLog: manual entries log "manual-entry", bypassed
steps log the step name ("checkout", "check-in", ...). Edits, reorders and
corrections are logged there too but aren't steps, so they don't count.
"""

from sqlalchemy.orm import Session

from app.models.trip_bypass_log import TripBypassLog
from app.models.trip_helper import TripHelper

NOT_A_STEP = {"edit", "correction", "reorder", "cancel", "fix", "returned", "change-category"}

STEP_LABELS = {
    "checkout": "Checkout",
    "start": "Start",
    "check-in": "Arrived at store",
    "start-unloading": "Start unloading",
    "check-out": "Delivered",
    "checkin": "Checkin",
    "back-to-source": "Back to source",
}


def trip_sources(db: Session, trip_ids) -> dict[int, dict]:
    ids = [int(i) for i in trip_ids if i]
    result = {i: {"source": "app", "bypassed_steps": []} for i in ids}
    if not ids:
        return result
    for trip_id, action in db.query(TripBypassLog.trip_id, TripBypassLog.action).filter(
        TripBypassLog.trip_id.in_(ids)
    ):
        action = (action or "").strip()
        entry = result[trip_id]
        if action.startswith("manual-entry"):
            entry["source"] = "manual"
        elif action and action not in NOT_A_STEP:
            label = STEP_LABELS.get(action, action.replace("-", " ").capitalize())
            if label not in entry["bypassed_steps"]:
                entry["bypassed_steps"].append(label)
            if entry["source"] != "manual":
                entry["source"] = "bypass"
    return result


def trip_helpers(db: Session, trip_ids) -> dict[int, list[dict]]:
    """{trip_id: [{id, name, is_driver}]} -- names tagged when a driver
    rides as a helper (Driver as Helper)."""
    from app.services.user_roles import driver_employee_ids, helper_name

    ids = [int(i) for i in trip_ids if i]
    if not ids:
        return {}
    driver_ids = driver_employee_ids(db)
    out: dict[int, list[dict]] = {}
    for row in db.query(TripHelper).filter(TripHelper.trip_id.in_(ids)).order_by(TripHelper.id):
        if not row.helper:
            continue
        out.setdefault(row.trip_id, []).append(
            {
                "id": row.helper.id,
                "name": helper_name(row.helper, driver_ids),
                "is_driver": row.helper.id in driver_ids
                and (row.helper.position or "").upper() != "HELPER",
            }
        )
    return out

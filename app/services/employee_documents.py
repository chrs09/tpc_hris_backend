"""201 Employment Files: which documents each employee should have, and
which ones expire -- shared by the 201 (app/api/employees.py) and the HR
Dashboard (app/api/hr_dashboard.py)."""

from datetime import date

from sqlalchemy.orm import Session

from app.models.employee_document_expiry import EmployeeDocumentExpiry

DRIVER_DEPARTMENTS = {"CdcDriver", "CpdcDriver", "WingvanDriver"}

DOC_LABELS = {
    "PROFILE_IMAGE": "Profile Image",
    "CV": "CV",
    "CONTRACT": "Contract",
    "NBI_CLEARANCE": "NBI Clearance",
    "BRGY_CLEARANCE": "Barangay Clearance",
    "COMPANY_ID": "Company ID",
    "ACCOUNTABILITY": "Accountability",
    "ACCOUNT_NUMBER": "Proof of Account",
    "LICENSE": "Driver's License",
    "LICENSE_BACK": "Driver's License (Back)",
    "POLICE_CLEARANCE": "Police Clearance",
    "HEALTHCARD": "Health Card",
    "XRAY": "X-Ray",
    "SSS": "SSS",
    "PAGIBIG": "Pag-IBIG",
    "PHILHEALTH": "PhilHealth",
    "NC3": "NC3",
    "DEFENSIVE_DRIVING": "Defensive Driving Certificate",
}

# Lacking docs: what every active employee should have on file ...
REQUIRED_FOR_ALL = [
    "PROFILE_IMAGE",
    "CV",
    "CONTRACT",
    "NBI_CLEARANCE",
    "BRGY_CLEARANCE",
    "HEALTHCARD",
    "XRAY",
    "SSS",
    "PAGIBIG",
    "PHILHEALTH",
]
# ... plus, for drivers:
REQUIRED_FOR_DRIVERS = [
    "LICENSE",
    "LICENSE_BACK",
    "POLICE_CLEARANCE",
    "NC3",
    "DEFENSIVE_DRIVING",
]

# Documents that expire unless HR unticks "Has expiry" on the 201 (any
# other document can be ticked too).
EXPIRING_BY_DEFAULT = {
    "LICENSE",
    "NC3",
    "DEFENSIVE_DRIVING",
    "NBI_CLEARANCE",
    "POLICE_CLEARANCE",
    "HEALTHCARD",
    "XRAY",
}

# "Nearing expiry" window.
WARN_DAYS = 60


def is_driver(department: str | None) -> bool:
    return (department or "") in DRIVER_DEPARTMENTS


def required_documents(department: str | None) -> list[str]:
    return REQUIRED_FOR_ALL + (REQUIRED_FOR_DRIVERS if is_driver(department) else [])


def expiry_map(db: Session, employee_ids: list[int]) -> dict[int, dict[str, EmployeeDocumentExpiry]]:
    if not employee_ids:
        return {}
    out: dict[int, dict[str, EmployeeDocumentExpiry]] = {}
    for row in (
        db.query(EmployeeDocumentExpiry)
        .filter(EmployeeDocumentExpiry.employee_id.in_(employee_ids))
        .all()
    ):
        out.setdefault(row.employee_id, {})[row.document_type] = row
    return out


def expiry_payload(rows: dict[str, EmployeeDocumentExpiry]) -> dict:
    """{document_type: {has_expiry, expiry_date}} for the 201 -- every
    expiring-by-default type plus anything HR has saved."""
    out = {
        doc: {"has_expiry": True, "expiry_date": None} for doc in EXPIRING_BY_DEFAULT
    }
    for doc, row in rows.items():
        out[doc] = {
            "has_expiry": bool(row.has_expiry),
            "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None,
        }
    return out


def save_expiries(db: Session, employee_id: int, data: dict, user_id: int | None) -> None:
    """data: {document_type: {has_expiry: bool, expiry_date: "YYYY-MM-DD" | null}}."""
    existing = expiry_map(db, [employee_id]).get(employee_id, {})
    for doc, value in (data or {}).items():
        if doc not in DOC_LABELS or not isinstance(value, dict):
            continue
        has_expiry = bool(value.get("has_expiry"))
        raw = value.get("expiry_date") or None
        expiry = None
        if raw and has_expiry:
            try:
                expiry = date.fromisoformat(str(raw)[:10])
            except ValueError:
                expiry = None
        row = existing.get(doc)
        if row is None:
            # Nothing to store for an untouched default.
            if has_expiry == (doc in EXPIRING_BY_DEFAULT) and expiry is None:
                continue
            row = EmployeeDocumentExpiry(employee_id=employee_id, document_type=doc)
            db.add(row)
        row.has_expiry = has_expiry
        row.expiry_date = expiry
        row.updated_by_user_id = user_id

"""HRIS -> HR Dashboard: 201 compliance at a glance.

- Lacking docs: completion of each active employee's required Employment
  Files (app/services/employee_documents.py), by document and department.
- Nearing expiry: documents whose expiry date is past or within WARN_DAYS.
- Government ID deficiencies: no SSS / PhilHealth / Pag-IBIG / TIN number.

Filterable by department and attendance location. Anyone with HRIS ->
Employees (or admin) can view it."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.attendance_location import AttendanceLocation
from app.models.employee_government import EmployeeGovernmentDetails
from app.models.employees import Employee
from app.models.files import File as FileModel
from app.models.user import User
from app.services.approval_chain import load_json_list
from app.services.employee_documents import (
    DOC_LABELS,
    EXPIRING_BY_DEFAULT,
    WARN_DAYS,
    expiry_map,
    required_documents,
)
from app.services.attendance_alerts import now_ph
from app.utils.response import api_response

router = APIRouter(prefix="/hr-dashboard", tags=["HR Dashboard"])

_require_viewer = require_role_or_module(roles=["admin"], module_key="hris.employees")

GOV_FIELDS = {
    "sss": "sss_number",
    "philhealth": "philhealth_number",
    "pagibig": "pagibig_number",
    "tin": "tin_number",
}


def _name(emp: Employee) -> str:
    return " ".join(p for p in [emp.first_name, emp.last_name, emp.suffix] if p)


def _pct(have: int, need: int) -> float:
    return round(have * 100 / need, 1) if need else 100.0


@router.get("")
def hr_dashboard(
    department: str | None = Query(None),
    location_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_viewer),
):
    today = now_ph().date()
    warn_until = today + timedelta(days=WARN_DAYS)

    all_active = (
        db.query(Employee)
        .filter(Employee.is_active == 1)
        .order_by(Employee.last_name, Employee.first_name)
        .all()
    )
    departments = sorted({e.department for e in all_active if e.department})
    locations = [
        {"id": loc.id, "name": loc.name}
        for loc in db.query(AttendanceLocation).order_by(AttendanceLocation.name).all()
    ]

    employees = all_active
    if department:
        employees = [e for e in employees if e.department == department]
    if location_id:
        employees = [
            e
            for e in employees
            if location_id in {int(i) for i in load_json_list(e.attendance_location_ids)}
        ]
    ids = [e.id for e in employees]

    have_docs: dict[int, set[str]] = {}
    if ids:
        for emp_id, doc in (
            db.query(FileModel.entity_id, FileModel.document_type)
            .filter(FileModel.entity_type == "employee", FileModel.entity_id.in_(ids))
            .all()
        ):
            have_docs.setdefault(emp_id, set()).add(doc)
    expiries = expiry_map(db, ids)
    gov_rows = (
        {
            g.employee_id: g
            for g in db.query(EmployeeGovernmentDetails)
            .filter(EmployeeGovernmentDetails.employee_id.in_(ids))
            .all()
        }
        if ids
        else {}
    )

    doc_stats: dict[str, dict] = {}
    dept_stats: dict[str, dict] = {}
    lacking = []
    expiring = []
    no_expiry_date = []
    gov = {key: [] for key in GOV_FIELDS}
    total_need = total_have = complete = 0

    for emp in employees:
        person = {
            "employee_id": emp.id,
            "name": _name(emp),
            "department": emp.department,
            "position": emp.position,
        }
        have = have_docs.get(emp.id, set())

        # ---- Lacking docs
        need = required_documents(emp.department)
        missing = [d for d in need if d not in have]
        got = len(need) - len(missing)
        total_need += len(need)
        total_have += got
        if not missing:
            complete += 1
        for doc in need:
            s = doc_stats.setdefault(doc, {"required": 0, "have": 0})
            s["required"] += 1
            s["have"] += doc in have
        d = dept_stats.setdefault(
            emp.department or "-", {"employees": 0, "complete": 0, "need": 0, "have": 0}
        )
        d["employees"] += 1
        d["complete"] += not missing
        d["need"] += len(need)
        d["have"] += got
        if missing:
            lacking.append(
                {
                    **person,
                    "completion": _pct(got, len(need)),
                    "missing": [DOC_LABELS.get(m, m) for m in missing],
                }
            )

        # ---- Nearing expiry (only documents on file and flagged)
        rows = expiries.get(emp.id, {})
        flagged = {doc for doc in EXPIRING_BY_DEFAULT if doc not in rows}
        flagged |= {doc for doc, row in rows.items() if row.has_expiry}
        for doc in sorted(flagged):
            if doc not in have:
                continue
            row = rows.get(doc)
            if row is None or row.expiry_date is None:
                no_expiry_date.append({**person, "document": DOC_LABELS.get(doc, doc)})
                continue
            if row.expiry_date <= warn_until:
                days_left = (row.expiry_date - today).days
                expiring.append(
                    {
                        **person,
                        "document_type": doc,
                        "document": DOC_LABELS.get(doc, doc),
                        "expiry_date": row.expiry_date.isoformat(),
                        "days_left": days_left,
                        "status": "expired" if days_left < 0 else "expiring",
                    }
                )

        # ---- Government ID deficiencies (numbers on the 201)
        g = gov_rows.get(emp.id)
        for key, column in GOV_FIELDS.items():
            if not (getattr(g, column, None) or "").strip():
                gov[key].append(person)

    expiring.sort(key=lambda x: x["days_left"])
    lacking.sort(key=lambda x: (x["completion"], x["name"]))

    return api_response(
        {
            "today": today.isoformat(),
            "warn_days": WARN_DAYS,
            "filters": {"departments": departments, "locations": locations},
            "employees_count": len(employees),
            "complete_count": complete,
            "completion": _pct(total_have, total_need),
            "documents": sorted(
                (
                    {
                        "document_type": doc,
                        "label": DOC_LABELS.get(doc, doc),
                        "required": s["required"],
                        "have": s["have"],
                        "missing": s["required"] - s["have"],
                        "completion": _pct(s["have"], s["required"]),
                    }
                    for doc, s in doc_stats.items()
                ),
                key=lambda x: x["completion"],
            ),
            "departments": sorted(
                (
                    {
                        "department": name,
                        "employees": s["employees"],
                        "complete": s["complete"],
                        "completion": _pct(s["have"], s["need"]),
                    }
                    for name, s in dept_stats.items()
                ),
                key=lambda x: x["completion"],
            ),
            "lacking": lacking,
            "expiring": expiring,
            "no_expiry_date": no_expiry_date,
            "government": gov,
        }
    )

from datetime import datetime
from app.models.overtime_approval_details import OvertimeApprovalDetail
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.user import User
from app.models.employees import Employee
from app.models.overtime_approvals import OvertimeApproval

router = APIRouter(
    prefix="/overtime-approval",
    tags=["Overtime Approval"],
)

@router.get("/list")
def get_overtime_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = (
        db.query(OvertimeApproval)
        .order_by(
            OvertimeApproval.created_at.desc()
        )
        .all()
    )

    return records


@router.get("/employee/{employee_id}")
def get_employee_overtime(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = (
        db.query(OvertimeApproval)
        .filter(
            OvertimeApproval.employee_id
            == employee_id
        )
        .order_by(
            OvertimeApproval.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": item.id,
            "employee_id": item.employee_id,
            "cutoff_start": item.cutoff_start,
            "cutoff_end": item.cutoff_end,
            "detected_ot_hours": item.detected_ot_hours,
            "approved_ot_hours": item.approved_ot_hours,
            "status": item.status,

            "details": [
                {
                    "attendance_id": d.attendance_id,
                    "detected_ot_hours": d.detected_ot_hours,
                    "approved_ot_hours": d.approved_ot_hours,
                }
                for d in item.details
            ],
        }
        for item in records
    ]

@router.post("/approve")
def approve_overtime(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [
        "admin",
        "superadmin",
    ]:
        raise HTTPException(
            status_code=403,
            detail="Only HR/Admin can approve overtime.",
        )

    employee = (
        db.query(Employee)
        .filter(
            Employee.id == payload["employee_id"]
        )
        .first()
    )

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found.",
        )

    existing = (
        db.query(OvertimeApproval)
        .filter(
            OvertimeApproval.employee_id
            == payload["employee_id"],
            OvertimeApproval.cutoff_start
            == payload["cutoff_start"],
            OvertimeApproval.cutoff_end
            == payload["cutoff_end"],
        )
        .first()
    )

    if existing:
        existing.detected_ot_hours = payload[
            "detected_ot_hours"
        ]

        existing.approved_ot_hours = payload[
            "approved_ot_hours"
        ]

        existing.status = "Approved"

        existing.remarks = payload.get(
            "remarks"
        )

        existing.approved_by_user_id = (
            current_user.id
        )

        existing.approved_at = (
            datetime.utcnow()
        )

        db.query(
            OvertimeApprovalDetail
        ).filter(
            OvertimeApprovalDetail
            .overtime_approval_id
            == existing.id
        ).delete()

        for detail in payload.get(
            "details",
            [],
        ):
            db.add(
                OvertimeApprovalDetail(
                    overtime_approval_id=
                    existing.id,

                    attendance_id=
                    detail[
                        "attendance_id"
                    ],

                    detected_ot_hours=
                    detail[
                        "detected_ot_hours"
                    ],

                    approved_ot_hours=
                    detail[
                        "approved_ot_hours"
                    ],
                )
            )

        db.commit()
        db.refresh(existing)

        return {
            "message": "Overtime updated and approved.",
            "id": existing.id,
        }

    overtime = OvertimeApproval(
        employee_id=payload[
            "employee_id"
        ],
        cutoff_start=payload[
            "cutoff_start"
        ],
        cutoff_end=payload[
            "cutoff_end"
        ],
        detected_ot_hours=payload[
            "detected_ot_hours"
        ],
        approved_ot_hours=payload[
            "approved_ot_hours"
        ],
        status="Approved",
        remarks=payload.get(
            "remarks"
        ),
        approved_by_user_id=current_user.id,
        approved_at=datetime.utcnow(),
    )

    db.add(overtime)

    db.flush()

    for detail in payload.get(
        "details",
        [],
    ):
        db.add(
            OvertimeApprovalDetail(
                overtime_approval_id=
                overtime.id,

                attendance_id=
                detail[
                    "attendance_id"
                ],

                detected_ot_hours=
                detail[
                    "detected_ot_hours"
                ],

                approved_ot_hours=
                detail[
                    "approved_ot_hours"
                ],
            )
        )

    db.commit()
    db.refresh(overtime)

    return {
        "message":
        "Overtime approved successfully.",
        "id": overtime.id,
    }


@router.post("/reverse")
def reverse_overtime(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in [
        "admin",
        "superadmin",
    ]:
        raise HTTPException(
            status_code=403,
            detail="Only HR/Admin can reverse overtime.",
        )

    overtime = (
        db.query(OvertimeApproval)
        .filter(
            OvertimeApproval.employee_id
            == payload["employee_id"],
            OvertimeApproval.cutoff_start
            == payload["cutoff_start"],
            OvertimeApproval.cutoff_end
            == payload["cutoff_end"],
        )
        .first()
    )

    if not overtime:
        raise HTTPException(
            status_code=404,
            detail="Overtime approval not found.",
        )

    overtime.status = "Reversed"

    overtime.approved_ot_hours = 0

    overtime.reversed_by_user_id = (
        current_user.id
    )

    overtime.reversed_at = (
        datetime.utcnow()
    )

    db.query(
        OvertimeApprovalDetail
    ).filter(
        OvertimeApprovalDetail
        .overtime_approval_id
        == overtime.id
    ).delete()

    db.commit()
    db.refresh(overtime)

    return {
        "message": "Overtime approval reversed.",
        "id": overtime.id,
    }
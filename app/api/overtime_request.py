from datetime import datetime, date, time as time_cls, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_admin
from app.models.user import User
from app.models.overtime_approver import OvertimeApprover
from app.models.overtime_request import OvertimeRequest
from app.schemas.overtime_request import OvertimeRequestCreate

router = APIRouter(prefix="/overtime-requests", tags=["Overtime Requests"])


def _compute_hours(ot_date: date, time_in: time_cls, time_out: time_cls) -> float:
    """Hours between time_in and time_out on ot_date. If time_out is not
    after time_in (e.g. 8pm-12:30am), the shift is treated as crossing
    into the next day."""
    start = datetime.combine(ot_date, time_in)
    end = datetime.combine(ot_date, time_out)
    if end <= start:
        end += timedelta(days=1)
    return round((end - start).total_seconds() / 3600, 2)


def _serialize(req: OvertimeRequest) -> dict:
    employee = req.employee
    requester = req.requester
    approver = req.requested_by
    return {
        "id": req.id,
        "employee_id": req.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee
            else (requester.username if requester else None)
        ),
        "ot_date": str(req.ot_date),
        "time_in": req.time_in.strftime("%H:%M"),
        "time_out": req.time_out.strftime("%H:%M"),
        "computed_hours": req.computed_hours,
        "reason": req.reason,
        "status": req.status,
        "approved_hours": req.approved_hours,
        "remarks": req.remarks,
        "requested_by_user_id": req.requested_by_user_id,
        "requested_by_name": approver.username if approver else None,
        "approved_by_user_id": req.approved_by_user_id,
        "approved_at": req.approved_at,
        "created_at": req.created_at,
    }


@router.get("/approvers")
def list_approvers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    approvers = (
        db.query(OvertimeApprover)
        .options(joinedload(OvertimeApprover.user))
        .filter(OvertimeApprover.is_active == True)  # noqa: E712
        .all()
    )
    return [
        {"id": a.id, "user_id": a.user_id, "username": a.user.username}
        for a in approvers
        if a.user
    ]


@router.post("/approvers")
def add_approver(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    user_id = payload.get("user_id")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    existing = (
        db.query(OvertimeApprover).filter(OvertimeApprover.user_id == user_id).first()
    )
    if existing:
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return {"id": existing.id, "user_id": existing.user_id, "username": target.username}

    approver = OvertimeApprover(
        user_id=user_id,
        added_by_user_id=current_user.id,
        is_active=True,
    )
    db.add(approver)
    db.commit()
    db.refresh(approver)
    return {"id": approver.id, "user_id": approver.user_id, "username": target.username}


@router.post("/")
def file_overtime_request(
    payload: OvertimeRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Superadmin accounts cannot file overtime requests.",
        )

    approver_entry = (
        db.query(OvertimeApprover)
        .filter(
            OvertimeApprover.user_id == payload.requested_by_user_id,
            OvertimeApprover.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not approver_entry:
        raise HTTPException(
            status_code=400,
            detail="Selected approver is not a valid overtime approver.",
        )

    hours = _compute_hours(payload.ot_date, payload.time_in, payload.time_out)

    request = OvertimeRequest(
        user_id=current_user.id,
        employee_id=current_user.employee_id,
        requested_by_user_id=payload.requested_by_user_id,
        ot_date=payload.ot_date,
        time_in=payload.time_in,
        time_out=payload.time_out,
        computed_hours=hours,
        reason=payload.reason,
        status="pending",
    )

    db.add(request)
    db.commit()
    db.refresh(request)

    return _serialize(request)


@router.get("/mine")
def get_my_overtime_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requests = (
        db.query(OvertimeRequest)
        .options(joinedload(OvertimeRequest.employee), joinedload(OvertimeRequest.requested_by))
        .filter(OvertimeRequest.user_id == current_user.id)
        .order_by(OvertimeRequest.created_at.desc())
        .all()
    )
    return [_serialize(r) for r in requests]


@router.post("/{request_id}/cancel")
def cancel_overtime_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = (
        db.query(OvertimeRequest).filter(OvertimeRequest.id == request_id).first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Overtime request not found")
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own requests")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be cancelled")

    request.status = "cancelled"
    db.commit()
    db.refresh(request)
    return _serialize(request)

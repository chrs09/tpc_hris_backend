from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload, object_session

from app.core.database import get_db
from app.core.dependencies import (
    get_current_admin,
    get_current_user,
    has_editable_grant,
    require_role_or_module,
)
from app.models.user import User
from app.models.leave_request import LeaveRequest
from app.models.attendance import AttendanceRecord
from app.models.employees import Employee
from app.services.approval_chain import (
    acting_index,
    append_log,
    describe_chain,
    dump_chain,
    load_json_list,
    log_skipped,
    resolve_chain,
    skipped_for,
    team_scope,
)
from app.schemas.leave import LeaveRequestCreate, LeaveReviewAction

router = APIRouter(prefix="/leave", tags=["Leave"])


def _apply_on_leave_attendance(leave: LeaveRequest, db: Session, approved_by_user_id: int):
    """Marks attendance as "On Leave" for every date in an approved leave
    request's range.

    Required by: approve_leave_request() below -- this is what makes an
    approved leave actually show up on the attendance list, instead of
    leave requests and attendance being two disconnected records of the
    same absence.

    Only fills in dates that don't already have an attendance record
    (e.g. the employee clocked in that day, or an admin already marked
    it some other way) -- an existing record is left untouched rather
    than overwritten, so this can never erase real attendance data.
    Does nothing if the leave isn't linked to an employee record (e.g.
    an admin account with no HR employee profile), since attendance is
    tracked per employee.
    """
    if not leave.employee_id:
        return

    current_date = leave.start_date
    while current_date <= leave.end_date:
        existing = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.employee_id == leave.employee_id,
                AttendanceRecord.attendance_date == current_date,
            )
            .first()
        )

        if not existing:
            db.add(
                AttendanceRecord(
                    employee_id=leave.employee_id,
                    attendance_date=current_date,
                    status="On Leave",
                    remarks=leave.reason,
                    created_by_user_id=approved_by_user_id,
                )
            )

        current_date += timedelta(days=1)


def _requester_role(leave: LeaveRequest) -> str | None:
    requester = leave.requester
    if not requester:
        return None
    role = requester.role
    return role.value if hasattr(role, "value") else role


def _ensure_can_review(leave: LeaveRequest, current_user: User):
    """Admin-filed leave can only be approved/rejected by a superadmin --
    an admin cannot review another admin's leave request."""
    if _requester_role(leave) == "admin" and current_user.role != "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Only a superadmin can review an admin's leave request.",
        )


def _has_leave_module(db: Session, user: User) -> bool:
    """HR / admin side (the Leave module): admin, superadmin, or the
    hris.leave grant with "Can edit: Yes"."""
    role = user.role.value if hasattr(user.role, "value") else user.role
    return role in ("admin", "superadmin") or has_editable_grant(db, user, ["hris.leave"])


def _chain(leave: LeaveRequest) -> list[int]:
    return [int(i) for i in load_json_list(leave.approval_chain)]


def _serialize(leave: LeaveRequest) -> dict:
    employee = leave.employee
    requester = leave.requester
    return {
        "id": leave.id,
        "employee_id": leave.employee_id,
        "employee_name": (
            f"{employee.first_name} {employee.last_name}"
            if employee
            else (requester.username if requester else None)
        ),
        "employee_role": _requester_role(leave),
        "position": employee.position if employee else None,
        "leave_type": leave.leave_type,
        "start_date": str(leave.start_date),
        "end_date": str(leave.end_date),
        "reason": leave.reason,
        "status": leave.status,
        "review_remarks": leave.review_remarks,
        "reviewed_by_user_id": leave.reviewed_by_user_id,
        "reviewed_at": leave.reviewed_at,
        "created_at": leave.created_at,
        # False when the viewer's step was passed up (they're away today).
        "can_act": getattr(leave, "_can_act", True),
        "viewer_away": getattr(leave, "_away", None),
        # Org chart approval progress (empty when routed the old way).
        **(
            describe_chain(
                object_session(leave),
                leave.approval_chain,
                leave.approval_step,
                leave.approval_log,
                leave.status != "pending",
            )
            if object_session(leave) is not None
            else {}
        ),
    }


@router.post("/request")
def file_leave_request(
    payload: LeaveRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Everyone can file leave except superadmin -- there's no one above a
    # superadmin to approve/reject it, so it wouldn't have a workflow.
    if current_user.role == "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Superadmin accounts cannot file leave requests.",
        )

    if payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before the start date.",
        )

    overlapping = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.user_id == current_user.id,
            LeaveRequest.status.in_(["pending", "approved"]),
            LeaveRequest.start_date <= payload.end_date,
            LeaveRequest.end_date >= payload.start_date,
        )
        .first()
    )

    if overlapping:
        raise HTTPException(
            status_code=400,
            detail="You already have a pending or approved leave request that overlaps these dates.",
        )

    # Org chart first: every head up the layers with Leave ticked, in
    # order. Nobody set up there -> HR / admin approve as before.
    employee = (
        db.query(Employee).filter(Employee.id == current_user.employee_id).first()
        if current_user.employee_id
        else None
    )
    chain = resolve_chain(db, employee, current_user, "leave")

    leave = LeaveRequest(
        user_id=current_user.id,
        employee_id=current_user.employee_id,
        leave_type="unpaid",
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        status="pending",
        approval_chain=dump_chain(chain),
        approval_step=0,
    )

    db.add(leave)
    db.commit()
    db.refresh(leave)

    return _serialize(leave)


@router.get("/my-requests")
def get_my_leave_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    leaves = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.employee))
        .filter(LeaveRequest.user_id == current_user.id)
        .order_by(LeaveRequest.created_at.desc())
        .all()
    )

    return [_serialize(leave) for leave in leaves]


@router.post("/{leave_id}/cancel")
def cancel_leave_request(
    leave_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found.")

    if leave.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only cancel your own leave requests.",
        )

    if leave.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending leave requests can be cancelled.",
        )

    leave.status = "cancelled"
    db.commit()
    db.refresh(leave)

    return _serialize(leave)


@router.get("/for-my-approval")
def list_leave_for_my_approval(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pending leave whose turn is with me on the Org Chart chain (or
    passed up past me because I'm away today -- shown read-only)."""
    pending = (
        db.query(LeaveRequest)
        .options(joinedload(LeaveRequest.employee), joinedload(LeaveRequest.requester))
        .filter(LeaveRequest.status == "pending", LeaveRequest.approval_chain.isnot(None))
        .order_by(LeaveRequest.created_at.asc())
        .all()
    )
    team = team_scope(db, current_user)
    mine = []
    for leave in pending:
        if team is not None and leave.employee_id not in team["employee_ids"]:
            continue
        chain = _chain(leave)
        if acting_index(db, chain, leave.approval_step, current_user.id)[0] is not None:
            leave._can_act = True
            mine.append(leave)
        else:
            away = skipped_for(db, chain, leave.approval_step, current_user.id)
            if away:
                leave._can_act = False
                leave._away = away
                mine.append(leave)
    return [_serialize(leave) for leave in mine]


@router.get("/list")
def list_leave_requests(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role_or_module(roles=["admin", "superadmin"], module_key="hris.leave")),
):
    query = db.query(LeaveRequest).options(
        joinedload(LeaveRequest.employee),
        joinedload(LeaveRequest.requester),
    )

    if status:
        query = query.filter(LeaveRequest.status == status)

    leaves = query.order_by(LeaveRequest.created_at.desc()).all()

    return [_serialize(leave) for leave in leaves]


def _reviewer_step(db: Session, leave: LeaveRequest, current_user: User):
    """(acting chain step or None, skipped approvers). A head whose turn it
    is acts on their step; otherwise the HR / admin side (Leave module)
    can approve or reject at any point, as before."""
    chain = _chain(leave)
    acting, skipped = (
        acting_index(db, chain, leave.approval_step, current_user.id) if chain else (None, [])
    )
    if acting is None:
        if not _has_leave_module(db, current_user):
            raise HTTPException(
                status_code=403, detail="You can't review this leave request."
            )
        _ensure_can_review(leave, current_user)
    return chain, acting, skipped


@router.post("/{leave_id}/approve")
def approve_leave_request(
    leave_id: int,
    payload: LeaveReviewAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found.")

    if leave.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending leave requests can be approved.",
        )

    chain, acting, skipped = _reviewer_step(db, leave, current_user)
    leave.approval_log = log_skipped(db, leave.approval_log, chain, skipped)
    leave.approval_log = append_log(leave.approval_log, current_user, "approved", payload.remarks)

    # Org chart chain: pass it to the next head up; the last one (or the
    # HR / admin side) gives the final approval.
    if chain and acting is not None and acting < len(chain) - 1:
        leave.approval_step = acting + 1
        db.commit()
        db.refresh(leave)
        return _serialize(leave)
    if chain and acting is not None:
        leave.approval_step = acting

    leave.status = "approved"
    leave.review_remarks = payload.remarks
    leave.reviewed_by_user_id = current_user.id
    leave.reviewed_at = datetime.utcnow()

    _apply_on_leave_attendance(leave, db, current_user.id)

    db.commit()
    db.refresh(leave)

    return _serialize(leave)


@router.post("/{leave_id}/reject")
def reject_leave_request(
    leave_id: int,
    payload: LeaveReviewAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    leave = db.query(LeaveRequest).filter(LeaveRequest.id == leave_id).first()

    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found.")

    if leave.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending leave requests can be rejected.",
        )

    chain, acting, skipped = _reviewer_step(db, leave, current_user)
    leave.approval_log = log_skipped(db, leave.approval_log, chain, skipped)
    leave.approval_log = append_log(leave.approval_log, current_user, "rejected", payload.remarks)

    leave.status = "rejected"
    leave.review_remarks = payload.remarks
    leave.reviewed_by_user_id = current_user.id
    leave.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(leave)

    return _serialize(leave)

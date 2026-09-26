# app/api/tickets.py
#
# A lightweight Kanban-style ticket board for superadmin to log change
# requests/instructions in one place, with a status any admin viewing
# the board can move as work progresses. Superadmin-only (create/edit/
# move/delete) -- this is a superadmin-to-developer channel, not a
# general employee helpdesk.

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.employees import Employee
from app.models.user import User
from app.models.ticket import Ticket
from app.models.ticket_comment import TicketComment
from app.services.file_service import FileService
from app.utils.user_display import display_name as _display_name

ALLOWED_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

router = APIRouter(prefix="/tickets", tags=["Tickets"])

_require_tickets_access = require_role_or_module(
    roles=[], module_key="administrator.tickets"
)

VALID_STATUSES = {"todo", "in_progress", "review", "done"}
VALID_PRIORITIES = {"low", "medium", "high"}


class TicketCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str | None = None


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    # 0 means "explicitly unassign" (a valid, non-None value Pydantic
    # accepts), vs. omitting the field/leaving it None, which means
    # "don't touch this" -- matters because a drag-and-drop status move
    # only sends {"status": ...} and must never silently wipe the
    # assignee.
    assigned_to_user_id: int | None = None


# Tickets are handled by IT: active users whose linked employee has the
# position "IT".
def _it_users(db: Session) -> list[User]:
    return (
        db.query(User)
        .join(Employee, Employee.id == User.employee_id)
        .options(joinedload(User.employee))
        .filter(
            Employee.position.isnot(None),
            Employee.position.ilike("it"),
            User.is_active.is_(True),
        )
        .order_by(User.id.asc())
        .all()
    )


def _pick_it_assignee(db: Session) -> User | None:
    """The IT employee with the fewest open tickets (ties: lowest id)."""
    it_users = _it_users(db)
    if not it_users:
        return None
    open_counts = {u.id: 0 for u in it_users}
    for (assignee_id,) in db.query(Ticket.assigned_to_user_id).filter(
        Ticket.assigned_to_user_id.in_(list(open_counts)),
        Ticket.status != "done",
    ):
        open_counts[assignee_id] += 1
    return min(it_users, key=lambda u: (open_counts[u.id], u.id))


def _require_it_assignee(db: Session, user_id: int) -> None:
    if user_id not in {u.id for u in _it_users(db)}:
        raise HTTPException(
            status_code=400, detail="Tickets can only be assigned to IT."
        )


def _next_ticket_no(db: Session, when: datetime) -> str:
    """"TKT-YYYY-NNNN", sequential per year. The unique index on
    ticket_no is the safety net against a rare concurrent collision."""
    prefix = f"TKT-{when.year}-"
    last = (
        db.query(Ticket.ticket_no)
        .filter(Ticket.ticket_no.like(f"{prefix}%"))
        .order_by(Ticket.ticket_no.desc())
        .first()
    )
    number = 1
    if last and last[0]:
        try:
            number = int(last[0].rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            pass
    return f"{prefix}{number:04d}"


def _serialize(ticket: Ticket, comment_count: int = 0) -> dict:
    return {
        "comment_count": comment_count,
        "id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "created_by_user_id": ticket.created_by_user_id,
        "created_by_username": _display_name(ticket.created_by),
        "assigned_to_user_id": ticket.assigned_to_user_id,
        "assigned_to_username": _display_name(ticket.assigned_to),
        "image_url": ticket.image_url,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


@router.get("")
def list_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    tickets = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.created_by).joinedload(User.employee),
            joinedload(Ticket.assigned_to).joinedload(User.employee),
        )
        .order_by(Ticket.created_at.desc())
        .all()
    )
    counts = dict(
        db.query(TicketComment.ticket_id, func.count(TicketComment.id))
        .group_by(TicketComment.ticket_id)
        .all()
    )
    return [_serialize(t, counts.get(t.id, 0)) for t in tickets]


@router.get("/assignees")
def list_ticket_assignees(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    """Who a ticket can be assigned to: the IT employees."""
    return [
        {
            "id": u.id,
            "username": u.username,
            "employee_name": _display_name(u),
        }
        for u in _it_users(db)
    ]


@router.post("")
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")

    if payload.priority and payload.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority.")

    # Always handled by IT, never assigned to the creator.
    assignee = _pick_it_assignee(db)
    now = datetime.utcnow()

    ticket = Ticket(
        ticket_no=_next_ticket_no(db, now),
        title=title,
        description=(payload.description or "").strip() or None,
        priority=payload.priority,
        status="todo",
        created_by_user_id=current_user.id,
        assigned_to_user_id=assignee.id if assignee else None,
        created_at=now,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return _serialize(ticket)


@router.patch("/{ticket_id}")
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title is required.")
        ticket.title = title

    if payload.description is not None:
        ticket.description = payload.description.strip() or None

    if payload.status is not None:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status.")
        ticket.status = payload.status

    if payload.priority is not None:
        if payload.priority and payload.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority.")
        ticket.priority = payload.priority or None

    # Reassigning is only between IT employees (no unassigning).
    if payload.assigned_to_user_id:
        _require_it_assignee(db, payload.assigned_to_user_id)
        ticket.assigned_to_user_id = payload.assigned_to_user_id

    ticket.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(ticket)

    return _serialize(ticket)


@router.delete("/{ticket_id}")
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    db.query(TicketComment).filter(TicketComment.ticket_id == ticket.id).delete(
        synchronize_session=False
    )
    db.delete(ticket)
    db.commit()

    return {"message": "Ticket deleted."}


# =========================
# COMMENTS / REMARKS
# =========================
class TicketCommentCreate(BaseModel):
    body: str


def _serialize_comment(
    comment: TicketComment, current_user_id: int, creator_id: int
) -> dict:
    return {
        "id": comment.id,
        "body": comment.body,
        "user_id": comment.user_id,
        "user_name": _display_name(comment.user),
        # Marks the ticket creator's comments ("Creator" tag in the UI).
        "is_creator": comment.user_id == creator_id,
        "is_mine": comment.user_id == current_user_id,
        "created_at": comment.created_at,
    }


def _get_ticket(db: Session, ticket_id: int) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


@router.get("/{ticket_id}/comments")
def list_ticket_comments(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    """Oldest first, like a conversation."""
    ticket = _get_ticket(db, ticket_id)
    comments = (
        db.query(TicketComment)
        .options(joinedload(TicketComment.user).joinedload(User.employee))
        .filter(TicketComment.ticket_id == ticket.id)
        .order_by(TicketComment.created_at.asc(), TicketComment.id.asc())
        .all()
    )
    return [
        _serialize_comment(c, current_user.id, ticket.created_by_user_id)
        for c in comments
    ]


@router.post("/{ticket_id}/comments")
def add_ticket_comment(
    ticket_id: int,
    payload: TicketCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    ticket = _get_ticket(db, ticket_id)
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Comment can't be empty.")
    if len(body) > 5000:
        raise HTTPException(
            status_code=400, detail="Comment is too long (5,000 characters max)."
        )

    comment = TicketComment(ticket_id=ticket.id, user_id=current_user.id, body=body)
    db.add(comment)
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(comment)
    return _serialize_comment(comment, current_user.id, ticket.created_by_user_id)


@router.delete("/{ticket_id}/comments/{comment_id}")
def delete_ticket_comment(
    ticket_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    """Only the person who wrote a comment can delete it."""
    comment = (
        db.query(TicketComment)
        .filter(TicketComment.id == comment_id, TicketComment.ticket_id == ticket_id)
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found.")
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only delete your own comments."
        )
    db.delete(comment)
    db.commit()
    return {"message": "Comment deleted."}


@router.post("/{ticket_id}/image")
def upload_ticket_image(
    ticket_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    if image.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only PNG, JPEG, WEBP, or GIF images are allowed.",
        )

    ticket.image_url = FileService().upload_ticket_image(image, ticket.id)
    ticket.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(ticket)

    return _serialize(ticket)


@router.delete("/{ticket_id}/image")
def remove_ticket_image(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_tickets_access),
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")

    ticket.image_url = None
    ticket.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(ticket)

    return _serialize(ticket)

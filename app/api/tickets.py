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
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import require_role_or_module
from app.models.user import User
from app.models.ticket import Ticket
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
    assigned_to_user_id: int | None = None


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


def _require_valid_assignee(db: Session, user_id: int) -> None:
    assignee = db.query(User).filter(User.id == user_id).first()
    if not assignee:
        raise HTTPException(status_code=400, detail="Assignee not found.")


def _serialize(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
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
    return [_serialize(t) for t in tickets]


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

    if payload.assigned_to_user_id:
        _require_valid_assignee(db, payload.assigned_to_user_id)

    ticket = Ticket(
        title=title,
        description=(payload.description or "").strip() or None,
        priority=payload.priority,
        status="todo",
        created_by_user_id=current_user.id,
        assigned_to_user_id=payload.assigned_to_user_id or None,
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

    if payload.assigned_to_user_id is not None:
        if payload.assigned_to_user_id:
            _require_valid_assignee(db, payload.assigned_to_user_id)
        ticket.assigned_to_user_id = payload.assigned_to_user_id or None

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

    db.delete(ticket)
    db.commit()

    return {"message": "Ticket deleted."}


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

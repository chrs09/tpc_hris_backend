# app/api/tickets.py
#
# Helpdesk tickets. Anyone signed in can file one; each ticket has a
# category, and the category's Org Chart unit handles it -- the creator
# may pick any active user instead. Handlers can forward a ticket to
# another category or person with a note; every assign / forward /
# status change goes into the ticket's timeline. Public tickets come in
# through app/api/public/support.py.
#
# Who sees what: superadmin or anyone given Administrator -> Tickets
# (with edit) sees every ticket and manages categories; everyone else
# sees tickets they created, are assigned, or that belong to their
# Org Chart units.

import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import get_current_user, has_editable_grant
from app.models.employees import Employee
from app.models.org_unit import OrgUnit
from app.models.ticket import Ticket
from app.models.ticket_category import TicketCategory
from app.models.ticket_comment import TicketComment
from app.models.user import User
from app.services.approval_chain import _is_member
from app.services.email_service import send_email
from app.services.file_service import FileService
from app.utils.user_display import display_name as _display_name

ALLOWED_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

router = APIRouter(prefix="/tickets", tags=["Tickets"])

VALID_STATUSES = {"todo", "in_progress", "review", "done"}
STATUS_LABELS = {"todo": "To Do", "in_progress": "In Progress", "review": "Review", "done": "Done"}
VALID_PRIORITIES = {"low", "medium", "high"}


# =========================
# WHO HANDLES / WHO SEES
# =========================
def sees_all_tickets(db: Session, user: User) -> bool:
    return has_editable_grant(db, user, ["administrator.tickets"])


def unit_user_ids(db: Session, unit: OrgUnit | None) -> list[int]:
    """Active users in an Org Chart unit (its head first)."""
    if unit is None:
        return []
    ids = [unit.head_user_id] if unit.head_user_id else []
    users = (
        db.query(User)
        .options(joinedload(User.employee))
        .filter(User.is_active.is_(True))
        .all()
    )
    for user in users:
        employee = user.employee
        if employee is not None and employee.is_active != 1:
            continue
        if user.id not in ids and _is_member(unit, employee, user):
            ids.append(user.id)
    return ids


def my_unit_ids(db: Session, user: User) -> set[int]:
    """Units the user belongs to or heads (plus everything below a unit
    they head) -- their tickets queue."""
    units = db.query(OrgUnit).all()
    children: dict = {}
    for unit in units:
        children.setdefault(unit.parent_id, []).append(unit)
    employee = (
        db.query(Employee).filter(Employee.id == user.employee_id).first()
        if user.employee_id
        else None
    )
    mine = {u.id for u in units if _is_member(u, employee, user)}
    stack = [u for u in units if u.head_user_id == user.id]
    while stack:
        unit = stack.pop()
        if unit.id in mine and unit.head_user_id != user.id:
            continue
        mine.add(unit.id)
        stack.extend(children.get(unit.id, []))
    return mine


def pick_assignee(db: Session, category: TicketCategory | None) -> int | None:
    """The least-busy person (fewest open tickets) in the category's
    Org Chart unit; ties go to the head, then the lowest id."""
    candidates = unit_user_ids(db, category.org_unit if category else None)
    if not candidates:
        return None
    open_counts = {uid: 0 for uid in candidates}
    for (uid,) in db.query(Ticket.assigned_to_user_id).filter(
        Ticket.assigned_to_user_id.in_(candidates), Ticket.status != "done"
    ):
        open_counts[uid] += 1
    return min(candidates, key=lambda uid: (open_counts[uid], candidates.index(uid)))


def can_view(db: Session, user: User, ticket: Ticket) -> bool:
    if sees_all_tickets(db, user):
        return True
    if user.id in (ticket.created_by_user_id, ticket.assigned_to_user_id):
        return True
    category = ticket.category
    return bool(category and category.org_unit_id in my_unit_ids(db, user))


def _active_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=400, detail="That person can't be assigned.")
    return user


def _category(db: Session, category_id: int | None) -> TicketCategory | None:
    if not category_id:
        return None
    category = (
        db.query(TicketCategory)
        .filter(TicketCategory.id == category_id, TicketCategory.is_active.is_(True))
        .first()
    )
    if not category:
        raise HTTPException(status_code=400, detail="Pick a valid category.")
    return category


def add_history(ticket: Ticket, action: str, by: str | None, **extra):
    entries = json.loads(ticket.history or "[]")
    entries.append(
        {
            "action": action,
            "by": by or "Customer",
            "at": datetime.utcnow().isoformat(),
            **{k: v for k, v in extra.items() if v not in (None, "")},
        }
    )
    ticket.history = json.dumps(entries)


def _name(db: Session, user_id: int | None) -> str | None:
    if not user_id:
        return None
    return _display_name(db.query(User).filter(User.id == user_id).first())


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
    category = ticket.category
    return {
        "comment_count": comment_count,
        "id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "category_id": ticket.category_id,
        "category_name": category.name if category else None,
        "team_name": category.org_unit.name if category and category.org_unit else None,
        "source": ticket.source or "internal",
        "requester": (
            {
                "name": ticket.requester_name,
                "phone": ticket.requester_phone,
                "email": ticket.requester_email,
                "company": ticket.requester_company,
            }
            if ticket.source == "public"
            else None
        ),
        "created_by_user_id": ticket.created_by_user_id,
        "created_by_username": (
            _display_name(ticket.created_by)
            if ticket.created_by
            else ticket.requester_name
        ),
        "assigned_to_user_id": ticket.assigned_to_user_id,
        "assigned_to_username": _display_name(ticket.assigned_to),
        "image_url": ticket.image_url,
        "history": json.loads(ticket.history or "[]"),
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def _get_visible(db: Session, user: User, ticket_id: int) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket or not can_view(db, user, ticket):
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def email_requester(ticket: Ticket, subject: str, message: str):
    """Best effort -- a public requester with an email gets updates."""
    if ticket.source != "public" or not ticket.requester_email:
        return
    send_email(
        ticket.requester_email,
        f"[{ticket.ticket_no}] {subject}",
        (
            f"<p>Hi {ticket.requester_name or 'there'},</p>"
            f"<p>{message}</p>"
            f"<p>Ticket: <b>{ticket.ticket_no}</b> &middot; {ticket.title}<br>"
            f"Status: <b>{STATUS_LABELS.get(ticket.status, ticket.status)}</b></p>"
            "<p>You can check your ticket anytime on our support page with "
            "your ticket number and phone or email.</p>"
            "<p>Tytan Prime Corporation</p>"
        ),
    )


# =========================
# CATEGORIES
# =========================
def _serialize_category(c: TicketCategory) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "org_unit_id": c.org_unit_id,
        "team_name": c.org_unit.name if c.org_unit else None,
        "is_public": c.is_public,
        "is_active": c.is_active,
        "sort_order": c.sort_order,
    }


@router.get("/categories")
def list_categories(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(TicketCategory).options(joinedload(TicketCategory.org_unit))
    if not include_inactive:
        query = query.filter(TicketCategory.is_active.is_(True))
    return {
        "categories": [
            _serialize_category(c)
            for c in query.order_by(TicketCategory.sort_order, TicketCategory.name)
        ],
        "teams": [
            {"id": u.id, "name": u.name}
            for u in db.query(OrgUnit).order_by(OrgUnit.name)
        ],
        "can_manage": sees_all_tickets(db, current_user),
    }


class CategoryIn(BaseModel):
    name: str
    description: str | None = None
    org_unit_id: int | None = None
    is_public: bool = False
    is_active: bool = True
    sort_order: int = 0


def _require_manager(db: Session, user: User):
    if not sees_all_tickets(db, user):
        raise HTTPException(
            status_code=403,
            detail="Only superadmin or people given Administrator → Tickets can manage categories.",
        )


def _apply_category(db: Session, category: TicketCategory, payload: CategoryIn):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    clash = (
        db.query(TicketCategory)
        .filter(TicketCategory.name == name, TicketCategory.id != (category.id or 0))
        .first()
    )
    if clash:
        raise HTTPException(status_code=400, detail="A category with that name already exists.")
    category.name = name
    category.description = (payload.description or "").strip() or None
    category.org_unit_id = payload.org_unit_id or None
    category.is_public = payload.is_public
    category.is_active = payload.is_active
    category.sort_order = payload.sort_order


@router.post("/categories")
def create_category(
    payload: CategoryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manager(db, current_user)
    category = TicketCategory()
    _apply_category(db, category, payload)
    db.add(category)
    db.commit()
    db.refresh(category)
    return _serialize_category(category)


@router.put("/categories/{category_id}")
def update_category(
    category_id: int,
    payload: CategoryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manager(db, current_user)
    category = db.query(TicketCategory).filter(TicketCategory.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")
    _apply_category(db, category, payload)
    db.commit()
    db.refresh(category)
    return _serialize_category(category)


# =========================
# TICKETS
# =========================
@router.get("")
def list_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Ticket).options(
        joinedload(Ticket.created_by).joinedload(User.employee),
        joinedload(Ticket.assigned_to).joinedload(User.employee),
        joinedload(Ticket.category).joinedload(TicketCategory.org_unit),
    )
    if not sees_all_tickets(db, current_user):
        unit_ids = my_unit_ids(db, current_user)
        category_ids = [
            cid for (cid,) in db.query(TicketCategory.id).filter(
                TicketCategory.org_unit_id.in_(unit_ids or [0])
            )
        ]
        query = query.filter(
            or_(
                Ticket.created_by_user_id == current_user.id,
                Ticket.assigned_to_user_id == current_user.id,
                Ticket.category_id.in_(category_ids or [0]),
            )
        )
    tickets = query.order_by(Ticket.created_at.desc()).all()
    counts = dict(
        db.query(TicketComment.ticket_id, func.count(TicketComment.id))
        .group_by(TicketComment.ticket_id)
        .all()
    )
    return {
        "tickets": [_serialize(t, counts.get(t.id, 0)) for t in tickets],
        "sees_all": sees_all_tickets(db, current_user),
    }


@router.get("/assignees")
def list_ticket_assignees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Anyone active can be assigned a ticket."""
    users = (
        db.query(User)
        .outerjoin(Employee, Employee.id == User.employee_id)
        .options(joinedload(User.employee))
        .filter(User.is_active.is_(True), or_(Employee.id.is_(None), Employee.is_active == 1))
        .all()
    )
    rows = [
        {"id": u.id, "username": u.username, "employee_name": _display_name(u)}
        for u in users
    ]
    return sorted(rows, key=lambda r: (r["employee_name"] or r["username"]).lower())


class TicketCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str | None = None
    category_id: int | None = None
    # Optional: anyone active; empty = the category's team picks.
    assigned_to_user_id: int | None = None


@router.post("")
def create_ticket(
    payload: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")
    if payload.priority and payload.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority.")
    if not payload.category_id:
        raise HTTPException(status_code=400, detail="Pick a category.")
    category = _category(db, payload.category_id)

    if payload.assigned_to_user_id:
        assignee_id = _active_user(db, payload.assigned_to_user_id).id
    else:
        assignee_id = pick_assignee(db, category)

    now = datetime.utcnow()
    ticket = Ticket(
        ticket_no=_next_ticket_no(db, now),
        title=title,
        description=(payload.description or "").strip() or None,
        priority=payload.priority,
        status="todo",
        category_id=category.id,
        source="internal",
        created_by_user_id=current_user.id,
        assigned_to_user_id=assignee_id,
        created_at=now,
    )
    add_history(
        ticket,
        "created",
        _name(db, current_user.id),
        category=category.name,
        assigned_to=_name(db, assignee_id),
        note=None if payload.assigned_to_user_id else "Assigned automatically by category",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return _serialize(ticket)


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    category_id: int | None = None
    # Any active user. Omitted / None = don't touch (a drag-and-drop
    # status move only sends {"status": ...}).
    assigned_to_user_id: int | None = None


@router.patch("/{ticket_id}")
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _get_visible(db, current_user, ticket_id)
    me = _name(db, current_user.id)

    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title is required.")
        ticket.title = title

    if payload.description is not None:
        ticket.description = payload.description.strip() or None

    status_changed = False
    if payload.status is not None and payload.status != ticket.status:
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status.")
        add_history(
            ticket, "status", me,
            frm=STATUS_LABELS.get(ticket.status), to=STATUS_LABELS.get(payload.status),
        )
        ticket.status = payload.status
        status_changed = True

    if payload.priority is not None:
        if payload.priority and payload.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail="Invalid priority.")
        ticket.priority = payload.priority or None

    if payload.category_id and payload.category_id != ticket.category_id:
        category = _category(db, payload.category_id)
        add_history(ticket, "category", me, to=category.name)
        ticket.category_id = category.id

    if payload.assigned_to_user_id and payload.assigned_to_user_id != ticket.assigned_to_user_id:
        assignee = _active_user(db, payload.assigned_to_user_id)
        add_history(ticket, "assigned", me, assigned_to=_display_name(assignee))
        ticket.assigned_to_user_id = assignee.id

    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)

    if status_changed and ticket.status == "done":
        email_requester(ticket, "Your ticket is resolved", "We've marked your ticket as resolved.")
    return _serialize(ticket)


class TicketForward(BaseModel):
    category_id: int | None = None
    assigned_to_user_id: int | None = None
    note: str


@router.post("/{ticket_id}/forward")
def forward_ticket(
    ticket_id: int,
    payload: TicketForward,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hand a ticket to another team (category) and/or person, e.g. a
    trip manager sends a system bug to Technical / IT."""
    ticket = _get_visible(db, current_user, ticket_id)
    note = (payload.note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="Say why you're forwarding it.")
    if not payload.category_id and not payload.assigned_to_user_id:
        raise HTTPException(status_code=400, detail="Pick a category or a person.")

    category = _category(db, payload.category_id) if payload.category_id else ticket.category
    if payload.assigned_to_user_id:
        assignee_id = _active_user(db, payload.assigned_to_user_id).id
    else:
        assignee_id = pick_assignee(db, category)

    ticket.category_id = category.id if category else ticket.category_id
    ticket.assigned_to_user_id = assignee_id
    if ticket.status == "done":
        ticket.status = "todo"
    add_history(
        ticket, "forwarded", _name(db, current_user.id),
        category=category.name if category else None,
        assigned_to=_name(db, assignee_id),
        note=note,
    )
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return _serialize(ticket)


@router.delete("/{ticket_id}")
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _get_visible(db, current_user, ticket_id)
    if not (sees_all_tickets(db, current_user) or ticket.created_by_user_id == current_user.id):
        raise HTTPException(
            status_code=403, detail="Only the person who filed it can delete this ticket."
        )
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
    # Public tickets: also send this reply to the customer.
    to_customer: bool = False


def _serialize_comment(comment: TicketComment, current_user_id: int, creator_id) -> dict:
    return {
        "id": comment.id,
        "body": comment.body,
        "user_id": comment.user_id,
        "user_name": _display_name(comment.user),
        "is_creator": creator_id is not None and comment.user_id == creator_id,
        "is_mine": comment.user_id == current_user_id,
        "to_customer": bool(comment.to_customer),
        "created_at": comment.created_at,
    }


@router.get("/{ticket_id}/comments")
def list_ticket_comments(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Oldest first, like a conversation."""
    ticket = _get_visible(db, current_user, ticket_id)
    comments = (
        db.query(TicketComment)
        .options(joinedload(TicketComment.user).joinedload(User.employee))
        .filter(TicketComment.ticket_id == ticket.id)
        .order_by(TicketComment.created_at.asc(), TicketComment.id.asc())
        .all()
    )
    return [_serialize_comment(c, current_user.id, ticket.created_by_user_id) for c in comments]


@router.post("/{ticket_id}/comments")
def add_ticket_comment(
    ticket_id: int,
    payload: TicketCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _get_visible(db, current_user, ticket_id)
    body = (payload.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Comment can't be empty.")
    if len(body) > 5000:
        raise HTTPException(status_code=400, detail="Comment is too long (5,000 characters max).")
    to_customer = bool(payload.to_customer and ticket.source == "public")

    comment = TicketComment(
        ticket_id=ticket.id, user_id=current_user.id, body=body, to_customer=to_customer
    )
    db.add(comment)
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(comment)
    if to_customer:
        email_requester(ticket, "New reply on your ticket", body.replace("\n", "<br>"))
    return _serialize_comment(comment, current_user.id, ticket.created_by_user_id)


@router.delete("/{ticket_id}/comments/{comment_id}")
def delete_ticket_comment(
    ticket_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Only the person who wrote a comment can delete it."""
    _get_visible(db, current_user, ticket_id)
    comment = (
        db.query(TicketComment)
        .filter(TicketComment.id == comment_id, TicketComment.ticket_id == ticket_id)
        .first()
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found.")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own comments.")
    db.delete(comment)
    db.commit()
    return {"message": "Comment deleted."}


@router.post("/{ticket_id}/image")
def upload_ticket_image(
    ticket_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ticket = _get_visible(db, current_user, ticket_id)
    if image.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=400, detail="Only PNG, JPEG, WEBP, or GIF images are allowed."
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
    current_user: User = Depends(get_current_user),
):
    ticket = _get_visible(db, current_user, ticket_id)
    ticket.image_url = None
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return _serialize(ticket)

# app/api/public/support.py
#
# Public customer support (no login): file a ticket in a public category
# and check its status later with the ticket number + the phone or email
# used. Only replies staff marked "Send to customer" are shown here.
# Spam guards: a hidden honeypot field, a per-contact and per-IP daily
# limit, and an image size limit.

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.tickets import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    STATUS_LABELS,
    _next_ticket_no,
    _name,
    add_history,
    email_requester,
    pick_assignee,
)
from app.core.database import get_db
from app.models.ticket import Ticket
from app.models.ticket_category import TicketCategory
from app.models.ticket_comment import TicketComment
from app.services.file_service import FileService

router = APIRouter(prefix="/api/public/support", tags=["Public Support"])

MAX_PER_CONTACT_PER_DAY = 5
MAX_PER_IP_PER_DAY = 10
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


@router.get("/categories")
def public_categories(db: Session = Depends(get_db)):
    return [
        {"id": c.id, "name": c.name, "description": c.description}
        for c in db.query(TicketCategory)
        .filter(TicketCategory.is_active.is_(True), TicketCategory.is_public.is_(True))
        .order_by(TicketCategory.sort_order, TicketCategory.name)
    ]


@router.post("/tickets")
def submit_public_ticket(
    request: Request,
    name: str = Form(...),
    category_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    phone: str | None = Form(None),
    email: str | None = Form(None),
    company: str | None = Form(None),
    # Honeypot: hidden on the form; only bots fill it.
    website: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    if website:
        raise HTTPException(status_code=400, detail="Something went wrong. Please try again.")

    name, title, description = name.strip(), title.strip(), description.strip()
    phone = (phone or "").strip() or None
    email = (email or "").strip().lower() or None
    if not name or not title or not description:
        raise HTTPException(status_code=400, detail="Name, subject and details are required.")
    if not phone and not email:
        raise HTTPException(status_code=400, detail="Give a phone number or an email so we can reach you.")
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        raise HTTPException(status_code=400, detail="That email doesn't look right.")
    if phone and len(_digits(phone)) < 7:
        raise HTTPException(status_code=400, detail="That phone number doesn't look right.")

    category = (
        db.query(TicketCategory)
        .options(joinedload(TicketCategory.org_unit))
        .filter(
            TicketCategory.id == category_id,
            TicketCategory.is_active.is_(True),
            TicketCategory.is_public.is_(True),
        )
        .first()
    )
    if not category:
        raise HTTPException(status_code=400, detail="Pick a topic from the list.")

    since = datetime.utcnow() - timedelta(days=1)
    ip = request.client.host if request.client else None
    contact_filters = []
    if phone:
        contact_filters.append(Ticket.requester_phone == phone)
    if email:
        contact_filters.append(Ticket.requester_email == email)
    recent = db.query(Ticket).filter(Ticket.source == "public", Ticket.created_at >= since)
    if recent.filter(or_(*contact_filters)).count() >= MAX_PER_CONTACT_PER_DAY or (
        ip and recent.filter(Ticket.requester_ip == ip).count() >= MAX_PER_IP_PER_DAY
    ):
        raise HTTPException(
            status_code=429,
            detail="You've sent several tickets today. Please wait for our reply or try again tomorrow.",
        )

    if image is not None and (image.filename or "").strip():
        if image.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="The photo must be PNG, JPEG, WEBP or GIF.")
        image.file.seek(0, 2)
        size = image.file.tell()
        image.file.seek(0)
        if size > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="The photo is too large (8 MB max).")
    else:
        image = None

    now = datetime.utcnow()
    assignee_id = pick_assignee(db, category)
    ticket = Ticket(
        ticket_no=_next_ticket_no(db, now),
        title=title[:255],
        description=description[:5000],
        status="todo",
        category_id=category.id,
        source="public",
        requester_name=name[:150],
        requester_phone=phone[:50] if phone else None,
        requester_email=email[:150] if email else None,
        requester_company=((company or "").strip() or None),
        requester_ip=ip,
        created_by_user_id=None,
        assigned_to_user_id=assignee_id,
        created_at=now,
    )
    add_history(
        ticket, "created", f"{name} (support form)",
        category=category.name, assigned_to=_name(db, assignee_id),
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    if image is not None:
        ticket.image_url = FileService().upload_ticket_image(image, ticket.id)
        db.commit()

    email_requester(
        ticket,
        "We received your ticket",
        f"Thanks for reaching out. Your ticket has been sent to our {category.name} team.",
    )
    return {
        "ticket_no": ticket.ticket_no,
        "message": "Thanks! We received your ticket.",
    }


@router.get("/tickets/{ticket_no}")
def check_public_ticket(ticket_no: str, contact: str, db: Session = Depends(get_db)):
    """Status for the requester: ticket number + the phone or email they used."""
    ticket = (
        db.query(Ticket)
        .options(joinedload(Ticket.category))
        .filter(Ticket.ticket_no == ticket_no.strip().upper(), Ticket.source == "public")
        .first()
    )
    contact = (contact or "").strip().lower()
    matches = ticket and contact and (
        (ticket.requester_email and contact == ticket.requester_email)
        or (
            ticket.requester_phone
            and _digits(contact)
            and _digits(contact) == _digits(ticket.requester_phone)
        )
    )
    if not matches:
        raise HTTPException(
            status_code=404,
            detail="No ticket matches that number and phone/email.",
        )
    replies = (
        db.query(TicketComment)
        .filter(TicketComment.ticket_id == ticket.id, TicketComment.to_customer.is_(True))
        .order_by(TicketComment.created_at.asc())
        .all()
    )
    return {
        "ticket_no": ticket.ticket_no,
        "title": ticket.title,
        "category": ticket.category.name if ticket.category else None,
        "status": ticket.status,
        "status_label": STATUS_LABELS.get(ticket.status, ticket.status),
        "created_at": ticket.created_at,
        "replies": [{"body": r.body, "created_at": r.created_at} for r in replies],
    }

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_current_admin
from app.models.user import User
from app.models.schedule_template import ScheduleTemplate
from app.utils.response import api_response

router = APIRouter(
    prefix="/schedule-templates",
    tags=["Schedule Templates"],
)


def get_template_or_404(
    db: Session,
    template_id: int,
):
    template = (
        db.query(ScheduleTemplate).filter(ScheduleTemplate.id == template_id).first()
    )

    if not template:
        raise HTTPException(
            status_code=404,
            detail="Schedule template not found",
        )

    return template


def parse_time(value):
    if not value:
        return None

    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid time format: {value}. Use HH:MM",
        )


@router.get("/")
def get_schedule_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    templates = db.query(ScheduleTemplate).order_by(ScheduleTemplate.name.asc()).all()

    return api_response(
        [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "monday_in": str(t.monday_in) if t.monday_in else None,
                "monday_out": str(t.monday_out) if t.monday_out else None,
                "tuesday_in": str(t.tuesday_in) if t.tuesday_in else None,
                "tuesday_out": str(t.tuesday_out) if t.tuesday_out else None,
                "wednesday_in": str(t.wednesday_in) if t.wednesday_in else None,
                "wednesday_out": str(t.wednesday_out) if t.wednesday_out else None,
                "thursday_in": str(t.thursday_in) if t.thursday_in else None,
                "thursday_out": str(t.thursday_out) if t.thursday_out else None,
                "friday_in": str(t.friday_in) if t.friday_in else None,
                "friday_out": str(t.friday_out) if t.friday_out else None,
                "saturday_in": str(t.saturday_in) if t.saturday_in else None,
                "saturday_out": str(t.saturday_out) if t.saturday_out else None,
                "sunday_in": str(t.sunday_in) if t.sunday_in else None,
                "sunday_out": str(t.sunday_out) if t.sunday_out else None,
            }
            for t in templates
        ]
    )


@router.get("/{template_id}")
def get_schedule_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = get_template_or_404(db, template_id)

    return api_response(
        {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "monday_in": str(template.monday_in) if template.monday_in else None,
            "monday_out": str(template.monday_out) if template.monday_out else None,
            "tuesday_in": str(template.tuesday_in) if template.tuesday_in else None,
            "tuesday_out": str(template.tuesday_out) if template.tuesday_out else None,
            "wednesday_in": (
                str(template.wednesday_in) if template.wednesday_in else None
            ),
            "wednesday_out": (
                str(template.wednesday_out) if template.wednesday_out else None
            ),
            "thursday_in": str(template.thursday_in) if template.thursday_in else None,
            "thursday_out": (
                str(template.thursday_out) if template.thursday_out else None
            ),
            "friday_in": str(template.friday_in) if template.friday_in else None,
            "friday_out": str(template.friday_out) if template.friday_out else None,
            "saturday_in": str(template.saturday_in) if template.saturday_in else None,
            "saturday_out": (
                str(template.saturday_out) if template.saturday_out else None
            ),
            "sunday_in": str(template.sunday_in) if template.sunday_in else None,
            "sunday_out": str(template.sunday_out) if template.sunday_out else None,
        }
    )


@router.post("/")
def create_schedule_template(
    name: str = Form(...),
    description: str = Form(None),
    monday_in: str = Form(None),
    monday_out: str = Form(None),
    tuesday_in: str = Form(None),
    tuesday_out: str = Form(None),
    wednesday_in: str = Form(None),
    wednesday_out: str = Form(None),
    thursday_in: str = Form(None),
    thursday_out: str = Form(None),
    friday_in: str = Form(None),
    friday_out: str = Form(None),
    saturday_in: str = Form(None),
    saturday_out: str = Form(None),
    sunday_in: str = Form(None),
    sunday_out: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    existing = db.query(ScheduleTemplate).filter(ScheduleTemplate.name == name).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Template already exists",
        )

    template = ScheduleTemplate(
        name=name,
        description=description,
        monday_in=parse_time(monday_in),
        monday_out=parse_time(monday_out),
        tuesday_in=parse_time(tuesday_in),
        tuesday_out=parse_time(tuesday_out),
        wednesday_in=parse_time(wednesday_in),
        wednesday_out=parse_time(wednesday_out),
        thursday_in=parse_time(thursday_in),
        thursday_out=parse_time(thursday_out),
        friday_in=parse_time(friday_in),
        friday_out=parse_time(friday_out),
        saturday_in=parse_time(saturday_in),
        saturday_out=parse_time(saturday_out),
        sunday_in=parse_time(sunday_in),
        sunday_out=parse_time(sunday_out),
    )

    db.add(template)
    db.commit()
    db.refresh(template)

    return api_response(
        {"id": template.id, "message": "Schedule template created successfully"}
    )


@router.patch("/{template_id}")
def update_schedule_template(
    template_id: int,
    name: str = Form(None),
    description: str = Form(None),
    monday_in: str = Form(None),
    monday_out: str = Form(None),
    tuesday_in: str = Form(None),
    tuesday_out: str = Form(None),
    wednesday_in: str = Form(None),
    wednesday_out: str = Form(None),
    thursday_in: str = Form(None),
    thursday_out: str = Form(None),
    friday_in: str = Form(None),
    friday_out: str = Form(None),
    saturday_in: str = Form(None),
    saturday_out: str = Form(None),
    sunday_in: str = Form(None),
    sunday_out: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    template = get_template_or_404(
        db,
        template_id,
    )

    if name is not None:

        existing = (
            db.query(ScheduleTemplate)
            .filter(
                ScheduleTemplate.name == name,
                ScheduleTemplate.id != template_id,
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Template already exists",
            )

        template.name = name

    if description is not None:
        template.description = description

    if monday_in is not None:
        template.monday_in = parse_time(monday_in)

    if monday_out is not None:
        template.monday_out = parse_time(monday_out)

    if tuesday_in is not None:
        template.tuesday_in = parse_time(tuesday_in)

    if tuesday_out is not None:
        template.tuesday_out = parse_time(tuesday_out)

    if wednesday_in is not None:
        template.wednesday_in = parse_time(wednesday_in)

    if wednesday_out is not None:
        template.wednesday_out = parse_time(wednesday_out)

    if thursday_in is not None:
        template.thursday_in = parse_time(thursday_in)

    if thursday_out is not None:
        template.thursday_out = parse_time(thursday_out)

    if friday_in is not None:
        template.friday_in = parse_time(friday_in)

    if friday_out is not None:
        template.friday_out = parse_time(friday_out)

    if saturday_in is not None:
        template.saturday_in = parse_time(saturday_in)

    if saturday_out is not None:
        template.saturday_out = parse_time(saturday_out)

    if sunday_in is not None:
        template.sunday_in = parse_time(sunday_in)

    if sunday_out is not None:
        template.sunday_out = parse_time(sunday_out)

    db.commit()
    db.refresh(template)

    return api_response({"message": "Schedule template updated successfully"})


@router.delete("/{template_id}")
def delete_schedule_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    template = get_template_or_404(
        db,
        template_id,
    )

    if template.employees:
        raise HTTPException(
            status_code=400,
            detail=("Cannot delete schedule template " "assigned to employees"),
        )

    db.delete(template)
    db.commit()

    return api_response({"message": "Schedule template deleted successfully"})

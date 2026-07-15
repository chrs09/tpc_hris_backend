from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.schemas.holiday import HolidayCreate, HolidayUpdate
from app.services.nager_client import fetch_ph_holidays


async def sync_holidays_from_api(db: Session, year: int) -> dict:
    api_holidays = await fetch_ph_holidays(year)

    override_dates = {
        row.holiday_date
        for row in db.execute(
            select(Holiday.holiday_date).where(
                Holiday.override_api.is_(True),
                Holiday.holiday_date.between(
                    date_type(year, 1, 1), date_type(year, 12, 31)
                ),
            )
        ).all()
    }

    created, updated, skipped = 0, 0, 0

    for item in api_holidays:
        h_date = date_type.fromisoformat(item["date"])

        if h_date in override_dates:
            skipped += 1
            continue

        existing = db.execute(
            select(Holiday).where(
                Holiday.holiday_date == h_date,
                Holiday.source == "api",
            )
        ).scalar_one_or_none()

        holiday_type = (
            "regular" if "Public" in item.get("types", []) else "special_non_working"
        )

        if existing:
            existing.holiday_name = item["name"]   # 👈 changed from localName
            existing.holiday_type = holiday_type
            updated += 1
        else:
            db.add(
                Holiday(
                    holiday_name=item["name"],       # 👈 changed from localName
                    holiday_date=h_date,
                    holiday_type=holiday_type,
                    scope="national",
                    source="api",
                    override_api=False,
                    is_active=True,
                )
            )
            created += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def create_manual_holiday(db: Session, payload: HolidayCreate) -> Holiday:
    holiday = Holiday(**payload.model_dump(), source="manual")
    db.add(holiday)
    db.commit()
    db.refresh(holiday)
    return holiday


def update_holiday(db: Session, holiday_id: int, payload: HolidayUpdate) -> Holiday | None:
    holiday = db.get(Holiday, holiday_id)
    if not holiday:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(holiday, field, value)
    db.commit()
    db.refresh(holiday)
    return holiday


def delete_holiday(db: Session, holiday_id: int) -> bool:
    holiday = db.get(Holiday, holiday_id)
    if not holiday:
        return False
    db.delete(holiday)
    db.commit()
    return True
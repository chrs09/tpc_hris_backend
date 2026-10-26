# app/api/admin/page_titles.py
#
# Renameable labels on a page (e.g. the Fleet Management cards "Vehicle
# List" / "Vehicle Maintenance" / "Vehicle Types"). Kept as one JSON row
# per page in tpc_app_settings -- no table of its own. Anyone signed in
# reads them; only the superadmin changes them.

import json

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_superadmin
from app.models.app_setting import AppSetting

router = APIRouter(prefix="/page-titles", tags=["Page Titles"])

# Pages and the labels each one lets the superadmin rename.
PAGES = {
    "fleet_management": {"units", "maintenance", "truck_types"},
}
_MAX_TITLE = 40


def _key(page: str) -> str:
    if page not in PAGES:
        raise HTTPException(status_code=404, detail="Unknown page.")
    return f"page_titles.{page}"


def _read(db: Session, page: str) -> dict:
    row = db.query(AppSetting).filter(AppSetting.key == _key(page)).first()
    try:
        titles = json.loads(row.value) if row else {}
    except ValueError:
        titles = {}
    return {k: v for k, v in titles.items() if k in PAGES[page]}


@router.get("/{page}")
def get_page_titles(
    page: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Custom titles only -- the page keeps its default for any not set."""
    return _read(db, page)


@router.put("/{page}")
def set_page_titles(
    page: str,
    titles: dict[str, str] = Body(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    """Sets the given titles; a blank one goes back to the default."""
    key = _key(page)
    current = _read(db, page)
    for name, value in titles.items():
        if name not in PAGES[page]:
            raise HTTPException(status_code=400, detail=f"Unknown title: {name}")
        value = (value or "").strip()
        if len(value) > _MAX_TITLE:
            raise HTTPException(
                status_code=400,
                detail=f"Titles can be at most {_MAX_TITLE} characters.",
            )
        if value:
            current[name] = value
        else:
            current.pop(name, None)

    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        row = AppSetting(key=key, value="{}", description="Renamed page titles")
        db.add(row)
    row.value = json.dumps(current)
    db.commit()
    return current

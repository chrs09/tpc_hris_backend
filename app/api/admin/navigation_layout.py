# app/api/admin/navigation_layout.py
#
# A superadmin's own menu arrangement, set in Administrator -> Settings ->
# Navigation. Saved per superadmin account; everyone else (and a View As
# session) always gets the default menu.
#   sidebar_order -- sidebar groups, top to bottom, by label ("Payroll",
#                    "Trip Management" ...). Groups not listed keep their
#                    default place after the listed ones.
#   mobile_tabs   -- the groups in the phone's bottom bar, between Home and
#                    Menu (up to 4).
# Kept in tpc_app_settings (one JSON row each) -- no table of its own.

import json

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_superadmin
from app.models.app_setting import AppSetting

router = APIRouter(prefix="/navigation-layout", tags=["Navigation Layout"])


def _keys(user) -> tuple[str, str]:
    return f"nav.sidebar_order.user.{user.id}", f"nav.mobile_tabs.user.{user.id}"


def _is_superadmin(user) -> bool:
    return (getattr(user.role, "value", user.role) or "").lower() == "superadmin"


DEFAULT_TABS = ["Approvals", "Trip Management", "Tickets"]
MAX_TABS = 4
_MAX_LABEL = 40
_MAX_VALUE = 255  # tpc_app_settings.value


def _read(db: Session, key: str, default: list) -> list:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row:
        return list(default)
    try:
        value = json.loads(row.value)
    except ValueError:
        return list(default)
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else list(default)


def _write(db: Session, key: str, value: list, description: str) -> None:
    text = json.dumps(value, separators=(",", ":"))
    if len(text) > _MAX_VALUE:
        raise HTTPException(status_code=400, detail="Too many items to save.")
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        row = AppSetting(key=key, value=text, description=description)
        db.add(row)
    row.value = text


def _clean(labels, name: str) -> list:
    if not isinstance(labels, list):
        raise HTTPException(status_code=400, detail=f"{name} must be a list.")
    out = []
    for label in labels:
        label = str(label or "").strip()
        if not label or len(label) > _MAX_LABEL:
            raise HTTPException(status_code=400, detail=f"Invalid item in {name}.")
        if label not in out:
            out.append(label)
    return out


@router.get("")
def get_navigation_layout(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not _is_superadmin(current_user):
        return {"sidebar_order": [], "mobile_tabs": list(DEFAULT_TABS)}
    sidebar_key, tabs_key = _keys(current_user)
    return {
        "sidebar_order": _read(db, sidebar_key, []),
        "mobile_tabs": _read(db, tabs_key, DEFAULT_TABS),
    }


@router.put("")
def set_navigation_layout(
    sidebar_order: list = Body(None),
    mobile_tabs: list = Body(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    """Saves the signed-in superadmin's own arrangement (whichever of the
    two is sent). An empty sidebar_order goes back to the default order."""
    sidebar_key, tabs_key = _keys(current_user)
    if sidebar_order is not None:
        _write(db, sidebar_key, _clean(sidebar_order, "Sidebar order"), "Sidebar group order")
    if mobile_tabs is not None:
        tabs = _clean(mobile_tabs, "Bottom bar")
        if len(tabs) > MAX_TABS:
            raise HTTPException(status_code=400, detail=f"Pick up to {MAX_TABS} for the bottom bar.")
        _write(db, tabs_key, tabs, "Phone bottom bar groups")
    db.commit()
    return get_navigation_layout(db, current_user)

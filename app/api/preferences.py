# app/api/preferences.py
#
# The logged-in user's own settings -- for now their theme: light / dark /
# follow the device, and an accent colour. Stored on their account so it
# follows them on every device; the browser keeps a copy so it applies
# instantly before this loads.

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/me", tags=["My Preferences"])

MODES = ("light", "dark", "system")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class ThemeIn(BaseModel):
    mode: str | None = None
    # "#rrggbb", or null for the default accent.
    accent: str | None = None


def _read(user: User) -> dict:
    try:
        data = json.loads(user.theme_preference) if user.theme_preference else {}
    except (TypeError, ValueError):
        data = {}
    return {"mode": data.get("mode"), "accent": data.get("accent")}


@router.get("/theme")
def get_my_theme(current_user: User = Depends(get_current_user)):
    return _read(current_user)


@router.put("/theme")
def save_my_theme(
    payload: ThemeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.mode is not None and payload.mode not in MODES:
        raise HTTPException(status_code=400, detail="Mode must be light, dark or system.")
    if payload.accent is not None and not HEX.match(payload.accent):
        raise HTTPException(status_code=400, detail="Accent must be a colour like #047857.")
    user = db.query(User).filter(User.id == current_user.id).first()
    user.theme_preference = json.dumps(
        {"mode": payload.mode, "accent": payload.accent.lower() if payload.accent else None}
    )
    db.commit()
    return _read(user)

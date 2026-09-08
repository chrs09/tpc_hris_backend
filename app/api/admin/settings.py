# app/api/admin/settings.py
#
# Superadmin-only management of the tpc_app_settings key/value table (see
# app/models/app_setting.py). Required so that settings like
# "wallet_settlement_source" -- which used to be a hardcoded Python
# constant in app/api/driver/trips.py -- can actually be changed by an
# admin without editing code and redeploying.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_superadmin
from app.models.app_setting import AppSetting

router = APIRouter(prefix="/admin/settings", tags=["Admin Settings"])


class SettingUpdateRequest(BaseModel):
    value: str


def _serialize(setting: AppSetting) -> dict:
    return {
        "key": setting.key,
        "value": setting.value,
        "description": setting.description,
        "updated_at": setting.updated_at,
    }


@router.get("/")
def list_settings(
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    """Lists every row in tpc_app_settings, for a superadmin settings screen."""
    settings = db.query(AppSetting).order_by(AppSetting.key.asc()).all()
    return [_serialize(setting) for setting in settings]


@router.get("/{key}")
def get_setting(
    key: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    """Reads a single setting by key."""
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()

    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found.")

    return _serialize(setting)


@router.put("/{key}")
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_superadmin),
):
    """Updates a setting's value. The row must already exist (created via
    a migration, as with wallet_settlement_source) -- this endpoint does
    not create new setting keys, to avoid accidental typos silently
    creating unused rows that nothing reads."""
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()

    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found.")

    setting.value = payload.value
    db.commit()
    db.refresh(setting)

    return _serialize(setting)

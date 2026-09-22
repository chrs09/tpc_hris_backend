# app/api/mobile_app_version.py
#
# Lets tytan_mobile check, on launch, whether it's running an outdated
# build -- needed because the current testing channel is a directly
# distributed APK (not Google Play), which has no store-driven update
# mechanism of its own. Public/unauthenticated on purpose: the check
# should work even before login, so a very outdated app can still be
# told to update.

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_superadmin
from app.models.mobile_app_version import MobileAppVersion
from app.models.user import User
from app.schemas.mobile_app_version import MobileAppVersionUpdate

router = APIRouter(prefix="/mobile-app-version", tags=["Mobile App Version"])

_EXPO_PLATFORM_MAP = {"android": "ANDROID", "ios": "IOS"}


def _serialize(row: MobileAppVersion) -> dict:
    return {
        "platform": row.platform,
        "latest_version": row.latest_version,
        "min_supported_version": row.min_supported_version,
        "apk_url": row.apk_url,
        "release_notes": row.release_notes,
        "updated_at": row.updated_at,
    }


@router.get("/{platform}")
def get_latest_version(platform: str, db: Session = Depends(get_db)):
    row = (
        db.query(MobileAppVersion)
        .filter(MobileAppVersion.platform == platform)
        .first()
    )

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No published version info for platform '{platform}' yet.",
        )

    return _serialize(row)


@router.put("/{platform}")
def set_latest_version(
    platform: str,
    payload: MobileAppVersionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    row = (
        db.query(MobileAppVersion)
        .filter(MobileAppVersion.platform == platform)
        .first()
    )

    if not row:
        row = MobileAppVersion(platform=platform)
        db.add(row)

    row.latest_version = payload.latest_version
    row.min_supported_version = payload.min_supported_version
    row.apk_url = payload.apk_url
    row.release_notes = payload.release_notes
    row.updated_by_user_id = current_user.id

    db.commit()
    db.refresh(row)

    return _serialize(row)


@router.post("/{platform}/sync-from-eas")
def sync_from_eas(
    platform: str,
    profile: str = "preview",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Pulls the most recent finished EAS build for this platform+profile
    (e.g. android/preview) and updates latest_version/apk_url from it --
    an alternative to typing them in by hand after every `eas build`.
    Deliberately leaves min_supported_version and release_notes alone;
    those stay a manual decision, not something EAS knows about."""
    if not settings.EXPO_ACCESS_TOKEN:
        raise HTTPException(
            status_code=400,
            detail=(
                "EXPO_ACCESS_TOKEN is not configured on the server -- "
                "generate one at expo.dev (Account Settings -> Access "
                "Tokens) and add it to the backend's .env."
            ),
        )

    expo_platform = _EXPO_PLATFORM_MAP.get(platform.lower())
    if not expo_platform:
        raise HTTPException(
            status_code=400, detail=f"Unsupported platform '{platform}'."
        )

    # Expo's public REST API (v2/projects/{id}/builds) doesn't actually
    # exist -- confirmed by hitting it directly (404). The real data
    # lives behind the same GraphQL API eas-cli itself uses. Confirmed
    # live against this project: `buildProfile` (not `channel`, which
    # comes back null unless the build was made with a channel set in
    # eas.json) is the field that matches eas.json's profile names
    # ("development"/"preview"/"production") exactly.
    query = """
        query($appId: String!, $limit: Int!) {
          app {
            byId(appId: $appId) {
              builds(offset: 0, limit: $limit) {
                id
                status
                platform
                appVersion
                buildProfile
                createdAt
                artifacts {
                  buildUrl
                }
              }
            }
          }
        }
    """

    try:
        response = requests.post(
            "https://api.expo.dev/graphql",
            headers={
                "Authorization": f"Bearer {settings.EXPO_ACCESS_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "variables": {"appId": settings.EXPO_PROJECT_ID, "limit": 50},
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail=f"Could not reach Expo's API: {exc}"
        )
    except ValueError:
        raise HTTPException(
            status_code=502, detail="Expo's API returned an unreadable response."
        )

    if payload.get("errors"):
        raise HTTPException(
            status_code=502,
            detail=f"Expo's API returned an error: {payload['errors']}",
        )

    builds = (
        (payload.get("data") or {}).get("app", {}).get("byId", {}).get("builds")
        or []
    )

    def matches(build: dict) -> bool:
        return (
            build.get("platform") == expo_platform
            and build.get("status") == "FINISHED"
            and build.get("buildProfile") == profile
        )

    candidates = sorted(
        (b for b in builds if matches(b)),
        key=lambda b: b.get("createdAt", ""),
        reverse=True,
    )

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No finished '{profile}' builds found for {platform} on "
                "Expo. Make sure the build has finished and eas.json's "
                f"'{profile}' profile has a matching channel."
            ),
        )

    latest = candidates[0]
    app_version = latest.get("appVersion")
    artifacts = latest.get("artifacts") or {}
    apk_url = artifacts.get("buildUrl") or artifacts.get("applicationArchiveUrl")

    if not app_version or not apk_url:
        raise HTTPException(
            status_code=502,
            detail="Found a matching build, but couldn't read its version or download URL from Expo's response.",
        )

    row = (
        db.query(MobileAppVersion)
        .filter(MobileAppVersion.platform == platform)
        .first()
    )

    if not row:
        row = MobileAppVersion(
            platform=platform,
            min_supported_version=app_version,
        )
        db.add(row)

    row.latest_version = app_version
    row.apk_url = apk_url
    row.updated_by_user_id = current_user.id

    db.commit()
    db.refresh(row)

    return _serialize(row)

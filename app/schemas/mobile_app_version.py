from pydantic import BaseModel


class MobileAppVersionUpdate(BaseModel):
    latest_version: str
    min_supported_version: str
    apk_url: str
    release_notes: str | None = None

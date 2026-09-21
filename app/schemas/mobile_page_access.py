from pydantic import BaseModel


class MobilePageAccessSet(BaseModel):
    page_keys: list[str]

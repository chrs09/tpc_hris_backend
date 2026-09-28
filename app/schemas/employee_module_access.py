from pydantic import BaseModel


class ModuleAccessSet(BaseModel):
    module_keys: list[str]
    # Granted keys that are view-only (can't edit). Omit to keep each
    # key's current setting (e.g. the Module Assignment page, which
    # doesn't edit this).
    read_only_keys: list[str] | None = None

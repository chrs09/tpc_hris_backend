from pydantic import BaseModel


class ModuleAccessSet(BaseModel):
    module_keys: list[str]

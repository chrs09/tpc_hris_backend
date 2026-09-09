from pydantic import BaseModel


class DepartmentHeadSet(BaseModel):
    head_user_id: int

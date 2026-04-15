from typing import Optional

from pydantic import BaseModel, Field


class ApplicantQuestionCreate(BaseModel):
    target_role: str = Field(..., min_length=1, max_length=50)
    key_suffix: str = Field(..., min_length=1, max_length=100)
    question_text: str = Field(..., min_length=1)
    question_type: str = Field(..., min_length=1, max_length=50)
    is_required: bool = False
    sort_order: Optional[int] = None
    is_active: bool = True


class ApplicantQuestionUpdate(BaseModel):
    target_role: str = Field(..., min_length=1, max_length=50)
    question_text: str = Field(..., min_length=1)
    question_type: str = Field(..., min_length=1, max_length=50)
    is_required: bool = False
    sort_order: Optional[int] = None
    is_active: bool = True


class ApplicantQuestionResponse(BaseModel):
    id: int
    target_role: str
    question_key: str
    question_text: str
    question_type: str
    is_required: bool
    sort_order: int
    is_active: bool
    created_by_user_id: int | None = None

    class Config:
        from_attributes = True

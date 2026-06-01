from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..models.feedback import FeedbackCategory, FeedbackStatus


class FeedbackCreate(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    category: FeedbackCategory = FeedbackCategory.SUGESTAO

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: object) -> FeedbackCategory:
        if isinstance(v, FeedbackCategory):
            return v
        try:
            return FeedbackCategory(str(v or "").strip().lower())
        except Exception:
            return FeedbackCategory.SUGESTAO


class FeedbackStatusUpdate(BaseModel):
    status: FeedbackStatus

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: object) -> FeedbackStatus:
        if isinstance(v, FeedbackStatus):
            return v
        return FeedbackStatus(str(v or "").strip().lower())


class FeedbackOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    message: str
    category: FeedbackCategory
    status: FeedbackStatus
    created_at: datetime
    read_at: datetime | None = None
    read_by_id: int | None = None
    read_by_name: str | None = None

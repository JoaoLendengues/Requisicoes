from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from ..models.feedback import FeedbackCategory, FeedbackStatus


class FeedbackCreate(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    category: FeedbackCategory = FeedbackCategory.SUGESTAO
    is_public: bool = True

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


class FeedbackReactionUpdate(BaseModel):
    """`None` = remover reação."""
    reaction: Optional[Literal["like", "dislike"]] = None


class FeedbackOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    message: str
    category: FeedbackCategory
    status: FeedbackStatus
    is_public: bool
    created_at: datetime
    read_at: datetime | None = None
    read_by_id: int | None = None
    read_by_name: str | None = None

    # Reações
    likes: int = 0
    dislikes: int = 0
    my_reaction: Optional[Literal["like", "dislike"]] = None


class FeedbackUnreadCount(BaseModel):
    unread: int = 0

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    message: str = Field(min_length=1, max_length=150)


class FeedbackOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    message: str
    created_at: datetime
    read_at: datetime | None = None
    read_by_id: int | None = None
    read_by_name: str | None = None


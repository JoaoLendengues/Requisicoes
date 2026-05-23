from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator

from ..services.text_normalizer import normalize_upper_optional, normalize_upper_required


class ProductCreate(BaseModel):
    code: str
    name: str

    @field_validator("code", "name", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        return normalize_upper_required(value)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


class ProductBulkItem(BaseModel):
    code: str
    name: str

    @field_validator("code", "name", mode="before")
    @classmethod
    def normalize_bulk_text(cls, value: object) -> str:
        return normalize_upper_required(value)


class ProductBulkImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = []


class ProductResponse(BaseModel):
    id: int
    code: str
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

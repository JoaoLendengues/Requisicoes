from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional
from ..models.user import Role
from ..services.text_normalizer import normalize_upper_optional, normalize_upper_required


class UserCreate(BaseModel):
    code: str
    name: str
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Role = Role.VENDEDOR
    whatsapp: Optional[str] = None
    sector: Optional[str] = None
    is_active: bool = True

    @field_validator("code", "name", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        return normalize_upper_required(value)

    @field_validator("sector", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


class UserUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[Role] = None
    whatsapp: Optional[str] = None
    sector: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("code", "name", mode="before")
    @classmethod
    def normalize_update_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)

    @field_validator("sector", mode="before")
    @classmethod
    def normalize_update_optional_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


class UserBulkItem(BaseModel):
    code: str
    name: str
    contact: Optional[str] = None
    sector: Optional[str] = None

    @field_validator("code", "name", mode="before")
    @classmethod
    def normalize_bulk_required_text(cls, value: object) -> str:
        return normalize_upper_required(value)

    @field_validator("sector", mode="before")
    @classmethod
    def normalize_bulk_optional_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


class UserBulkImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = []


class UserResponse(BaseModel):
    id: int
    code: str
    name: str
    email: Optional[str] = None
    role: Role
    whatsapp: Optional[str]
    sector: Optional[str]
    must_change_password: bool
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}

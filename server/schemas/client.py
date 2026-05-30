from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional
from ..services.text_normalizer import normalize_upper_optional, normalize_upper_required


class ClientCreate(BaseModel):
    code: str
    name: str
    cnpj: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("code", "name", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        return normalize_upper_required(value)

    @field_validator("address", "city", "state", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    cnpj: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None

    @field_validator("name", "address", "city", "state", mode="before")
    @classmethod
    def normalize_update_text(cls, value: object) -> str | None:
        return normalize_upper_optional(value)


class ClientBulkItem(BaseModel):
    """Um item dentro de uma importação em lote."""
    code: str
    name: str
    cnpj: Optional[str] = None

    @field_validator("code", "name", mode="before")
    @classmethod
    def normalize_bulk_text(cls, value: object) -> str:
        return normalize_upper_required(value)


class BulkImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = []


class ClientResponse(BaseModel):
    id: int
    code: str
    name: str
    cnpj: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

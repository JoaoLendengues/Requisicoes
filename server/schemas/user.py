from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from ..models.user import Role


class UserCreate(BaseModel):
    code: str
    name: str
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Role = Role.VENDEDOR
    whatsapp: Optional[str] = None
    sector: Optional[str] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[Role] = None
    whatsapp: Optional[str] = None
    sector: Optional[str] = None
    must_change_password: Optional[bool] = None
    is_active: Optional[bool] = None


class UserBulkItem(BaseModel):
    code: str
    name: str
    contact: Optional[str] = None
    sector: Optional[str] = None


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
    created_at: datetime

    model_config = {"from_attributes": True}

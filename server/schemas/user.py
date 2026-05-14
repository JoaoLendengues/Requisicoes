from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from ..models.user import Role


class UserCreate(BaseModel):
    code: str
    name: str
    email: EmailStr
    password: str
    role: Role = Role.VENDEDOR
    whatsapp: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[Role] = None
    whatsapp: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    code: str
    name: str
    email: str
    role: Role
    whatsapp: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

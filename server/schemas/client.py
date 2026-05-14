from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class ClientCreate(BaseModel):
    code: str
    name: str
    cnpj: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    cnpj: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


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

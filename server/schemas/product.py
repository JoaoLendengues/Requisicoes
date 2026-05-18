from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ProductCreate(BaseModel):
    code: str
    name: str


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class ProductBulkItem(BaseModel):
    code: str
    name: str


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

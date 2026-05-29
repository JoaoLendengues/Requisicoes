from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..models.production_machine import MachineOperationalStatus
from ..models.user import Role
from ..services.text_normalizer import normalize_upper_required


class ProductionMachineOperatorResponse(BaseModel):
    id: int
    code: str
    name: str
    role: Role

    model_config = {"from_attributes": True}


class ProductionMachineRegistryResponse(BaseModel):
    id: int
    destination: str
    name: str
    sort_order: int
    status: MachineOperationalStatus
    updated_at: datetime
    operators: list[ProductionMachineOperatorResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ProductionMachineRegistryCreate(BaseModel):
    name: str
    destination: str
    operator_ids: list[int] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str:
        return normalize_upper_required(value)

    @field_validator("operator_ids", mode="before")
    @classmethod
    def normalize_operator_ids(cls, value: object) -> list[int]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("operator_ids deve ser uma lista")

        normalized: list[int] = []
        seen: set[int] = set()
        for item in value:
            try:
                user_id = int(item)
            except (TypeError, ValueError):
                continue
            if user_id <= 0 or user_id in seen:
                continue
            seen.add(user_id)
            normalized.append(user_id)
        return normalized


class ProductionMachineRegistryUpdate(ProductionMachineRegistryCreate):
    pass

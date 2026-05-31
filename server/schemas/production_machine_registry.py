from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..models.operator import OperatorRole
from ..models.production_machine import MachineOperationalStatus
from ..services.text_normalizer import normalize_upper_required


class OperatorResponse(BaseModel):
    id: int
    name: str
    role: OperatorRole
    model_config = {"from_attributes": True}


# Alias para compatibilidade com código existente
ProductionMachineOperatorResponse = OperatorResponse


class ProductionMachineRegistryResponse(BaseModel):
    id: int
    destination: str
    name: str
    sort_order: int
    status: MachineOperationalStatus
    updated_at: datetime
    operators: list[OperatorResponse] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class ProductionMachineRegistryCreate(BaseModel):
    name: str
    destination: str
    # Nomes livres — servidor faz upsert em `operators` e vincula à máquina
    operator_names: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v: object) -> str:
        return normalize_upper_required(v)

    @field_validator("operator_names", mode="before")
    @classmethod
    def normalize_operator_names(cls, v: object) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, (list, tuple, set)):
            raise ValueError("operator_names deve ser uma lista")
        seen: set[str] = set()
        result: list[str] = []
        for item in v:
            n = normalize_upper_required(item) if item else ""
            if n and n not in seen:
                seen.add(n)
                result.append(n)
        return result


class ProductionMachineRegistryUpdate(ProductionMachineRegistryCreate):
    pass

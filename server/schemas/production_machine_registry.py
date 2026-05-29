from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from ..models.production_machine import MachineOperationalStatus
from ..services.text_normalizer import normalize_upper_required


class OperatorResponse(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


# Mantido para compatibilidade com código existente que importa esse nome.
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
    # Nomes livres dos operadores — o servidor faz upsert em `operators`
    # e vincula à máquina via production_machine_operators.
    operator_names: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str:
        return normalize_upper_required(value)

    @field_validator("operator_names", mode="before")
    @classmethod
    def normalize_operator_names(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("operator_names deve ser uma lista")
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            normalized = normalize_upper_required(item) if item else ""
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result


class ProductionMachineRegistryUpdate(ProductionMachineRegistryCreate):
    pass


# ── Schemas para o cadastro independente de operadores ────────────────────────

class OperatorCreate(BaseModel):
    name: str

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str:
        return normalize_upper_required(value)


class OperatorUpdate(OperatorCreate):
    pass

from pydantic import BaseModel, Field, field_validator


class CancelReasonItem(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=3, max_length=255)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> str:
        return " ".join(str(value or "").upper().split())

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> str:
        return " ".join(str(value or "").split())


class OperationalSettingsResponse(BaseModel):
    pending_invoice_alert_days: int = Field(default=1, ge=1, le=3650)
    min_delivery_business_days: int = Field(default=0, ge=0, le=365)
    cancel_reasons: list[CancelReasonItem] = Field(default_factory=list)


class OperationalSettingsUpdate(BaseModel):
    pending_invoice_alert_days: int | None = Field(default=None, ge=1, le=3650)
    min_delivery_business_days: int | None = Field(default=None, ge=0, le=365)
    cancel_reasons: list[CancelReasonItem] | None = None

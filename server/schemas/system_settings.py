from pydantic import BaseModel, Field


class OperationalSettingsResponse(BaseModel):
    pending_invoice_alert_days: int = Field(default=1, ge=1, le=3650)
    min_delivery_business_days: int = Field(default=0, ge=0, le=365)


class OperationalSettingsUpdate(BaseModel):
    pending_invoice_alert_days: int | None = Field(default=None, ge=1, le=3650)
    min_delivery_business_days: int | None = Field(default=None, ge=0, le=365)

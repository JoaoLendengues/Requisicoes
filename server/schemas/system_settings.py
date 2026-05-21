from pydantic import BaseModel, Field


class OperationalSettingsResponse(BaseModel):
    pending_invoice_alert_days: int = Field(default=1, ge=1, le=3650)


class OperationalSettingsUpdate(BaseModel):
    pending_invoice_alert_days: int = Field(..., ge=1, le=3650)

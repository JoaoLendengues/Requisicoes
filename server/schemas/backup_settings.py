from pydantic import BaseModel, Field


class BackupSettingsResponse(BaseModel):
    daily_enabled:     bool = True
    weekly_enabled:    bool = True
    monthly_enabled:   bool = False
    daily_hour:        int  = Field(default=2,  ge=0,  le=23)
    retention_daily:   int  = Field(default=15, ge=1,  le=365)
    retention_weekly:  int  = Field(default=8,  ge=1,  le=52)
    retention_monthly: int  = Field(default=6,  ge=1,  le=24)


class BackupSettingsUpdate(BaseModel):
    """Todos os campos são opcionais — permite PATCH parcial."""
    daily_enabled:     bool | None = None
    weekly_enabled:    bool | None = None
    monthly_enabled:   bool | None = None
    daily_hour:        int  | None = Field(default=None, ge=0,  le=23)
    retention_daily:   int  | None = Field(default=None, ge=1,  le=365)
    retention_weekly:  int  | None = Field(default=None, ge=1,  le=52)
    retention_monthly: int  | None = Field(default=None, ge=1,  le=24)

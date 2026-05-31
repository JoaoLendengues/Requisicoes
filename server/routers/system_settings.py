from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, require_manager_or_admin
from ..models.user import User
from ..schemas.system_settings import (
    OperationalSettingsResponse,
    OperationalSettingsUpdate,
)
from ..services.system_settings import (
    load_operational_settings,
    save_operational_settings,
)


router = APIRouter(prefix="/system-settings", tags=["Configurações do Sistema"])


@router.get("/operational", response_model=OperationalSettingsResponse)
def get_operational_settings(_: User = Depends(get_current_user)):
    return OperationalSettingsResponse(**load_operational_settings())


@router.patch("/operational", response_model=OperationalSettingsResponse)
def update_operational_settings(
    data: OperationalSettingsUpdate,
    _: User = Depends(require_manager_or_admin),
):
    saved = save_operational_settings(
        pending_invoice_alert_days=data.pending_invoice_alert_days,
        min_delivery_business_days=data.min_delivery_business_days,
        cancel_reasons=(
            [item.model_dump() for item in data.cancel_reasons]
            if data.cancel_reasons is not None
            else None
        ),
        delivery_cancel_reasons=(
            [item.model_dump() for item in data.delivery_cancel_reasons]
            if data.delivery_cancel_reasons is not None
            else None
        ),
        delivery_deadline_change_reasons=(
            [item.model_dump() for item in data.delivery_deadline_change_reasons]
            if data.delivery_deadline_change_reasons is not None
            else None
        ),
    )
    return OperationalSettingsResponse(**saved)

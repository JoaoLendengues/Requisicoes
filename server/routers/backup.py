from fastapi import APIRouter, Depends

from ..dependencies import require_admin
from ..models.user import User
from ..schemas.backup_settings import BackupSettingsResponse, BackupSettingsUpdate
from ..services.backup_service import list_backups, run_backup
from ..services.backup_settings_service import load_backup_settings, save_backup_settings

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.post("/run")
def trigger_backup(_: User = Depends(require_admin)):
    """Dispara um backup manual imediato (somente admin)."""
    return run_backup("manual")


@router.get("/list")
def get_backup_list(_: User = Depends(require_admin)):
    """Retorna a lista de backups existentes (somente admin)."""
    return list_backups()


@router.get("/settings", response_model=BackupSettingsResponse)
def get_settings(_: User = Depends(require_admin)):
    """Retorna as configurações de agendamento de backup (somente admin)."""
    return load_backup_settings()


@router.patch("/settings", response_model=BackupSettingsResponse)
def update_settings(data: BackupSettingsUpdate, _: User = Depends(require_admin)):
    """Atualiza as configurações de agendamento de backup (somente admin)."""
    return save_backup_settings(data.model_dump(exclude_none=True))

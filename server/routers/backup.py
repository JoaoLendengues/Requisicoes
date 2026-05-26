from fastapi import APIRouter, Depends

from ..dependencies import require_admin
from ..models.user import User
from ..services.backup_service import list_backups, run_backup

router = APIRouter(prefix="/backup", tags=["Backup"])


@router.post("/run")
def trigger_backup(_: User = Depends(require_admin)):
    """Dispara um backup manual imediato (somente admin)."""
    return run_backup("manual")


@router.get("/list")
def get_backup_list(_: User = Depends(require_admin)):
    """Retorna a lista de backups existentes (somente admin)."""
    return list_backups()

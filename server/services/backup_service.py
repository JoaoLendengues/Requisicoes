"""
Serviço de backup do banco de dados PostgreSQL.

Usa pg_dump para gerar arquivos .sql na pasta de rede configurada em
settings.BACKUP_FOLDER.  O agendador interno (backup_scheduler) roda
como task asyncio em background — iniciado no lifespan do FastAPI.

Tipos de backup:
  diario   → backup_diario_YYYY-MM-DD.sql          (todo dia às daily_hour)
  semanal  → backup_semanal_YYYY_SXX.sql            (toda segunda-feira)
  mensal   → backup_mensal_YYYY-MM.sql              (dia 1 de cada mês)
  manual   → backup_manual_YYYY-MM-DD_HH-MM-SS.sql  (disparado pelo admin via API)

Rotação: mantém os N arquivos mais recentes de cada tipo, conforme
configurado em backup_settings.json (via backup_settings_service).
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta

from ..config import settings
from .backup_settings_service import load_backup_settings

log = logging.getLogger(__name__)

# ── Localização do pg_dump ────────────────────────────────────────────────────

def _find_pg_dump() -> str | None:
    """Procura o executável pg_dump no PATH e em instalações padrão do Windows."""
    found = shutil.which("pg_dump") or shutil.which("pg_dump.exe")
    if found:
        return found
    for version in range(17, 9, -1):
        for base in (r"C:\Program Files", r"C:\Program Files (x86)"):
            candidate = os.path.join(base, "PostgreSQL", str(version), "bin", "pg_dump.exe")
            if os.path.exists(candidate):
                return candidate
    return None


def _get_db_params() -> dict:
    """Retorna os parâmetros de conexão para o pg_dump a partir das settings."""
    return {
        "host":     settings.BACKUP_DB_HOST,
        "port":     str(settings.BACKUP_DB_PORT),
        "user":     settings.BACKUP_DB_USER,
        "password": settings.BACKUP_DB_PASSWORD,
        "dbname":   settings.BACKUP_DB_NAME,
    }


# ── Rotação de arquivos ───────────────────────────────────────────────────────

def _rotate(folder: str, prefix: str, retention: int) -> None:
    """Apaga os backups mais antigos quando passa do limite de retenção."""
    try:
        files = sorted(
            f for f in os.listdir(folder)
            if f.startswith(prefix) and f.endswith(".sql")
        )
        while len(files) > retention:
            os.remove(os.path.join(folder, files.pop(0)))
    except Exception as exc:
        log.warning("Rotação de backups falhou: %s", exc)


# ── Execução do backup ────────────────────────────────────────────────────────

def run_backup(backup_type: str = "manual") -> dict:
    """
    Executa pg_dump e salva o arquivo na pasta configurada.

    Retorna dict com:
      success    bool
      filename   str   (somente se success=True)
      size_bytes int   (somente se success=True)
      created_at str   (ISO 8601, somente se success=True)
      error      str   (somente se success=False)
    """
    folder = settings.BACKUP_FOLDER

    try:
        os.makedirs(folder, exist_ok=True)
    except Exception as exc:
        return {"success": False, "error": f"Pasta de backup inacessível: {exc}"}

    pg_dump = _find_pg_dump()
    if not pg_dump:
        return {
            "success": False,
            "error": (
                "pg_dump não encontrado. Instale o PostgreSQL Client Tools "
                "na máquina do servidor e garanta que está no PATH."
            ),
        }

    now = datetime.now()
    cfg = load_backup_settings()

    if backup_type == "semanal":
        week     = now.isocalendar()[1]
        filename = f"backup_semanal_{now.year}_S{week:02d}.sql"
        prefix   = "backup_semanal_"
        retention = cfg.get("retention_weekly", 8)
    elif backup_type == "mensal":
        filename  = f"backup_mensal_{now.strftime('%Y-%m')}.sql"
        prefix    = "backup_mensal_"
        retention = cfg.get("retention_monthly", 6)
    elif backup_type == "manual":
        filename  = f"backup_manual_{now.strftime('%Y-%m-%d_%H-%M-%S')}.sql"
        prefix    = "backup_manual_"
        retention = cfg.get("retention_daily", 15)   # manual usa retenção do diário
    else:  # diario
        filename  = f"backup_diario_{now.strftime('%Y-%m-%d')}.sql"
        prefix    = "backup_diario_"
        retention = cfg.get("retention_daily", 15)

    filepath = os.path.join(folder, filename)
    params   = _get_db_params()

    env = os.environ.copy()
    env["PGPASSWORD"] = params["password"]

    cmd = [
        pg_dump,
        "-h", params["host"],
        "-p", params["port"],
        "-U", params["user"],
        "-d", params["dbname"],
        "-F", "p",        # plain SQL — legível e restaurável com psql
        "--no-password",
        "-f", filepath,
    ]

    try:
        result = subprocess.run(
            cmd, env=env,
            capture_output=True, text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout: pg_dump demorou mais de 5 minutos."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        return {"success": False, "error": stderr or f"pg_dump retornou código {result.returncode}"}

    try:
        size = os.path.getsize(filepath)
    except Exception:
        size = 0

    _rotate(folder, prefix, retention)
    log.info("Backup '%s' concluído (%d bytes).", filename, size)

    return {
        "success":    True,
        "filename":   filename,
        "size_bytes": size,
        "created_at": now.isoformat(),
    }


# ── Listagem ──────────────────────────────────────────────────────────────────

def list_backups() -> list[dict]:
    """Retorna lista de backups existentes, do mais recente para o mais antigo."""
    folder = settings.BACKUP_FOLDER
    try:
        entries = []
        for name in os.listdir(folder):
            if not (name.startswith("backup_") and name.endswith(".sql")):
                continue
            path = os.path.join(folder, name)
            try:
                stat = os.stat(path)
                entries.append({
                    "filename":   name,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except Exception:
                pass
        return sorted(entries, key=lambda x: x["filename"], reverse=True)
    except Exception:
        return []


# ── Agendador asyncio ─────────────────────────────────────────────────────────

async def backup_scheduler() -> None:
    """
    Task asyncio que dispara os backups automáticos.
    Deve ser iniciada no lifespan do FastAPI.

    A cada ciclo:
      1. Lê as configurações atuais (daily_hour, flags de ativação).
      2. Dorme até o próximo daily_hour:00.
      3. Executa os tipos habilitados:
           - diário  → sempre que daily_enabled
           - semanal → se weekly_enabled E for segunda-feira (weekday 0)
           - mensal  → se monthly_enabled E for dia 1 do mês
    """
    log.info("Agendador de backup iniciado.")
    loop = asyncio.get_event_loop()

    while True:
        cfg        = load_backup_settings()
        daily_hour = int(cfg.get("daily_hour", 2))

        now      = datetime.now()
        next_run = now.replace(hour=daily_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        wait = (next_run - datetime.now()).total_seconds()
        log.info(
            "Próximo backup automático em %.0f s (%s).",
            wait, next_run.strftime("%Y-%m-%d %H:%M"),
        )
        await asyncio.sleep(wait)

        # Re-lê as configurações no momento da execução (podem ter mudado)
        cfg = load_backup_settings()
        now = datetime.now()

        if cfg.get("daily_enabled", True):
            result = await loop.run_in_executor(None, lambda: run_backup("diario"))
            if result["success"]:
                log.info("Backup diário concluído: %s", result.get("filename"))
            else:
                log.error("Backup diário falhou: %s", result.get("error"))

        if cfg.get("weekly_enabled", True) and now.weekday() == 0:
            result = await loop.run_in_executor(None, lambda: run_backup("semanal"))
            if result["success"]:
                log.info("Backup semanal concluído: %s", result.get("filename"))
            else:
                log.error("Backup semanal falhou: %s", result.get("error"))

        if cfg.get("monthly_enabled", False) and now.day == 1:
            result = await loop.run_in_executor(None, lambda: run_backup("mensal"))
            if result["success"]:
                log.info("Backup mensal concluído: %s", result.get("filename"))
            else:
                log.error("Backup mensal falhou: %s", result.get("error"))

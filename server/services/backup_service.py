"""
Serviço de backup do banco de dados PostgreSQL.

Usa pg_dump para gerar arquivos .sql na pasta de rede configurada em
settings.BACKUP_FOLDER.  O agendador interno (backup_scheduler) roda
como task asyncio em background — iniciado no lifespan do FastAPI.

Tipos de backup:
  diario   → backup_diario_YYYY-MM-DD.sql         (todo dia às BACKUP_DAILY_HOUR)
  semanal  → backup_semanal_YYYY_SXX.sql           (toda segunda-feira)
  manual   → backup_manual_YYYY-MM-DD_HH-MM-SS.sql (disparado pelo admin via API)

Rotação: mantém os BACKUP_RETENTION arquivos mais recentes de cada tipo.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from urllib.parse import urlparse

from ..config import settings

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


def _parse_db_url() -> dict:
    """Extrai host, port, user, password e dbname da DATABASE_URL."""
    parsed = urlparse(settings.DATABASE_URL)
    return {
        "host":     parsed.hostname or "localhost",
        "port":     str(parsed.port or 5432),
        "user":     parsed.username or "",
        "password": parsed.password or "",
        "dbname":   (parsed.path or "").lstrip("/"),
    }


# ── Rotação de arquivos ───────────────────────────────────────────────────────

def _rotate(folder: str, prefix: str) -> None:
    """Apaga os backups mais antigos quando passa do limite de retenção."""
    try:
        files = sorted(
            f for f in os.listdir(folder)
            if f.startswith(prefix) and f.endswith(".sql")
        )
        while len(files) > settings.BACKUP_RETENTION:
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
    if backup_type == "semanal":
        week = now.isocalendar()[1]
        filename = f"backup_semanal_{now.year}_S{week:02d}.sql"
        prefix   = "backup_semanal_"
    elif backup_type == "manual":
        filename = f"backup_manual_{now.strftime('%Y-%m-%d_%H-%M-%S')}.sql"
        prefix   = "backup_manual_"
    else:
        filename = f"backup_diario_{now.strftime('%Y-%m-%d')}.sql"
        prefix   = "backup_diario_"

    filepath = os.path.join(folder, filename)
    params   = _parse_db_url()

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

    _rotate(folder, prefix)
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

    Lógica:
      - Calcula o tempo até às BACKUP_DAILY_HOUR:00 do próximo dia.
      - Aguarda esse intervalo, então executa:
          - backup diário (sempre)
          - backup semanal (somente segunda-feira)
      - Repete indefinidamente.
    """
    log.info("Agendador de backup iniciado (backup diário às %02dh).", settings.BACKUP_DAILY_HOUR)
    loop = asyncio.get_event_loop()

    while True:
        now  = datetime.now()
        next_run = now.replace(
            hour=settings.BACKUP_DAILY_HOUR, minute=0, second=0, microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)

        wait = (next_run - datetime.now()).total_seconds()
        log.info("Próximo backup automático em %.0f segundos (%s).", wait, next_run.strftime("%Y-%m-%d %H:%M"))
        await asyncio.sleep(wait)

        # Backup diário
        result = await loop.run_in_executor(None, lambda: run_backup("diario"))
        if result["success"]:
            log.info("Backup diário concluído: %s", result.get("filename"))
        else:
            log.error("Backup diário falhou: %s", result.get("error"))

        # Backup semanal toda segunda-feira (weekday 0)
        if datetime.now().weekday() == 0:
            result = await loop.run_in_executor(None, lambda: run_backup("semanal"))
            if result["success"]:
                log.info("Backup semanal concluído: %s", result.get("filename"))
            else:
                log.error("Backup semanal falhou: %s", result.get("error"))

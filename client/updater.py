"""
Sistema de atualizações automáticas — Requisições Pinheiro.

Componentes:
  - UpdateChecker(QThread)    → consulta GitHub API silenciosamente
  - UpdateDownloader(QThread) → baixa o pacote com progresso
  - UpdateInstaller           → prepara e lança o update_helper.exe
  - finalize_pending_update() → chamado no startup para confirmar update anterior
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import json
from datetime import datetime
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal

from .version import CURRENT_VERSION


# ── Caminhos internos ─────────────────────────────────────────────────────────

def _get_app_dir() -> Path:
    """Diretório do executável (frozen) ou raiz do projeto (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_update_log_path() -> Path:
    return _get_app_dir() / "update.log"


def get_update_state_path() -> Path:
    return _get_app_dir() / "update_state.json"


# ── Helpers internos ──────────────────────────────────────────────────────────

def _parse_version(version: str) -> tuple[int, ...]:
    parts = [int(p) for p in re.findall(r"\d+", version or "0")]
    return tuple(parts or [0])


def _find_portable_asset(assets: list) -> dict | None:
    zip_assets = [a for a in assets if a.get("name", "").lower().endswith(".zip")]
    if not zip_assets:
        return None
    for marker in ("portable", "windows", "win64"):
        for a in zip_assets:
            if marker in a.get("name", "").lower():
                return a
    return zip_assets[0]


def _find_installer_asset(assets: list) -> dict | None:
    exe_assets = [a for a in assets if a.get("name", "").lower().endswith(".exe")]
    if not exe_assets:
        return None
    for marker in ("setup", "installer"):
        for a in exe_assets:
            if marker in a.get("name", "").lower():
                return a
    return exe_assets[0]


def _load_update_state() -> dict:
    state_path = get_update_state_path()
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_update_state(state: dict) -> None:
    state_path = get_update_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── finalize_pending_update ───────────────────────────────────────────────────

def finalize_pending_update() -> dict | None:
    """
    Verifica se há uma atualização pendente do startup anterior.
    Retorna um dict com 'status' e 'message', ou None se não houver nada.
    Deve ser chamada logo no início do main(), antes de mostrar qualquer janela.
    """
    state = _load_update_state()
    if not state:
        return None

    status = state.get("status")
    target_version = str(state.get("target_version", "")).strip()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Atualização aplicada com sucesso
    if status == "applied" and target_version == CURRENT_VERSION:
        state["status"] = "completed"
        state["completed_at"] = timestamp
        _save_update_state(state)
        return {
            "status": "completed",
            "message": f"Atualização concluída com sucesso para a versão {CURRENT_VERSION}.",
        }

    # Helper iniciou mas a versão não mudou (helper falhou ou foi interrompido)
    if status in {"pending", "applying"} and target_version and target_version != CURRENT_VERSION:
        state["status"] = "failed"
        state["failed_at"] = timestamp
        state.setdefault(
            "last_error",
            "A atualização anterior não concluiu antes da reabertura do aplicativo.",
        )
        _save_update_state(state)
        return {
            "status": "failed",
            "message": (
                f"A atualização para a versão {target_version} não foi concluída. "
                f"Consulte o log em {get_update_log_path()}."
            ),
        }

    # Falha já registrada mas ainda não notificada ao usuário nesta sessão
    if status == "failed" and not state.get("startup_notified_at"):
        state["startup_notified_at"] = timestamp
        _save_update_state(state)
        last_error = state.get("last_error") or "Falha ao aplicar a atualização."
        rollback_applied = state.get("rollback_applied")
        rollback_note = ""
        if rollback_applied is True:
            rollback_note = " O sistema foi restaurado a partir do backup."
        elif rollback_applied is False:
            rollback_note = " O rollback não pôde ser concluído automaticamente."
        return {
            "status": "failed",
            "message": (
                f"A atualização para a versão {target_version or 'informada'} falhou. "
                f"{last_error}.{rollback_note} Consulte o log em {get_update_log_path()}."
            ).replace("..", "."),
        }

    return None


# ── UpdateChecker ─────────────────────────────────────────────────────────────

class UpdateChecker(QThread):
    """Consulta o GitHub Releases em segundo plano e emite sinais com o resultado."""

    update_available = Signal(dict)
    no_update = Signal()
    error = Signal(str)

    RELEASES_URL = (
        "https://api.github.com/repos/JoaoLendengues/Requisicoes/releases/latest"
    )

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            response = requests.get(
                self.RELEASES_URL,
                timeout=15,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Requisicoes-Updater",
                },
            )
            response.raise_for_status()

            data = response.json()
            latest_version = (data.get("tag_name") or "0.0.0").lstrip("vV")

            if _parse_version(latest_version) <= _parse_version(CURRENT_VERSION):
                self.no_update.emit()
                return

            assets = data.get("assets", [])
            portable_asset = _find_portable_asset(assets)
            installer_asset = _find_installer_asset(assets)
            selected_asset = portable_asset or installer_asset

            if not selected_asset:
                self.error.emit(
                    "A release mais recente não possui instalador nem ZIP compatível."
                )
                return

            self.update_available.emit({
                "version": latest_version,
                "download_url": selected_asset.get("browser_download_url"),
                "asset_name": selected_asset.get("name", ""),
                "asset_kind": "portable" if selected_asset is portable_asset else "installer",
                "changelog": data.get("body", "Nova versão disponível."),
                "release_date": data.get("published_at", ""),
                "release_name": data.get("name", ""),
            })

        except Exception as exc:
            self.error.emit(str(exc))


# ── UpdateDownloader ──────────────────────────────────────────────────────────

class UpdateDownloader(QThread):
    """Baixa o pacote de atualização e emite progresso (0–100)."""

    progress = Signal(int)
    finished = Signal(str)   # caminho do arquivo baixado
    error = Signal(str)

    def __init__(self, download_url: str, asset_name: str = "", parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.asset_name = Path(asset_name).name or "update.bin"

    def run(self):
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="requisicoes_download_"))
            download_path = temp_dir / self.asset_name

            response = requests.get(
                self.download_url,
                stream=True,
                timeout=60,
                headers={"User-Agent": "Requisicoes-Updater"},
            )
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(download_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    file.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        self.progress.emit(int((downloaded / total_size) * 100))

            if total_size == 0:
                self.progress.emit(100)

            self.finished.emit(str(download_path))

        except Exception as exc:
            self.error.emit(str(exc))


# ── UpdateInstaller ───────────────────────────────────────────────────────────

class UpdateInstaller:
    """Prepara o ambiente e lança o update_helper.exe para aplicar a atualização."""

    PROTECTED_FILES = ("settings.json",)
    PROTECTED_DIRS  = ("backup", "logs", "temp_update", "__pycache__")

    # ── Utilidades de log ─────────────────────────────────────────────────────

    @staticmethod
    def _append_log(log_path: Path, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    # ── Caminho curto do Windows (lida com acentos no nome do usuário) ────────

    @staticmethod
    def _get_short_path(path: Path) -> str | None:
        try:
            import ctypes
            target = str(path)
            size = ctypes.windll.kernel32.GetShortPathNameW(target, None, 0)
            if not size:
                return None
            buf = ctypes.create_unicode_buffer(size)
            if ctypes.windll.kernel32.GetShortPathNameW(target, buf, size):
                return buf.value
        except Exception:
            pass
        return None

    @staticmethod
    def _to_cmd_safe_path(path: Path) -> str:
        """Retorna caminho ASCII seguro para usar em scripts PowerShell/CMD."""
        path = Path(path)
        try:
            resolved = path.resolve(strict=False)
        except Exception:
            resolved = path

        short = UpdateInstaller._get_short_path(resolved)
        if short:
            return short

        parent_short = UpdateInstaller._get_short_path(resolved.parent)
        if parent_short:
            return str(Path(parent_short) / resolved.name)

        return str(resolved)

    # ── Ponto de entrada público ──────────────────────────────────────────────

    @staticmethod
    def install_update(update_file: str) -> tuple[bool, str]:
        """
        Prepara e lança a atualização.
        Retorna (True, mensagem) em caso de sucesso ou (False, erro) em caso de falha.
        Deve ser chamado apenas no executável empacotado (sys.frozen == True).
        """
        try:
            if not getattr(sys, "frozen", False):
                return False, "A atualização automática funciona apenas no executável instalado."

            app_dir = Path(sys.executable).resolve().parent
            backup_dir = UpdateInstaller._create_backup(app_dir)

            log_path = get_update_log_path()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("", encoding="utf-8")
            UpdateInstaller._append_log(log_path, f"Iniciando atualização a partir de {update_file}.")

            update_path = Path(update_file)

            if update_path.suffix.lower() == ".exe":
                # Modo instalador: usa script PowerShell
                UpdateInstaller._append_log(log_path, "Modo: instalador (.exe).")
                script_path = UpdateInstaller._write_installer_script(
                    app_dir=app_dir,
                    installer_file=update_path,
                    process_id=os.getpid(),
                )
                UpdateInstaller._launch_script(script_path)
                UpdateInstaller._append_log(log_path, "Script PowerShell iniciado.")

            else:
                # Modo portátil: usa update_helper.exe
                UpdateInstaller._append_log(log_path, "Modo: portátil (.zip).")
                staging_dir = Path(tempfile.mkdtemp(prefix="requisicoes_stage_"))

                with zipfile.ZipFile(update_path, "r") as archive:
                    archive.extractall(staging_dir)
                UpdateInstaller._append_log(log_path, f"ZIP extraído para {staging_dir}.")

                payload_dir = UpdateInstaller._find_payload_dir(staging_dir)
                if payload_dir is None:
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    return False, "O ZIP da release não contém o build empacotado esperado."

                validation_error = UpdateInstaller._validate_payload(payload_dir)
                if validation_error:
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    return False, validation_error

                target_version = UpdateInstaller._extract_version(update_path.name)
                UpdateInstaller._append_log(log_path, f"Payload validado. Versão alvo: {target_version}.")

                UpdateInstaller._write_pending_state(
                    target_version=target_version,
                    backup_dir=backup_dir,
                    asset_name=update_path.name,
                )
                UpdateInstaller._launch_helper(
                    app_dir=app_dir,
                    staging_dir=staging_dir,
                    payload_dir=payload_dir,
                    backup_dir=Path(backup_dir),
                    process_id=os.getpid(),
                    target_version=target_version,
                )
                UpdateInstaller._append_log(log_path, "update_helper.exe iniciado.")

            return (
                True,
                "Atualização pronta. O sistema será fechado para concluir a instalação "
                f"e reabrirá automaticamente.\n\nBackup salvo em: {backup_dir}",
            )

        except Exception as exc:
            try:
                UpdateInstaller._append_log(get_update_log_path(), f"Falha inesperada: {exc}")
            except Exception:
                pass
            return False, str(exc)

    # ── Backup ────────────────────────────────────────────────────────────────

    @staticmethod
    def _create_backup(app_dir: Path) -> str:
        backup_dir = app_dir / "backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)
        for item_name in ("requisicoes.exe", "_internal", "update_helper.exe"):
            source = app_dir / item_name
            if not source.exists():
                continue
            dest = backup_dir / item_name
            if source.is_dir():
                shutil.copytree(source, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(source, dest)
        return str(backup_dir)

    # ── Localização e validação do payload ───────────────────────────────────

    @staticmethod
    def _find_payload_dir(staging_dir: Path) -> Path | None:
        for root, _, _ in os.walk(staging_dir):
            root_path = Path(root)
            if (root_path / "requisicoes.exe").exists() and (root_path / "_internal").exists():
                return root_path
        return None

    @staticmethod
    def _validate_payload(payload_dir: Path) -> str | None:
        required = ("requisicoes.exe", "_internal", "update_helper.exe")
        missing = [e for e in required if not (payload_dir / e).exists()]
        if missing:
            return (
                f"O pacote da atualização está incompleto. "
                f"Itens ausentes: {', '.join(missing)}."
            )
        return None

    @staticmethod
    def _extract_version(asset_name: str) -> str:
        match = re.search(r"v?(\d+(?:\.\d+)+)", asset_name or "")
        return match.group(1) if match else CURRENT_VERSION

    # ── Estado pendente ───────────────────────────────────────────────────────

    @staticmethod
    def _write_pending_state(target_version: str, backup_dir: str, asset_name: str) -> None:
        _save_update_state({
            "status": "pending",
            "from_version": CURRENT_VERSION,
            "target_version": target_version,
            "asset_name": asset_name,
            "backup_dir": backup_dir,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "startup_notified_at": None,
            "last_error": None,
            "rollback_applied": None,
        })

    # ── Lançamento do helper ──────────────────────────────────────────────────

    @staticmethod
    def _launch_helper(
        app_dir: Path,
        staging_dir: Path,
        payload_dir: Path,
        backup_dir: Path,
        process_id: int,
        target_version: str,
    ) -> None:
        payload_helper   = payload_dir / "update_helper.exe"
        installed_helper = app_dir / "update_helper.exe"
        helper_source    = payload_helper if payload_helper.exists() else installed_helper

        if not helper_source.exists():
            raise FileNotFoundError(
                f"update_helper.exe não encontrado em {installed_helper} "
                f"nem em {payload_helper}."
            )

        # Copia para diretório temporário para evitar que o próprio exe seja sobrescrito
        runtime_dir = Path(tempfile.mkdtemp(prefix="requisicoes_helper_"))
        helper_runtime = runtime_dir / "update_helper.exe"
        shutil.copy2(helper_source, helper_runtime)

        command = [
            str(helper_runtime),
            "--app-dir",       str(app_dir),
            "--payload-dir",   str(payload_dir),
            "--staging-dir",   str(staging_dir),
            "--backup-dir",    str(backup_dir),
            "--wait-pid",      str(process_id),
            "--target-version", str(target_version),
            "--state-path",    str(get_update_state_path()),
            "--log-path",      str(get_update_log_path()),
        ]

        flags = 0
        for flag in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
            flags |= getattr(subprocess, flag, 0)

        subprocess.Popen(command, creationflags=flags, close_fds=True)

    # ── Script PowerShell (modo instalador .exe) ──────────────────────────────

    @staticmethod
    def _launch_script(script_path: Path) -> None:
        flags = 0
        for flag in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
            flags |= getattr(subprocess, flag, 0)
        command = [
            "powershell.exe", "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(script_path),
        ]
        subprocess.Popen(command, creationflags=flags, close_fds=True)

    @staticmethod
    def _write_installer_script(
        app_dir: Path, installer_file: Path, process_id: int
    ) -> Path:
        script_path = Path(tempfile.gettempdir()) / (
            f"requisicoes_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ps1"
        )
        app_dir_safe       = UpdateInstaller._to_cmd_safe_path(app_dir)
        installer_file_safe = UpdateInstaller._to_cmd_safe_path(installer_file)

        lines = [
            "$ErrorActionPreference = 'Stop'",
            f"$AppDir = '{app_dir_safe}'",
            f"$InstallerFile = '{installer_file_safe}'",
            f"$ProcessIdToWait = {process_id}",
            "$LogFile = Join-Path $AppDir 'update.log'",
            "$InstallerDir = Split-Path -Parent $InstallerFile",
            "",
            "function Write-UpdateLog {",
            "    param([string]$Message)",
            "    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'",
            "    Add-Content -Path $LogFile -Value \"[$timestamp] $Message\" -Encoding UTF8",
            "}",
            "",
            "New-Item -ItemType Directory -Path $AppDir -Force | Out-Null",
            "Set-Content -Path $LogFile -Value '' -Encoding UTF8",
            "Write-UpdateLog 'Iniciando atualizacao pelo instalador'",
            "",
            "$waitCount = 0",
            "while (Get-Process -Id $ProcessIdToWait -ErrorAction SilentlyContinue) {",
            "    Start-Sleep -Milliseconds 500",
            "    $waitCount += 1",
            "    if ($waitCount -ge 40) {",
            "        Write-UpdateLog 'Timeout: forcando encerramento do processo principal'",
            "        Stop-Process -Id $ProcessIdToWait -Force -ErrorAction SilentlyContinue",
            "        Start-Sleep -Seconds 2",
            "        break",
            "    }",
            "}",
            "Write-UpdateLog 'Processo principal encerrado'",
            "Start-Sleep -Seconds 2",
            "",
            "Write-UpdateLog 'Executando instalador silencioso'",
            "$args = @('/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',",
            "           '/CLOSEAPPLICATIONS', '/FORCECLOSEAPPLICATIONS', '/LOG',",
            "           \"/DIR=$AppDir\")",
            "$proc = Start-Process -FilePath $InstallerFile -ArgumentList $args -PassThru -Wait -WindowStyle Hidden",
            "Write-UpdateLog \"Instalador encerrou com codigo $($proc.ExitCode)\"",
            "if ($proc.ExitCode -ne 0) { Write-UpdateLog 'Falha na instalacao'; exit 1 }",
            "",
            "if (-not (Test-Path (Join-Path $AppDir 'requisicoes.exe'))) {",
            "    Write-UpdateLog 'requisicoes.exe nao encontrado apos instalacao'; exit 1",
            "}",
            "",
            "Write-UpdateLog 'Reiniciando aplicativo'",
            "try {",
            "    Start-Process -FilePath (Join-Path $AppDir 'requisicoes.exe') -WorkingDirectory $AppDir",
            "    Write-UpdateLog 'Aplicativo reiniciado com sucesso'",
            "} catch {",
            "    Write-UpdateLog \"Falha ao reiniciar: $($_.Exception.Message)\"; exit 1",
            "}",
            "if (Test-Path $InstallerDir) {",
            "    Remove-Item $InstallerDir -Recurse -Force -ErrorAction SilentlyContinue",
            "}",
            "Remove-Item $PSCommandPath -Force -ErrorAction SilentlyContinue",
            "exit 0",
        ]

        script_path.write_text("\n".join(lines), encoding="utf-8-sig", newline="\r\n")
        return script_path

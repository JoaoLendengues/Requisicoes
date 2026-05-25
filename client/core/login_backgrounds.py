"""
Gerenciador de campanhas de fundo da tela de login.

Estrutura do config.json em bg_folder (caminho configurável em settings.json,
padrão: Z:\\REQUISIÇÕES (VENDAS)\\login_backgrounds):
[
  {
    "id": 1,
    "name": "Natal 2025",
    "start": "2025-12-15",
    "end":   "2025-12-26",
    "image": "1_natal_2025.jpg"
  },
  ...
]

Quando múltiplas campanhas estão ativas no mesmo dia, o sistema alterna
entre elas em rodízio a cada abertura do app (round-robin por ID,
persistido em _state.json).

A pasta fica em rede (Z:\\) para que todas as máquinas compartilhem as
mesmas campanhas automaticamente. O caminho pode ser customizado via
settings.json ("bg_folder").
"""
import json
import os
import shutil
from datetime import date

from .resolution import res


def _bg_dir() -> str:
    """Retorna o caminho da pasta de backgrounds (lido do settings a cada chamada)."""
    return res.bg_folder


def _config_path() -> str:
    return os.path.join(_bg_dir(), "config.json")


def _state_path() -> str:
    return os.path.join(_bg_dir(), "_state.json")


def _ensure_dir() -> None:
    os.makedirs(_bg_dir(), exist_ok=True)


# ── Leitura / escrita de campanhas ────────────────────────────────────────────

def load_all() -> list[dict]:
    """Lê todas as campanhas do config.json. Retorna lista vazia se não houver."""
    try:
        with open(_config_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_all(campaigns: list[dict]) -> None:
    """Grava a lista de campanhas no config.json."""
    _ensure_dir()
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(campaigns, f, indent=2, ensure_ascii=False)


# ── Estado de rotação ─────────────────────────────────────────────────────────

def _read_state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_state(data: dict) -> None:
    _ensure_dir()
    with open(_state_path(), "w", encoding="utf-8") as f:
        json.dump(data, f)


# ── Campanha ativa com rodízio ────────────────────────────────────────────────

def get_active_background() -> str | None:
    """
    Retorna o caminho absoluto da imagem a exibir hoje, ou None.

    Comportamento quando múltiplas campanhas cobrem a data atual:
      - As campanhas ativas são ordenadas por ID.
      - A cada abertura do app é escolhida a próxima na fila (round-robin).
      - O último ID exibido fica gravado em _state.json.
    """
    today = date.today().isoformat()

    bg = _bg_dir()
    active = [
        c for c in load_all()
        if c.get("start", "") <= today <= c.get("end", "")
        and c.get("image")
        and os.path.isfile(os.path.join(bg, c["image"]))
    ]

    if not active:
        return None

    # Ordena para que o rodízio seja determinístico
    active.sort(key=lambda c: c.get("id", 0))

    if len(active) == 1:
        # Não precisa persistir estado para uma única campanha
        return os.path.join(bg, active[0]["image"])

    # Round-robin: próxima após o último ID exibido
    last_id   = _read_state().get("last_shown_id", -1)
    next_camp = next((c for c in active if c["id"] > last_id), active[0])

    _write_state({"last_shown_id": next_camp["id"]})
    return os.path.join(bg, next_camp["image"])


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_campaign(name: str, start: str, end: str, src_path: str) -> dict:
    """
    Copia a imagem para a pasta de backgrounds e adiciona a campanha.
    Retorna o dict da campanha criada.
    """
    _ensure_dir()
    campaigns = load_all()
    new_id    = max((c.get("id", 0) for c in campaigns), default=0) + 1
    ext       = os.path.splitext(src_path)[1].lower() or ".jpg"
    slug      = "".join(c if c.isalnum() else "_" for c in name.lower())[:40]
    filename  = f"{new_id}_{slug}{ext}"
    dest      = os.path.join(_bg_dir(), filename)
    shutil.copy2(src_path, dest)
    campaign = {
        "id":    new_id,
        "name":  name,
        "start": start,
        "end":   end,
        "image": filename,
    }
    campaigns.append(campaign)
    save_all(campaigns)
    return campaign


def remove_campaign(campaign_id: int) -> None:
    """
    Remove a campanha pelo ID da lista de config.
    O arquivo de imagem NÃO é apagado (pode ser reutilizado).
    """
    campaigns = [c for c in load_all() if c.get("id") != campaign_id]
    save_all(campaigns)


# ── Utilitários de display ────────────────────────────────────────────────────

def campaign_status(start: str, end: str) -> str:
    """Retorna 'Ativa', 'Programada' ou 'Expirada' com base na data de hoje."""
    today = date.today().isoformat()
    if today < start:
        return "Programada"
    if today > end:
        return "Expirada"
    return "Ativa"


def fmt_date(iso: str) -> str:
    """Converte 'YYYY-MM-DD' para 'DD/MM/YYYY'. Retorna a string original em erro."""
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso

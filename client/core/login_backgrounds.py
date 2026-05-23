"""
Gerenciador de campanhas de fundo da tela de login.

Estrutura do config.json em assets/login_backgrounds/:
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

A campanha ativa é a primeira cujo intervalo [start, end] cobre a data de hoje.
Se houver sobreposição, a mais recente (maior id) tem precedência.
"""
import json
import os
import shutil
from datetime import date

_BG_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "assets", "login_backgrounds")
)
_CONFIG = os.path.join(_BG_DIR, "config.json")


def _ensure_dir() -> None:
    os.makedirs(_BG_DIR, exist_ok=True)


# ── Leitura / escrita ─────────────────────────────────────────────────────────

def load_all() -> list[dict]:
    """Lê todas as campanhas do config.json. Retorna lista vazia se não houver."""
    try:
        with open(_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_all(campaigns: list[dict]) -> None:
    """Grava a lista de campanhas no config.json."""
    _ensure_dir()
    with open(_CONFIG, "w", encoding="utf-8") as f:
        json.dump(campaigns, f, indent=2, ensure_ascii=False)


# ── Campanha ativa ────────────────────────────────────────────────────────────

def get_active_background() -> str | None:
    """
    Retorna o caminho absoluto da imagem da campanha ativa para hoje,
    ou None se não houver campanha ativa (ou arquivo não existir).

    Se múltiplas campanhas cobrem hoje, usa a de maior id.
    """
    today = date.today().isoformat()   # ex.: "2025-12-25"
    active = None
    for campaign in load_all():
        start = campaign.get("start", "")
        end   = campaign.get("end",   "")
        img   = campaign.get("image", "")
        if start <= today <= end and img:
            path = os.path.join(_BG_DIR, img)
            if os.path.isfile(path):
                # maior id tem precedência
                if active is None or campaign.get("id", 0) > active[0]:
                    active = (campaign.get("id", 0), path)
    return active[1] if active else None


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_campaign(name: str, start: str, end: str, src_path: str) -> dict:
    """
    Copia a imagem para a pasta de backgrounds e adiciona a campanha.
    Retorna o dict da campanha criada.
    """
    _ensure_dir()
    campaigns = load_all()
    new_id = max((c.get("id", 0) for c in campaigns), default=0) + 1
    ext    = os.path.splitext(src_path)[1].lower() or ".jpg"
    slug   = "".join(c if c.isalnum() else "_" for c in name.lower())[:40]
    filename = f"{new_id}_{slug}{ext}"
    dest = os.path.join(_BG_DIR, filename)
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

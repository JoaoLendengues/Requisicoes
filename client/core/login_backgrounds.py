"""
Gerenciador de imagens de fundo da tela de login.

Funcionamento:
  - Coloque imagens (PNG, JPG, JPEG, BMP, WEBP) na pasta configurada em
    settings.json ("bg_folder").  Não é necessário nenhum config.json.
  - A cada abertura do app, o sistema exibe a próxima imagem em rodízio
    (round-robin pelo nome do arquivo, persistido em _state.json).
  - A pasta pode ser local ou de rede (ex.: Z:\\REQUISIÇÕES (VENDAS)\\login_backgrounds).
    Todos os computadores que apontarem para o mesmo caminho compartilham
    automaticamente as mesmas imagens.
"""
import json
import os

from .resolution import res

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_STATE_FILENAME   = "_state.json"


def _bg_dir() -> str:
    """Retorna o caminho da pasta de backgrounds (lido do settings a cada chamada)."""
    return res.bg_folder


def _state_path() -> str:
    return os.path.join(_bg_dir(), _STATE_FILENAME)


# ── Leitura de imagens ────────────────────────────────────────────────────────

def load_all() -> list[str]:
    """
    Retorna a lista de nomes de arquivo de imagem encontrados na pasta,
    ordenados alfabeticamente. Retorna lista vazia se a pasta não existir.
    """
    bg = _bg_dir()
    if not os.path.isdir(bg):
        return []
    return sorted(
        f for f in os.listdir(bg)
        if os.path.splitext(f.lower())[1] in _IMAGE_EXTENSIONS
        and f != _STATE_FILENAME
    )


# ── Estado de rotação ─────────────────────────────────────────────────────────

def _read_state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_state(data: dict) -> None:
    try:
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


# ── Imagem ativa com rodízio ──────────────────────────────────────────────────

def get_active_background() -> str | None:
    """
    Retorna o caminho absoluto da próxima imagem a exibir, ou None se não
    houver imagens na pasta.

    A cada chamada avança uma posição no rodízio (round-robin alfabético).
    O último arquivo exibido fica gravado em _state.json dentro da própria pasta.
    """
    bg      = _bg_dir()
    images  = load_all()

    if not images:
        return None

    if len(images) == 1:
        return os.path.join(bg, images[0])

    # Round-robin pelo nome do último arquivo exibido
    last = _read_state().get("last_shown", "")
    try:
        last_idx = images.index(last)
        next_idx = (last_idx + 1) % len(images)
    except ValueError:
        next_idx = 0

    _write_state({"last_shown": images[next_idx]})
    return os.path.join(bg, images[next_idx])

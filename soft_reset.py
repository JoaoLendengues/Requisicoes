"""
Soft Reset — Requisições App
============================
PRESERVA: clients, users, operators, production_machines, products
RESETA  : requisitions e toda a cadeia, notifications, audit_log,
          login_attempts, feedbacks, deliveries
BONUS   : remove chaves guide_shown_* do settings.json local

Rodar APENAS no ambiente de dev / pré-produção, antes de ir ao ar.

Uso:
    python soft_reset.py
    python soft_reset.py --dry-run     (mostra contagens, não apaga nada)
"""
from __future__ import annotations

import json
import os
import re
import sys

import psycopg2
import psycopg2.extras

# ── Conexão ─────────────────────────────────────────────────────────────────
DB_URL = "postgresql://tipinheiro:Pinheiro123@10.1.1.151:5432/requisicoes"

# ── Caminho do settings.json ─────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(_HERE, "client", "settings.json")

DRY_RUN = "--dry-run" in sys.argv

# ── SQL de contagem antes do reset ──────────────────────────────────────────
COUNT_QUERIES: list[tuple[str, str]] = [
    ("requisitions",               "SELECT COUNT(*) FROM requisitions"),
    ("requisition_items",          "SELECT COUNT(*) FROM requisition_items"),
    ("canvas_data",                "SELECT COUNT(*) FROM canvas_data"),
    ("requisition_production_splits", "SELECT COUNT(*) FROM requisition_production_splits"),
    ("status_history",             "SELECT COUNT(*) FROM status_history"),
    ("notifications",              "SELECT COUNT(*) FROM notifications"),
    ("audit_log",                  "SELECT COUNT(*) FROM audit_log"),
    ("login_attempts",             "SELECT COUNT(*) FROM login_attempts"),
    ("feedbacks",                  "SELECT COUNT(*) FROM feedbacks"),
    ("feedback_reactions",         "SELECT COUNT(*) FROM feedback_reactions"),
    ("feedback_reads",             "SELECT COUNT(*) FROM feedback_reads"),
    ("deliveries",                 "SELECT COUNT(*) FROM deliveries"),
]

PRESERVED_QUERIES: list[tuple[str, str]] = [
    ("clients",                    "SELECT COUNT(*) FROM clients"),
    ("users",                      "SELECT COUNT(*) FROM users"),
    ("operators",                  "SELECT COUNT(*) FROM operators"),
    ("production_machines",        "SELECT COUNT(*) FROM production_machines"),
    ("products",                   "SELECT COUNT(*) FROM products"),
]

# ── SQL de reset ──────────────────────────────────────────────────────────────
RESET_SQL = """
-- Desabilita FK checks temporariamente via TRUNCATE CASCADE
-- Ordem: primeiro as filhas, depois as mães — CASCADE cuida do resto

TRUNCATE TABLE
    deliveries,
    feedback_reads,
    feedback_reactions,
    feedbacks,
    notifications,
    audit_log,
    login_attempts,
    status_history,
    requisition_items,
    canvas_data,
    requisition_production_splits,
    requisitions
RESTART IDENTITY CASCADE;

-- Limpa last_login_at — usuários terão aparência de "nunca logaram"
UPDATE users SET last_login_at = NULL;
"""


def _count(cur, queries: list[tuple[str, str]]) -> dict[str, int]:
    result = {}
    for name, sql in queries:
        cur.execute(sql)
        result[name] = cur.fetchone()[0]
    return result


def _print_table(title: str, counts: dict[str, int], prefix: str = "  ") -> None:
    print(f"\n{title}")
    for name, n in counts.items():
        print(f"{prefix}{name:<40} {n:>8,}")


def reset_database() -> None:
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    print("Conectado ao banco:", DB_URL.split("@")[1])

    before = _count(cur, COUNT_QUERIES)
    preserved = _count(cur, PRESERVED_QUERIES)

    _print_table(">>> SERÁ RESETADO:", before)
    _print_table(">>> SERÁ PRESERVADO (intocado):", preserved)

    if DRY_RUN:
        print("\n[DRY-RUN] Nenhuma alteração feita.")
        cur.close()
        conn.close()
        return

    print("\nExecutando reset...")
    cur.execute(RESET_SQL)
    conn.commit()

    after = _count(cur, COUNT_QUERIES)
    _print_table(">>> APÓS RESET (deve ser tudo 0):", after)

    preserved_after = _count(cur, PRESERVED_QUERIES)
    _print_table(">>> PRESERVADO (deve ser igual ao antes):", preserved_after)

    cur.close()
    conn.close()
    print("\n[OK] Banco resetado com sucesso.")


def reset_guide_flags() -> None:
    if not os.path.exists(SETTINGS_FILE):
        print(f"\n[AVISO] settings.json não encontrado em: {SETTINGS_FILE}")
        print("        Localize o arquivo em cada máquina cliente e remova")
        print("        manualmente as chaves que começam com 'guide_shown_'.")
        return

    with open(SETTINGS_FILE, encoding="utf-8") as f:
        data: dict = json.load(f)

    guide_keys = [k for k in data if k.startswith("guide_shown_")]
    if not guide_keys:
        print("\n[INFO] Nenhuma chave guide_shown_* encontrada em settings.json.")
        return

    if DRY_RUN:
        print(f"\n[DRY-RUN] Removeria {len(guide_keys)} chaves do settings.json:")
        for k in sorted(guide_keys):
            print(f"  - {k}")
        return

    for k in guide_keys:
        del data[k]

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] {len(guide_keys)} chaves guide_shown_* removidas de settings.json.")
    print("     O Guia Rápido vai rodar no próximo login em CADA PERFIL desta máquina.")


def main() -> None:
    mode = "DRY-RUN" if DRY_RUN else "REAL"
    print(f"{'=' * 60}")
    print(f"  SOFT RESET — Requisições App  [{mode}]")
    print(f"{'=' * 60}")

    if not DRY_RUN:
        confirm = input(
            "\nATENÇÃO: esta operação apaga TODOS os pedidos, histórico e logs.\n"
            "         Clientes, usuários, máquinas e produtos são PRESERVADOS.\n\n"
            "         Digite CONFIRMAR para prosseguir: "
        ).strip()
        if confirm != "CONFIRMAR":
            print("Operação cancelada.")
            sys.exit(0)

    reset_database()
    reset_guide_flags()

    if not DRY_RUN:
        print(f"\n{'=' * 60}")
        print("  Reset concluído.")
        print()
        print("  PRÓXIMOS PASSOS:")
        print("  1. Reinicie o servidor FastAPI (se estiver rodando)")
        print("  2. Para resetar o Guia Rápido nas OUTRAS máquinas,")
        print("     copie o settings.json limpo ou remova as chaves")
        print("     guide_shown_* do settings.json de cada usuário.")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

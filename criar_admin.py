"""
Cria (ou promove) um usuário administrador no banco PostgreSQL.
Execute na raiz do projeto:
    .venv\Scripts\python criar_admin.py

Não requer nenhum admin existente — acessa o banco diretamente.
"""

import sys
import bcrypt
import psycopg2

# ── Configuração ──────────────────────────────────────────────────────────────
PG_DSN = "postgresql://tipinheiro:Pinheiro123@localhost:5432/requisicoes"

# ── Dados do novo administrador ───────────────────────────────────────────────
ADMIN_CODE  = "ADMIN"          # código de login
ADMIN_NAME  = "Administrador"  # nome exibido
ADMIN_EMAIL = "admin@pinheiro.local"
ADMIN_PASS  = "admin123"       # senha (altere aqui ou será solicitada abaixo)

# ─────────────────────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    normalized = password.strip().casefold()
    return bcrypt.hashpw(normalized.encode(), bcrypt.gensalt()).decode()


def _ensure_admin_enum(cur):
    """Garante que 'admin' existe como valor válido no enum do PostgreSQL."""
    cur.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'role'
              AND e.enumlabel = 'admin'
        )
    """)
    if not cur.fetchone()[0]:
        print("[ENUM] Adicionando 'admin' ao tipo enum 'role' no PostgreSQL...")
        cur.execute("ALTER TYPE role ADD VALUE 'admin'")
        print("[ENUM] Valor 'admin' adicionado com sucesso.")
    else:
        print("[ENUM] Valor 'admin' já existe no enum.")


def main():
    print("=" * 60)
    print("  CRIAÇÃO DE USUÁRIO ADMINISTRADOR")
    print("=" * 60)

    # Permite sobrescrever a senha pelo terminal
    senha = ADMIN_PASS
    resp = input(f"\nSenha para '{ADMIN_CODE}' [Enter = '{ADMIN_PASS}']: ").strip()
    if resp:
        senha = resp

    hashed = _hash(senha)

    try:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = False
        cur = conn.cursor()

        # 1. Garante que o enum tem o valor 'admin'
        # ALTER TYPE não pode rodar dentro de uma transação explícita
        conn.autocommit = True
        _ensure_admin_enum(cur)
        conn.autocommit = False

        # 2. Verifica se já existe usuário com esse código
        cur.execute("SELECT id, role FROM users WHERE code = %s", (ADMIN_CODE,))
        row = cur.fetchone()

        if row:
            user_id, role_atual = row
            if role_atual == "admin":
                print(f"\n[OK] Usuário '{ADMIN_CODE}' já é administrador (id={user_id}). Nada a fazer.")
            else:
                cur.execute(
                    "UPDATE users SET role = 'admin', is_active = TRUE WHERE id = %s",
                    (user_id,),
                )
                conn.commit()
                print(f"\n[OK] Usuário '{ADMIN_CODE}' (id={user_id}) promovido para ADMIN.")
        else:
            # Verifica e-mail duplicado
            cur.execute("SELECT id FROM users WHERE email = %s", (ADMIN_EMAIL,))
            if cur.fetchone():
                email_auto = f"{ADMIN_CODE.lower()}@usuarios.local"
                print(f"[AVISO] E-mail '{ADMIN_EMAIL}' já em uso. Usando '{email_auto}'.")
            else:
                email_auto = ADMIN_EMAIL

            cur.execute("""
                INSERT INTO users
                    (code, name, email, hashed_password, role,
                     must_change_password, is_active, created_at, updated_at)
                VALUES
                    (%s, %s, %s, %s, 'admin',
                     FALSE, TRUE, NOW(), NOW())
            """, (ADMIN_CODE, ADMIN_NAME, email_auto, hashed))
            conn.commit()
            print(f"\n[OK] Administrador criado com sucesso!")
            print(f"     Código : {ADMIN_CODE}")
            print(f"     Nome   : {ADMIN_NAME}")
            print(f"     E-mail : {email_auto}")
            print(f"     Senha  : {senha}")
            print(f"\n  ⚠  Altere a senha após o primeiro login!")

        cur.close()
        conn.close()

    except Exception as exc:
        print(f"\n[ERRO] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

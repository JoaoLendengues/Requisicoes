# Documentação Técnica — Requisições App
**Ferragens Pinheiro** | Versão 1.1.0

---

## Sumário

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Stack tecnológica](#2-stack-tecnológica)
3. [Estrutura de pastas](#3-estrutura-de-pastas)
4. [Configuração do ambiente](#4-configuração-do-ambiente)
5. [Rodando o projeto](#5-rodando-o-projeto)
6. [Banco de dados](#6-banco-de-dados)
7. [Autenticação e perfis](#7-autenticação-e-perfis)
8. [API REST — Endpoints](#8-api-rest--endpoints)
9. [Sistema de notificações (SSE)](#9-sistema-de-notificações-sse)
10. [Geração de PDF](#10-geração-de-pdf)
11. [Editor de desenho (canvas)](#11-editor-de-desenho-canvas)
12. [Sistema de atualizações automáticas](#12-sistema-de-atualizações-automáticas)
13. [Backup automático](#13-backup-automático)
14. [Gerando o executável](#14-gerando-o-executável)
15. [CI/CD — GitHub Actions](#15-cicd--github-actions)
16. [Variáveis de ambiente](#16-variáveis-de-ambiente)

---

## 1. Visão geral da arquitetura

O sistema é composto por dois processos independentes que se comunicam via HTTP/SSE:

```
┌─────────────────────────────┐        HTTP / SSE        ┌──────────────────────────┐
│     Cliente Desktop          │ ◄──────────────────────► │     Servidor FastAPI      │
│     (PySide6 / Python)        │    porta 5000 (rede)     │     (Python / uvicorn)    │
│                               │                          │                           │
│  • Interface gráfica Qt6      │                          │  • API REST               │
│  • Lógica de negócio local    │                          │  • Autenticação JWT       │
│  • Editor de desenho          │                          │  • Notificações SSE       │
│  • Geração de PDF             │                          │  • Backup automático      │
│  • Auto-update                │                          │  • Audit log              │
└─────────────────────────────┘                          └──────────┬───────────────┘
                                                                     │
                                                          ┌──────────▼───────────────┐
                                                          │     PostgreSQL             │
                                                          │     (porta 5432)           │
                                                          └──────────────────────────┘
```

### Premissas de implantação

- **Servidor**: máquina Windows na rede local (`10.1.1.151:5000`)
- **Clientes**: estações Windows com o executável instalado
- **Banco**: PostgreSQL no mesmo servidor ou máquina dedicada
- **PDFs**: gravados em pasta de rede compartilhada (`Z:\REQUISIÇÕES (VENDAS)\PDF`)

---

## 2. Stack tecnológica

### Backend (`server/`)

| Tecnologia | Versão | Função |
|-----------|--------|--------|
| Python | 3.11+ | Linguagem base |
| FastAPI | 0.136.1 | Framework web / API REST |
| SQLAlchemy | 2.0.49 | ORM |
| PostgreSQL | 12+ | Banco de dados de produção |
| Uvicorn | 0.47.0 | Servidor ASGI |
| Pydantic | 2.13.4 | Validação de schemas |
| python-jose | 3.5.0 | Tokens JWT |
| bcrypt | 5.0.0 | Hash de senhas |
| APScheduler | — | Agendamento de backup |
| httpx | 0.28.1 | Requisições HTTP assíncronas |

### Frontend (`client/`)

| Tecnologia | Versão | Função |
|-----------|--------|--------|
| Python | 3.11+ | Linguagem base |
| PySide6 | 6.11.1 | Interface gráfica (Qt6) |
| httpx | 0.28.1 | Cliente HTTP com SSE |
| ReportLab | 4.0.0 | Geração de PDF |
| Pillow | 12.2.0 | Processamento de imagens |
| pandas | 3.0.3 | Importação de dados (Excel/CSV) |
| openpyxl | 3.1.5 | Leitura de .xlsx |
| odfpy | 1.4.1 | Leitura de .ods |
| qrcode | 8.2 | Geração de QR Code no PDF |
| PyInstaller | — | Empacotamento do executável |
| Inno Setup | 6 | Gerador do instalador Windows |

---

## 3. Estrutura de pastas

```
requisicoes/
│
├── client/                         # Aplicação desktop
│   ├── api/
│   │   └── client.py               # Cliente HTTP (httpx wrapper)
│   ├── assets/
│   │   ├── fonts/                  # Fonte Inter
│   │   └── icons/                  # Ícones da sidebar e app
│   ├── core/
│   │   ├── session.py              # Singleton de sessão do usuário
│   │   ├── theme.py                # Tokens de cor (light/dark)
│   │   ├── resolution.py           # Escala adaptativa por resolução
│   │   ├── login_backgrounds.py    # Gerencia fundos do login
│   │   └── pdf_folders.py          # Roteamento de pasta de PDFs
│   ├── services/
│   │   ├── pdf_generator.py        # Geração de PDF (ReportLab)
│   │   ├── notification_listener.py # Listener SSE
│   │   ├── client_importer.py      # Importador de clientes
│   │   ├── product_importer.py     # Importador de produtos
│   │   └── user_importer.py        # Importador de usuários
│   ├── views/                      # Telas (QWidget/QDialog)
│   ├── widgets/                    # Componentes reutilizáveis
│   ├── main.py                     # Ponto de entrada
│   ├── updater.py                  # Lógica de auto-update
│   ├── update_helper.py            # Helper standalone de update
│   └── version.py                  # CURRENT_VERSION (atualizado pelo CI)
│
├── server/                         # API REST
│   ├── models/                     # Modelos SQLAlchemy (tabelas)
│   ├── routers/                    # Endpoints por recurso
│   ├── schemas/                    # Pydantic schemas (request/response)
│   ├── services/                   # Lógica de negócio
│   ├── config.py                   # Pydantic Settings (.env)
│   ├── database.py                 # Engine + session factory
│   ├── dependencies.py             # get_current_user, get_db
│   └── main.py                     # App FastAPI + lifespan + migrations
│
├── docs/                           # Documentação
├── tests/                          # Testes unitários
│
├── .github/workflows/
│   └── build_release.yml           # CI/CD: build + release automático
│
├── .env                            # Variáveis de ambiente (git-ignored)
├── .env.example                    # Template comentado
├── requirements.txt                # Dependências completas
├── requisicoes.spec                # PyInstaller spec do cliente
├── update_helper.spec              # PyInstaller spec do helper
├── installer_script.iss            # Inno Setup script
├── run.py                          # Entrypoint do servidor
├── run_client.py                   # Entrypoint do cliente (dev)
├── criar_admin.py                  # Seed: cria usuário admin
└── migrate_to_pg.py                # Migração SQLite → PostgreSQL
```

---

## 4. Configuração do ambiente

### Pré-requisitos

- Python 3.11+
- PostgreSQL 12+
- Git

### Instalação

```bash
# 1. Clonar o repositório
git clone https://github.com/JoaoLendengues/Requisicoes.git
cd Requisicoes

# 2. Criar e ativar o virtualenv
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar variáveis de ambiente
copy .env.example .env
# Edite o .env com os dados do seu banco e configurações

# 5. Criar o banco de dados
# (As tabelas são criadas automaticamente no primeiro start do servidor)

# 6. Criar o usuário admin inicial
python criar_admin.py
```

### Migração de SQLite para PostgreSQL (se necessário)

```bash
python migrate_to_pg.py
```

---

## 5. Rodando o projeto

### Servidor

```bash
# Via script (Windows)
INICIAR_SERVIDOR.bat

# Ou diretamente
.venv\Scripts\python.exe run.py
```

O servidor sobe em `http://0.0.0.0:5000`. A documentação interativa da API fica em `http://localhost:5000/docs`.

> **Importante:** Use apenas 1 worker Uvicorn. O sistema de notificações SSE usa `asyncio.Queue` em memória — múltiplos workers quebrariam a entrega de notificações.

### Cliente (modo desenvolvimento)

```bash
# Via script (Windows)
INICIAR_CLIENTE.bat

# Ou diretamente
.venv\Scripts\python.exe run_client.py
```

---

## 6. Banco de dados

### Migrations

As migrations são aplicadas automaticamente no startup do servidor via `lifespan` do FastAPI. Não há ferramenta externa como Alembic — as alterações de schema são feitas inline no `server/main.py`.

### Tabelas principais

| Tabela | Descrição |
|--------|-----------|
| `users` | Usuários do sistema (código, senha bcrypt, role, setor) |
| `clients` | Clientes com CNPJ, razão social, endereço |
| `products` | Produtos (código, nome, ativo) |
| `requisitions` | Requisições (status, vendedor, cliente, número do pedido) |
| `requisition_items` | Itens de uma requisição (produto, qtd, preço) |
| `canvas_data` | Desenho JSON associado a uma requisição (1:1) |
| `status_history` | Histórico de mudanças de status |
| `notifications` | Notificações por usuário |
| `production_machines` | Máquinas de produção |
| `feedbacks` | Feedbacks enviados pelos usuários |
| `audit_logs` | Log de ações por usuário |
| `login_attempts` | Tentativas de login (sucesso/falha) |

### Índices de performance (PostgreSQL)

```sql
-- Busca fuzzy por nome/CNPJ de clientes (trigram)
CREATE INDEX idx_clients_name_trgm  ON clients USING gin (name  gin_trgm_ops);
CREATE INDEX idx_clients_code_trgm  ON clients USING gin (code  gin_trgm_ops);
CREATE INDEX idx_clients_cnpj_trgm  ON clients USING gin (cnpj  gin_trgm_ops);

-- Requisições por status, vendedor e cliente
CREATE INDEX idx_requisitions_status    ON requisitions (status);
CREATE INDEX idx_requisitions_vendor_id ON requisitions (vendor_id);
CREATE INDEX idx_requisitions_client_id ON requisitions (client_id);

-- Notificações não lidas por usuário
CREATE INDEX idx_notifications_user_unread ON notifications (user_id, read);
```

---

## 7. Autenticação e perfis

### Fluxo de autenticação

```
POST /auth/login
  { code: "1001", password: "senha" }
        │
        ▼
  authenticate_user() — bcrypt.verify
        │
        ▼
  create_access_token() — JWT RS256
        │
        ▼
  { access_token: "eyJ...", token_type: "bearer" }
        │
        ▼
  Cliente armazena em UserSession (singleton)
  Todas as requisições: Authorization: Bearer {token}
```

### Roles (perfis)

```python
class Role(str, Enum):
    admin     = "admin"
    gerente   = "gerente"
    vendedor  = "vendedor"
    producao  = "producao"   # A&R
    industria = "industria"
    entrega   = "entrega"
```

### Propriedades de acesso (client/core/session.py)

```python
session.is_admin                 # Apenas admin
session.is_manager_or_admin      # Admin ou gerente
session.is_view_only             # Producao, industria, entrega
session.is_production_team       # Producao, industria, entrega
session.can_edit_requisitions    # Vendedor, gerente, admin
```

### Token

- Algoritmo: HS256
- Expiração: 480 minutos (8 horas), configurável via `ACCESS_TOKEN_EXPIRE_MINUTES`
- Payload: `{ sub: user_id, role: role, exp: ... }`

---

## 8. API REST — Endpoints

Base URL: `http://10.1.1.151:5000`

### Autenticação

| Método | Endpoint | Autenticação | Descrição |
|--------|----------|-------------|-----------|
| POST | `/auth/login` | Não | Login com código e senha |
| POST | `/auth/first-access` | Não | Definir senha no primeiro acesso |
| POST | `/auth/change-password` | Bearer | Alterar senha |
| GET | `/auth/profile` | Bearer | Dados do usuário logado |

### Usuários

| Método | Endpoint | Role | Descrição |
|--------|----------|------|-----------|
| GET | `/users` | Admin, Gerente | Listar usuários |
| POST | `/users` | Admin | Criar usuário |
| PUT | `/users/{id}` | Admin | Atualizar usuário |
| DELETE | `/users/{id}` | Admin | Remover usuário |
| POST | `/users/import` | Admin | Importar usuários (CSV/Excel) |

### Clientes

| Método | Endpoint | Autenticação | Descrição |
|--------|----------|-------------|-----------|
| GET | `/clients` | Bearer | Buscar clientes (suporta `q=` para busca fuzzy) |
| POST | `/clients` | Bearer | Criar cliente |
| PUT | `/clients/{id}` | Bearer | Atualizar cliente |
| POST | `/clients/import/bulk` | Bearer | Importar clientes em lote |

### Requisições

| Método | Endpoint | Autenticação | Descrição |
|--------|----------|-------------|-----------|
| GET | `/requisitions` | Bearer | Listar requisições (filtros: status, vendor, date) |
| POST | `/requisitions` | Bearer | Criar requisição |
| GET | `/requisitions/{id}` | Bearer | Detalhes de uma requisição |
| PUT | `/requisitions/{id}` | Bearer | Atualizar requisição |
| PATCH | `/requisitions/{id}/status` | Bearer | Alterar status |
| DELETE | `/requisitions/{id}` | Bearer | Cancelar requisição |

### Notificações

| Método | Endpoint | Autenticação | Descrição |
|--------|----------|-------------|-----------|
| GET | `/notifications` | Bearer | Listar notificações do usuário |
| PATCH | `/notifications/{id}/read` | Bearer | Marcar como lida |
| GET | `/notifications/stream` | Bearer | Stream SSE em tempo real |

---

## 9. Sistema de notificações (SSE)

### Arquitetura

```
Evento no servidor (ex: nova requisição)
        │
        ▼
notification_service.notify(user_id, message)
        │
        ▼
asyncio.Queue por user_id (em memória)
        │
        ▼
GET /notifications/stream  ──► Client SSE listener
        │
        ▼
notification_listener.py recebe evento
        │
        ▼
Emite sinal Qt → Toast + Badge atualizado
```

### Considerações

- O broker é **em memória** (sem Redis). O servidor deve rodar com **1 único worker**.
- Se o cliente perder a conexão, ele reconecta automaticamente e busca notificações perdidas via polling.
- Admins e gerentes recebem todas as notificações do sistema.

---

## 10. Geração de PDF

### Fluxo

1. Após salvar uma requisição, `pdf_generator.py` é chamado.
2. ReportLab monta o documento com dados da requisição, itens, QR Code e assinatura.
3. Se houver `canvas_data`, os elementos do editor de desenho são renderizados no PDF.
4. O arquivo é salvo na pasta de rede definida em `PDF_FOLDERS`, organizada por vendedor.

### Roteamento de pastas

```python
# client/core/pdf_folders.py
# PDFs de vendedores → Z:\REQUISIÇÕES (VENDAS)\PDF\<vendor_code>\
# PDFs de gerentes  → Z:\REQUISIÇÕES (VENDAS)\PDF\gerentes\<vendor_code>\
```

### Tipos de itens do canvas suportados no PDF

| Tipo interno | Descrição |
|-------------|-----------|
| `line` | Linha simples |
| `ruler_measure_line` / `manual_dimension_line` | Linha de cota |
| `text` | Texto livre |
| `ruler_measure_text` / `manual_dimension_text` | Rótulo de cota |
| `rect` | Retângulo |
| `arrow` | Seta |
| `freehand` | Desenho livre (caneta) |

---

## 11. Editor de desenho (canvas)

### Arquivo principal

`client/widgets/canvas_widget.py` — implementa `DrawingCanvas(QGraphicsView)`.

### Serialização

O estado do canvas é serializado como JSON e armazenado na tabela `canvas_data`. Cada elemento é um dicionário com:

```json
{
  "type": "line",
  "x1": 100, "y1": 50, "x2": 200, "y2": 150,
  "pen": { "color": "#000000", "width": 2, "style": "solid" }
}
```

### Posicionamento inteligente de cotas

O método `_smart_label_pos()` detecta colisões com outros elementos da cena e posiciona o rótulo de medida no lado oposto quando há sobreposição.

```python
def _smart_label_pos(self, start, end, label="") -> QPointF:
    # vertical: padrão à direita, vira à esquerda se houver colisão
    # horizontal: padrão acima, vira abaixo se houver colisão
```

---

## 12. Sistema de atualizações automáticas

### Componentes

| Arquivo | Função |
|---------|--------|
| `client/updater.py` | `UpdateChecker`, `UpdateDownloader`, `UpdateInstaller` |
| `client/widgets/update_dialog.py` | Interface do popup de atualização |
| `client/update_helper.py` | Executável standalone que substitui os arquivos |

### Fluxo completo

```
1. App abre → UpdateChecker (QThread) consulta GitHub API
   GET https://api.github.com/repos/JoaoLendengues/Requisicoes/releases/latest

2. Se versão remota > CURRENT_VERSION → emite update_available signal

3. UpdateAvailableDialog aparece para o usuário

4. Usuário clica "Atualizar agora" → UpdateDownloader baixa o ZIP

5. UpdateInstaller.install_update():
   a. Cria backup do diretório atual
   b. Extrai ZIP para pasta temporária
   c. Valida payload (verifica requisicoes.exe + _internal + update_helper.exe)
   d. Grava update_state.json (status: "pending")
   e. Lança update_helper.exe com os parâmetros (fora do processo principal)

6. App fecha (QApplication.quit())

7. update_helper.exe:
   a. Aguarda o processo principal terminar
   b. Copia os arquivos novos para o diretório da aplicação
   c. Preserva settings.json e outros arquivos protegidos
   d. Atualiza update_state.json (status: "applied")
   e. Relança requisicoes.exe

8. App reabre → finalize_pending_update() detecta "applied"
   → exibe mensagem de sucesso → limpa estado
```

### Arquivos protegidos durante update

```python
PROTECTED_FILES = ("settings.json",)
PROTECTED_DIRS  = ("backup", "logs", "temp_update")
```

---

## 13. Backup automático

### Configuração

No `.env`:

```
BACKUP_FOLDER=\\10.1.1.140\ti\REQUISICOES\backup_bd
BACKUP_DB_HOST=10.1.1.151
BACKUP_DB_PORT=5432
BACKUP_DB_USER=tipinheiro
BACKUP_DB_PASSWORD=...
BACKUP_DB_NAME=requisicoes
BACKUP_DAILY_HOUR=2         # Horário do backup diário (0-23)
```

Nas configurações do app (admin), é possível ajustar:
- Intervalo entre backups
- Retenção por tipo (diário, semanal, mensal)

### Mecanismo

- Utiliza `pg_dump` (PostgreSQL) para exportar o banco.
- Arquivos salvos com timestamp: `backup_YYYYMMDD_HHMMSS.dump`
- Retenção automática remove backups antigos conforme as regras configuradas.

---

## 14. Gerando o executável

### Pré-requisitos

- PyInstaller instalado: `pip install pyinstaller`
- Inno Setup 6 instalado em `C:\Program Files (x86)\Inno Setup 6\`

### Build manual

```powershell
# 1. Gerar o executável principal
pyinstaller requisicoes.spec --noconfirm

# 2. Gerar o update helper
pyinstaller update_helper.spec --noconfirm
copy dist\update_helper.exe dist\requisicoes\update_helper.exe

# 3. Gerar o instalador
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" `
    "/DMyAppVersion=1.1.0" `
    "/DBuildRoot=dist\requisicoes" `
    installer_script.iss

# Saída:
# dist\requisicoes\         → pasta do executável portátil
# installer_output\         → instalador .exe
```

### Observações sobre o build

- O arquivo `client/settings.json` precisa existir antes do build (é incluído como dado). O CI cria um padrão automaticamente.
- O `CURRENT_VERSION` em `client/version.py` é sobrescrito pelo CI com a versão da tag.

---

## 15. CI/CD — GitHub Actions

Arquivo: `.github/workflows/build_release.yml`

### Gatilhos

| Evento | Condição | Ação |
|--------|----------|------|
| `push` em tag `v*.*.*` | Automático | Build + Release |
| `workflow_dispatch` | Manual | Build (+ Release opcional) |

### Pipeline

```
1. Checkout do código
2. Setup Python 3.11
3. Extrair versão da tag (ex: v1.1.0 → 1.1.0)
4. Instalar dependências do cliente (PySide6, httpx, reportlab, etc.)
5. Atualizar client/version.py com a versão da tag
6. Criar client/settings.json com valores padrão
7. Build PyInstaller → dist/requisicoes/
8. Build update_helper → dist/requisicoes/update_helper.exe
9. Build Inno Setup → installer_output/Requisicoes_Setup_v1.1.0.exe
10. Criar ZIP portátil → dist/Requisicoes_Portable_v1.1.0.zip
11. Publicar no GitHub Releases (instalador + ZIP)
```

### Como publicar uma nova release

```bash
# Após fazer commit de todas as mudanças:
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin v1.2.0
# O GitHub Actions cuida do resto
```

---

## 16. Variáveis de ambiente

Arquivo `.env` na raiz do projeto (baseado em `.env.example`):

```dotenv
# ── Banco de dados ────────────────────────────────────────────
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://usuario:senha@10.1.1.151:5432/requisicoes

# ── Segurança ─────────────────────────────────────────────────
SECRET_KEY=<gerar com: python -c "import secrets; print(secrets.token_hex(32))">
ACCESS_TOKEN_EXPIRE_MINUTES=480

# ── E-mail (Locaweb SMTP) ─────────────────────────────────────
SMTP_HOST=email.locaweb.com.br
SMTP_PORT=587
SMTP_USER=requisicoes@pinheiroferragens.com.br
SMTP_PASSWORD=***

# ── WhatsApp (Evolution API) ──────────────────────────────────
WHATSAPP_API_URL=http://localhost:8080
WHATSAPP_API_KEY=***
WHATSAPP_INSTANCE=pinheiro

# ── Backup ────────────────────────────────────────────────────
BACKUP_FOLDER=\\10.1.1.140\ti\REQUISIÇÕES (VENDAS)\backup_bd
BACKUP_DB_HOST=10.1.1.151
BACKUP_DB_PORT=5432
BACKUP_DB_USER=tipinheiro
BACKUP_DB_PASSWORD=***
BACKUP_DB_NAME=requisicoes
BACKUP_DAILY_HOUR=2
```

---

*Documento gerado em maio de 2026 — Ferragens Pinheiro | Requisições App v1.1.0*

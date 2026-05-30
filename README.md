# Requisições App

Sistema interno de gestão de requisições da **Ferragens Pinheiro**.  
Substitui o processo manual em papel e planilhas por uma aplicação desktop completa, com rastreamento em tempo real, geração automática de PDFs e controle de acesso por perfil.

---

## Funcionalidades

- **Central de Pedidos** — criação, acompanhamento e busca de requisições com status em tempo real
- **Geração de PDF automática** — PDF gerado e enviado para a pasta de rede ao salvar
- **Editor de Desenho** — croquis e cotas MM integrados diretamente à requisição
- **Notificações em tempo real** — via Server-Sent Events (SSE), com toasts e painel lateral
- **Perfis de acesso** — 6 perfis com permissões específicas (Admin, Gerente, Vendedor, A&R, Indústria, Entrega)
- **Histórico** — todas as requisições filtráveis por data, status e vendedor; exportação para Excel
- **Calculadora de Peso** — cálculo de massa de perfis metálicos por dimensão
- **Backup automático** — pg_dump agendado com retenção diária/semanal/mensal
- **Atualização automática** — nova versão detectada no startup, instalada com um clique

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Interface (cliente) | PySide6 / Qt6 |
| API (servidor) | FastAPI + Uvicorn |
| Banco de dados | PostgreSQL + SQLAlchemy |
| Autenticação | JWT (python-jose + bcrypt) |
| Geração de PDF | ReportLab |
| Notificações | Server-Sent Events (SSE) |
| Atualização | GitHub Releases + httpx |

---

## Pré-requisitos

- Python 3.11+
- PostgreSQL 12+
- `pg_dump` disponível no PATH (para backup automático)

---

## Estrutura do projeto

```
requisicoes/
├── client/                 # Aplicação desktop (PySide6)
│   ├── views/              # Telas da interface
│   ├── widgets/            # Componentes reutilizáveis
│   ├── services/           # Comunicação com a API
│   ├── core/               # Configurações, tema, utilitários
│   ├── updater.py          # Sistema de atualização automática
│   └── main.py
├── server/                 # API REST (FastAPI)
│   ├── routers/            # Endpoints por domínio
│   ├── models/             # Modelos do banco (SQLAlchemy)
│   ├── schemas/            # Schemas de validação (Pydantic)
│   ├── services/           # Lógica de negócio
│   └── main.py
├── docs/                   # Documentação e apresentações
├── tests/                  # Testes automatizados
├── migrate_to_pg.py        # Migração SQLite → PostgreSQL
├── criar_admin.py          # Script para criar usuário admin
└── requirements.txt
```

---

## Documentação

| Arquivo | Descrição |
|---------|-----------|
| `docs/manual-usuario.md` | Manual do usuário completo |
| `docs/documentacao-tecnica.md` | Arquitetura, API, banco de dados e deploy |
| `docs/Manual_do_Usuario_Requisicoes_App.docx` | Manual em Word formatado |
| `docs/Apresentacao_Requisicoes_App.pptx` | Apresentação para gestores |
| `ROADMAP.md` | Bugs conhecidos e próximas funcionalidades |

---

## Equipe

| Responsável | Área |
|-------------|------|
| João | Líder do projeto, arquitetura e backend |
| cappinheiro7 | Fluxo, configurações e correções |
| Victor | Canvas, PDF e interface visual |

---

## Versão

**v1.1.0** — Maio de 2026  
Veja o [histórico de releases](https://github.com/JoaoLendengues/Requisicoes/releases) para o changelog completo.

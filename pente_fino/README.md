# Pente Fino — Revisão Geral do Sistema

Pasta dedicada à auditoria tela a tela do sistema (ver plano no `ROADMAP.md`).
Para cada tela: fluxograma + auditoria detalhada (endpoints, tabelas, fluxos de
dados, informações órfãs, inconsistências e permissões por perfil).

## Índice

| # | Tela | Fluxograma | Auditoria | Status |
|---|------|-----------|-----------|--------|
| 01 | Nova Requisição | [fluxograma](./01-nova-requisicao-fluxograma.md) | [auditoria](./01-nova-requisicao-auditoria.md) | ✅ concluída |
| 02 | Painel Gerencial | — | — | ⏳ pendente |
| 03 | Central de Pedidos | — | — | ⏳ pendente |
| 04 | Entregas | — | — | ⏳ pendente |
| 05 | Pinheiro Indústria | — | — | ⏳ pendente |
| 06 | A&R | — | — | ⏳ pendente |
| 07 | Histórico / Busca | — | — | ⏳ pendente |
| 08 | Feedbacks | — | — | ⏳ pendente |
| 09 | Configurações (10 abas) | — | — | ⏳ pendente |

## Fluxos transversais

| Fluxo | Status |
|-------|--------|
| A. Notificações (SSE) | ⏳ |
| B. Auditoria (`audit_log`) | ⏳ |
| C. Geração de PDF | ⏳ |
| D. Atualização automática | ⏳ |
| E. Backup periódico | ⏳ |
| F. Status flow das requisições | ⏳ |

> Os fluxogramas usam [Mermaid](https://mermaid.js.org/) e renderizam direto no GitHub.

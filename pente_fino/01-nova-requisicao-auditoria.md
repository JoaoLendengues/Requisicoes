# Pente Fino — Tela: Nova Requisição

**View:** `client/views/requisition_form.py` (+ widgets `item_table.py`, `canvas_widget.py`, `status_badge.py`)
**Save flow:** `client/views/main_window.py` (`_save_requisition` → `_after_save` → `_on_fully_saved`)
**Router:** `server/routers/requisitions.py` · **Schema:** `schemas/requisition.py` · **Model:** `models/requisition.py`

---

## 1. Endpoints da API que consome

| Ação na tela | Método cliente | Endpoint | Permissão |
|---|---|---|---|
| Busca de cliente (tempo real) | `api.list_clients(term, limit)` | `GET /clients/?search=&limit=` | qualquer autenticado |
| Carregar cliente ao abrir | `api.get_client(id)` | `GET /clients/{id}` | qualquer autenticado |
| Autopreencher produto pelo código | `api.list_products("", code, 1)` | `GET /products/?code=` | qualquer autenticado |
| Criar requisição | `api.create_requisition(data)` | `POST /requisitions/` | `require_creator` |
| Atualizar requisição | `api.update_requisition(id, data)` | `PATCH /requisitions/{id}` | `require_creator` |
| Salvar desenho (canvas) | `api.update_canvas(id, json)` | `PATCH /requisitions/{id}/canvas` | `require_creator` |
| Abrir requisição existente | `api.get_requisition(id)` | `GET /requisitions/{id}` | `get_current_user` + `_can_view` |
| Enviar p/ produção / atalho | `api.update_status(id, status, note)` | `PATCH /requisitions/{id}/status` | `get_current_user` + `_can_edit` |
| Atalho "abrir por PED" | `api.list_requisitions(...)` | `GET /requisitions/?search=` | filtrado por perfil |

> O PDF **não é endpoint** — é gerado localmente no cliente (`services/pdf_generator.py`) e salvo na pasta de rede do vendedor.

---

## 2. Tabelas do banco que lê/escreve

**Lê:** `clients`, `products`, `requisitions` (+ `requisition_items`, `canvas_data`, `status_history`, e `users` para nomes de vendedor/cliente).

**Escreve (ao salvar):**
- `requisitions` (cabeçalho) — INSERT/UPDATE
- `requisition_items` — recriados a cada update (delete-all + re-insert)
- `canvas_data` — chamada separada (`update_canvas`)
- `status_history` — 1 registro no create; +1 ao enviar p/ produção
- `audit_log` — via `log_action` (CREATE/UPDATE)
- `notifications` — só ao enviar p/ produção

---

## 3. Fluxos de dados

- **Cliente:** digitação → `GET /clients` → escolha → guarda só `client_id` → enviado no payload. Ao reabrir, `client_id` → `GET /clients/{id}` repõe o texto.
- **Produto:** código no item → `GET /products?code=` → preenche `product_name`. Só conveniência; persiste o texto do item, não um vínculo com `products`.
- **Salvar (2 passos):** `get_form_data()` → `POST/PATCH /requisitions` → depois `PATCH /canvas` → depois PDF local.
- **Peso:** somado no cliente, mas recalculado no servidor a partir dos itens.
- **Enviar p/ produção:** salva primeiro → `PATCH /status` (nota `PRODUCAO|...`) → `status_history` + `notifications` (SSE).
- **Abrir existente:** Histórico/Central de Pedidos → `GET /requisitions/{id}` → `load_requisition()`.

---

## 4. Informações órfãs / desperdiçadas

1. **`weight` enviado pelo cliente é ignorado no create** — servidor recalcula de `_sum_item_weights(items)`.
2. **`os_number`** — existe em model/schema/Response, "trackeado" no update, mas a tela nunca preenche nem exibe.
3. **`nf_attachment`** — coluna + campo na Response + endpoint `PATCH /{id}/nf`, mas a Nova Requisição não usa nada.
4. **`delivery_deadline_changed_at` / `delivery_deadline_change_reason`** — colunas no model que **não estão na `RequisitionResponse`**; o motivo de "prazo alterado" só chega via `status_history`/notificação.
5. **Payload de resposta pesado** — ~15 campos `production_*`, `invoiced`, `delivered_at`, `cancel_reason` que esta tela ignora (outras telas usam).

---

## 5. Pontos de quebra / inconsistências

1. **Permissão cliente × servidor divergente (alta).** UI abre form em somente leitura para `producao`/`industria`/`entrega`, mas `require_creator` permite esses perfis criarem/editarem. Única barreira = UI.
2. **Save não atômico (canvas) (média).** Requisição numa chamada, desenho em outra (`update_canvas`). Se a 2ª falhar, requisição fica sem desenho. A assinatura, ao contrário, vai no mesmo payload (atômica) — tratamento inconsistente.
3. **Peso com fonte dupla** — risco de divergência entre tela e banco.
4. **`has_unsaved_data()` sempre `True` para requisição carregada** (`req_id is not None`) — falso positivo de "dados não salvos" ao navegar.
5. **Itens recriados a cada update** (delete-all + re-insert) — `id` mudam e o `audit_log` só registra contagem ("3→4 itens"), perdendo rastreabilidade fina.

---

## 6. Permissões por perfil

**Acesso à tela (cliente):** todos veem "Nova Requisição".
- admin/gerente/vendedor: criam e editam.
- producao/industria/entrega: form em **somente leitura** (`is_view_only`).

**Servidor:**
- Criar/editar/canvas (`require_creator`): admin, gerente, vendedor, **producao, industria, entrega** — *mais permissivo que a UI*.
- Editar requisição específica (`_can_edit_requisition`): admin/gerente sempre; vendedor só as próprias; produção só as do seu destino.
- `_ensure_editable`: bloqueia editar requisição recebida/finalizada (`finalized_at`) ou em status fechado.
- Prazo mínimo: vendedor barrado abaixo do mínimo; admin/gerente podem gravar abaixo.
- Ver requisição (`_can_view_requisition`): admin/gerente tudo; vendedor só as próprias; produção só as do seu destino.
- clients/products (lookup): qualquer autenticado lê; criar/importar = só admin.

---

## 🎯 Achados prioritários

| # | Achado | Severidade | Ação sugerida |
|---|--------|-----------|---------------|
| 1 | `require_creator` libera produção/indústria/entrega a criar/editar (UI não) | **Alta** | Restringir endpoint a admin/gerente/vendedor ou validar destino |
| 2 | Canvas salvo fora da transação da requisição | **Média** | Incluir `canvas_json` no payload do create/update |
| 3 | `weight` do cliente ignorado | Baixa | Documentar fonte única ou remover do payload |
| 4 | `nf_attachment`/`os_number` órfãos | Baixa | Implementar ou remover a superfície |
| 5 | `has_unsaved_data` falso positivo | Baixa | Comparar estado carregado × atual |

---

*Auditoria gerada em 30/05/2026 — primeira tela do plano "Pente Fino — Revisão Geral do Sistema".*

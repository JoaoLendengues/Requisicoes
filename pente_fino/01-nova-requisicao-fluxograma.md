# Fluxograma — Nova Requisição

> Tela: `client/views/requisition_form.py` · Save flow: `client/views/main_window.py`
> Backend: `server/routers/requisitions.py` · Schema/Model: `schemas/requisition.py`, `models/requisition.py`
>
> Os diagramas abaixo estão em [Mermaid](https://mermaid.js.org/) — renderizam automaticamente no GitHub.

---

## 1. Fluxo principal — Salvar requisição

```mermaid
flowchart TD
    U([Usuário preenche o formulário]) --> SAVE[Botão Salvar / Ctrl+S]
    SAVE --> VAL{PED válido<br/>e cliente selecionado?}
    VAL -- Não --> WARN[Aviso e cancela o salvamento]
    VAL -- Sim --> GFD["get_form_data()<br/>ped, client_id, obra, prazo,<br/>retirada/entrega, fone, endereço,<br/>itens, obs, assinatura (b64)"]
    GFD --> DEC{req_id já existe?}
    DEC -- Não --> CRE["api.create_requisition<br/>POST /requisitions/"]
    DEC -- Sim --> UPD["api.update_requisition<br/>PATCH /requisitions/{id}"]
    CRE --> DB1[("requisitions<br/>requisition_items<br/>status_history<br/>audit_log")]
    UPD --> DB1
    DB1 --> CANVAS["_after_save<br/>api.update_canvas<br/>PATCH /requisitions/{id}/canvas"]
    CANVAS --> DB2[("canvas_data")]
    DB2 --> PDF["_on_fully_saved<br/>gera PDF localmente<br/>(pasta de rede do vendedor)"]
    PDF --> DONE([Requisição salva + PDF gerado])

    CANVAS -. "se falhar aqui, a requisição<br/>persiste SEM o desenho" .-> RISK{{"⚠️ Save não atômico"}}

    classDef risco fill:#FEF2F2,stroke:#DC2626,color:#991B1B;
    class RISK risco;
```

---

## 2. Busca de cliente e lookup de produto (auxiliares, só leitura)

```mermaid
flowchart LR
    T[Digita no campo de cliente] --> LC["api.list_clients(termo)<br/>GET /clients/?search="]
    LC --> CL[("tabela clients")]
    CL --> PICK[Usuário escolhe<br/>→ guarda apenas client_id]

    IT[Digita código do produto na linha] --> LP["api.list_products(code)<br/>GET /products/?code="]
    LP --> PR[("tabela products")]
    PR --> FILL[Preenche product_name na linha<br/>(texto livre — sem vínculo persistente)]
```

---

## 3. Abrir requisição existente

```mermaid
flowchart LR
    H["Histórico / Busca<br/>ou Central de Pedidos"] --> OPEN["_open_requisition(id)"]
    OPEN --> GR["api.get_requisition<br/>GET /requisitions/{id}"]
    GR --> DB[("requisitions + items<br/>+ canvas_data + status_history")]
    DB --> LOAD["load_requisition()<br/>popula o formulário"]
    LOAD --> RO{"Perfil view-only<br/>ou já finalizada?"}
    RO -- Sim --> LOCK[Form em somente leitura]
    RO -- Não --> EDIT[Form editável]
```

---

## 4. Enviar para produção

```mermaid
flowchart TD
    SP[Botão Enviar para Produção] --> S1["save_requested<br/>(salva a requisição primeiro)"]
    S1 --> DEST{Escolhe destino<br/>A&R ou Pinheiro Indústria}
    DEST --> US["api.update_status(id, status, nota)<br/>PATCH /requisitions/{id}/status"]
    US --> SH[("status_history")]
    US --> NOT[("notifications<br/>→ SSE p/ equipe de produção")]
    NOT --> TOAST[Toast + badge no destino]
```

---

## 5. Mapa de permissões (resumo)

```mermaid
flowchart TD
    subgraph CLIENTE["Cliente (UI)"]
      A1["admin / gerente / vendedor<br/>→ criam e editam"]
      A2["produção / indústria / entrega<br/>→ form SOMENTE LEITURA"]
    end
    subgraph SERVIDOR["Servidor (require_creator)"]
      B1["admin, gerente, vendedor,<br/>PRODUÇÃO, INDÚSTRIA, ENTREGA<br/>→ TODOS podem criar/editar"]
    end
    A2 -. "⚠️ divergência:<br/>UI bloqueia, API permite" .-> B1

    classDef risco fill:#FEF2F2,stroke:#DC2626,color:#991B1B;
    class B1 risco;
```

---

## Legenda de riscos destacados

| ⚠️ | Onde | Resumo |
|----|------|--------|
| Save não atômico | Diagrama 1 | Desenho (canvas) salvo em chamada separada; se falhar, requisição fica sem o desenho. |
| Permissão UI × API | Diagrama 5 | `require_creator` libera produção/indústria/entrega que a UI bloqueia. |

> Detalhamento completo em [`01-nova-requisicao-auditoria.md`](./01-nova-requisicao-auditoria.md).

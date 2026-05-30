# Roadmap do Projeto

Organizacao por prioridade:
- Alta: critico, bloqueia fluxo ou gera retrabalho grande
- Media: importante, mas com workaround
- Baixa: melhoria incremental ou refinamento

Responsaveis:
- [joao]      → lider do projeto
- [cappinho]  → bugs de fluxo e configuracoes
- [victor]    → canvas, PDF e visual

---

## Alta prioridade

- [x] [joao]     Campos "Entrega" e "Retirada" como obrigatorios em Nova Requisicao.
                 Impede salvar se nenhuma das duas opcoes estiver selecionada.
                 *** RESOLVIDO ***

- [x] [joao]     A&R + Pinheiro Industria: alterar prazo de entrega com justificativa.
                 Producao digita o motivo da alteracao; requisicao volta para o vendedor
                 com notificacao e novo prazo visivel no historico.
                 *** RESOLVIDO ***

- [x] [joao]     Motivos predefinidos para cancelamento de requisicoes.
                 Caixa de selecao: "Desistencia", "Material danificado / avariado", "Outro".
                 Opcao "Outro" exige campo de texto livre obrigatorio.
                 Mostrar motivo nas tabelas de historico e nas telas de A&R / Industria.
                 *** RESOLVIDO ***

- [x] [cappinho] Remover campo de importacao de usuario na Central de Usuarios.
                 Central de Usuarios virou aba "Usuarios" dentro de Configuracoes,
                 com acesso exclusivo para administradores. Campo de importacao removido.
                 *** RESOLVIDO ***

---

## Media prioridade

- [x] [joao]     Prazo minimo em dias uteis.
                 Horario comercial: segunda a sexta 8h-18h, sabado 8h-12h.
                 Novo parametro em Configuracoes > Sistema para definir o minimo.
                 Notificar vendedor / gerente quando o prazo estiver proximo ou vencido.
                 *** RESOLVIDO *** (sabado nao conta; admin/gerente podem gravar abaixo do minimo)

- [x] [cappinho] Painel Gerencial: identificar backups realizados (data, tamanho, status).
                 Informacao ja disponivel no Painel Tecnico. Decidido nao replicar no
                 Painel Gerencial.
                 *** RESOLVIDO ***

- [x] [joao]     Botao "Exportar para Excel" em Historico / Busca.
                 Exporta os resultados filtrados atuais para .xlsx (openpyxl).
                 Aproveitado para reagrupar os filtros em duas linhas (mais
                 legivel e com folga para novos filtros).
                 *** RESOLVIDO ***

- [x] [joao]     A&R: ao enviar requisicao para maquina de corte, sempre encaminhar para
                 maquina de dobra em seguida.
                 Substituir botao "Finalizar" por "Encaminhar para Dobra" nas maquinas de
                 corte. Exibir lista de maquinas de dobra disponiveis para escolha.
                 Botao "Finalizar" permanece apenas nas maquinas de dobra.
                 *** RESOLVIDO ***

- [x] [joao]     Painel Tecnico movido para Configuracoes > aba "Sistema" (deixou de ser
                 tela na sidebar). Cards reorganizados em secoes (Disponibilidade /
                 Desempenho & Recursos / Usuarios), no padrao visual da aba.
                 *** RESOLVIDO ***

- [x] [joao]     Cadastro de clientes: nova aba "Clientes" em Configuracoes (admin).
                 Lista por busca no servidor, cadastro individual (code/name/cnpj
                 obrigatorios) e importacao em lote por planilha Excel (create-only,
                 rejeita e lista conflitos). Usa rotas existentes; sem reiniciar servidor.
                 *** RESOLVIDO ***

---

## Aguardando definicao

- [x] [joao]     Faturar pedido automaticamente ao enviar para producao (A&R e Pinheiro Industria).
                 *** RESOLVIDO ***

---

## Engavetado (revisitar futuramente)

Ideias preservadas, fora da fila ativa por ora. Nao descartadas.

- [ ] [victor]   Relatorio de maquinas (corte e dobra) de A&R e Pinheiro Industria.
                 Mostrar historico de uso, pedidos processados e tempo medio por maquina.
                 *** ENGAVETADO *** (sem prioridade no momento; revisitar quando houver demanda)

- [ ] [victor]   Canvas: ferramenta Esquadro no editor de desenho.
                 *** ENGAVETADO *** (falta de definicao/ideias ate o momento; discutir
                 especificacao antes de qualquer implementacao)

---

# Pente Fino - Revisao Geral do Sistema

Auditar **cada tela** verificando:
- Endpoints da API que ela consome
- Tabelas do banco que ela le/escreve
- Fluxos de dados (de onde vem, pra onde vai)
- Informacoes orfas / desperdicadas
- Pontos de quebra / inconsistencias (ex.: modelo Python diferente do schema do banco)
- Permissoes por perfil

## Telas a revisar (na ordem)

### Sidebar principal - NAV_ITEMS

- [ ] **1. Nova Requisicao** (`nova`) - formulario central, signature, canvas, itens, prazo, envio para producao
- [ ] **2. Painel Gerencial** (`dashboard`) - admin/gerente, metricas e graficos
- [ ] **3. Central de Pedidos** (`pedidos`) - 5 secoes: aguardando, em producao, faturados, cancelados, atrasados
- [ ] **4. Entregas** (`entregas`) - *novo, adicionado pelo cappinheiro recentemente*
- [ ] **5. Pinheiro Industria** (`pinheiro_industria`) - cards por maquina + acoes de producao
- [ ] **6. A&R** (`ar`) - cards por maquina + corte->dobra
- [ ] **7. Historico / Busca** (`historico`) - filtros + export Excel
- [ ] **8. Feedbacks** (`feedback`) - registro/visualizacao de feedbacks

### Sidebar - BOTTOM_NAV_ITEMS

- [ ] **9. Configuracoes** (`config`) - admin only, com abas:
  - [ ] 9.1. Aparencia
  - [ ] 9.2. Conta (trocar senha)
  - [ ] 9.3. Sistema (URL servidor, alertas, prazo minimo, motivos de cancelamento, Painel Tecnico embarcado)
  - [ ] 9.4. Login (backgrounds)
  - [ ] 9.5. Backup
  - [ ] 9.6. Usuarios
  - [ ] 9.7. Clientes
  - [ ] 9.8. Cadastro de Maquinas
  - [ ] 9.9. Operadores
  - [ ] 9.10. Ajuda

### Fluxos transversais (nao sao telas, mas conectam varias)

- [ ] **A.** Notificacoes (SSE + tabela `notifications`)
- [ ] **B.** Auditoria (`audit_log`)
- [ ] **C.** Geracao de PDF (caminho da rede, fallback)
- [ ] **D.** Atualizacao automatica (GitHub releases)
- [ ] **E.** Backup periodico (`pg_dump`)
- [ ] **F.** Status flow das requisicoes (em_andamento -> producao -> faturado)

## Template de auditoria por tela

Para cada item da lista, produzir:

```
### Tela: <Nome>
- View: client/views/<arquivo>.py
- Endpoints consumidos:
  - GET  /<rota>     -> funcao X
  - POST /<rota>     -> funcao Y
- Tabelas de banco lidas:  requisitions, clients...
- Tabelas escritas:        ...
- Permissoes (por role):   admin: ..., gerente: ..., vendedor: ...
- Fluxo de dados:          ...
- Achados:                 ...
```

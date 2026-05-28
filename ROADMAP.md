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

- [ ] [joao]     Campos "Entrega" e "Retirada" como obrigatorios em Nova Requisicao.
                 Impede salvar se nenhuma das duas opcoes estiver selecionada.

- [ ] [joao]     A&R + Pinheiro Industria: alterar prazo de entrega com justificativa.
                 Producao digita o motivo da alteracao; requisicao volta para o vendedor
                 com notificacao e novo prazo visivel no historico.

- [ ] [joao]     Motivos predefinidos para cancelamento de requisicoes.
                 Caixa de selecao: "Desistencia", "Material danificado / avariado", "Outro".
                 Opcao "Outro" exige campo de texto livre obrigatorio.
                 Mostrar motivo nas tabelas de historico e nas telas de A&R / Industria.

- [ ] [cappinho] Remover campo de importacao de usuario na Central de Usuarios.

---

## Media prioridade

- [ ] [joao]     Prazo minimo em dias uteis.
                 Horario comercial: segunda a sexta 8h-18h, sabado 8h-12h.
                 Novo parametro em Configuracoes > Sistema para definir o minimo.
                 Notificar vendedor / gerente quando o prazo estiver proximo ou vencido.

- [ ] [cappinho] Painel Gerencial: identificar backups realizados (data, tamanho, status).

- [ ] [cappinho] Botao "Exportar para Excel" em Historico / Busca.
                 Exportar os resultados filtrados atualmente visiveis na tabela.

- [ ] [joao]     A&R: ao enviar requisicao para maquina de corte, sempre encaminhar para
                 maquina de dobra em seguida.
                 Substituir botao "Finalizar" por "Encaminhar para Dobra" nas maquinas de
                 corte. Exibir lista de maquinas de dobra disponiveis para escolha.
                 Botao "Finalizar" permanece apenas nas maquinas de dobra.

- [ ] [victor]   Relatorio de maquinas (corte e dobra) de A&R e Pinheiro Industria.
                 Mostrar historico de uso, pedidos processados e tempo medio por maquina.

---

## Aguardando definicao

- [ ] [victor]   Canvas: ferramenta Esquadro no editor de desenho.
                 *** NAO IMPLEMENTAR ate receber autorizacao. Discutir especificacao primeiro. ***

- [x] [joao]     Faturar pedido automaticamente ao enviar para producao (A&R e Pinheiro Industria).
                 *** RESOLVIDO ***

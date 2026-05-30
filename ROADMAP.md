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

- [ ] [victor]   Relatorio de maquinas (corte e dobra) de A&R e Pinheiro Industria.
                 Mostrar historico de uso, pedidos processados e tempo medio por maquina.

---

## Aguardando definicao

- [ ] [victor]   Canvas: ferramenta Esquadro no editor de desenho.
                 *** NAO IMPLEMENTAR ate receber autorizacao. Discutir especificacao primeiro. ***

- [x] [joao]     Faturar pedido automaticamente ao enviar para producao (A&R e Pinheiro Industria).
                 *** RESOLVIDO ***

# Roadmap do Projeto

Arquivo para registrar:
- correcao de bugs
- proximas implementacoes
- novas ideias

Organizacao por prioridade:
- Alta: critico, bloqueia fluxo ou gera retrabalho grande
- Media: importante, mas com workaround
- Baixa: melhoria incremental ou refinamento

Responsaveis:
- [joao]      → lider do projeto
- [cappinho]  → bugs de fluxo e configuracoes
- [victor]    → canvas, PDF e visual

---

## Correcao de Bugs

### Prioridade Alta

- [ ] [cappinho] Ajustar filtro de datas da tela "HISTORICO/BUSCA" (puxando datas anteriores, nao somente a data selecionada)
- [ ] [cappinho] Corrigir contador de notificacoes na tela de notificacoes (badge nao reflete contagem correta)
- [ ] [victor]   Corrigir bug da tela de desenho: linha iniciando em ponto pre-definido
- [ ] [victor]   Revisar selecao de formas ocas no canvas (rect/elipse selecionaveis so na borda — comportamento implementado, mas pode precisar de ajuste fino)

### Prioridade Media

- [ ] [cappinho] Ajustar calendario para aparecer o simbolo da seta para abrir o calendario

### Prioridade Baixa

- [ ] [victor]   Refinar o raio do ima para ficar mais amplo

---

## v1.1.0 — Em andamento

### Prioridade Alta

- [ ] [joao]     Guia rapido por nivel de acesso (tutorial interativo por role ao primeiro login)
- [x] 2026-05-26 [joao]     Sistema de backup periodico do banco de dados

### Prioridade Media

- [x] 2026-05-25 [victor]    Melhorar velocidade de linhas no editor de desenho
- [x] 2026-05-26 [joao]     Alterar diretorio dos login_backgrounds para o servidor (\\10.1.1.140\ti\REQUISICOES (VENDAS)\login_backgrounds)

### Prioridade Baixa

- [x] 2026-05-25 [joao]     Ajustar botoes do editor de desenho (nomes cortados em diferentes resolucoes)
- [x] 2026-05-26 [joao]     Mudar logo do sidebar nos widgets A&R e Pinheiro Industria

---

## Proximas Implementacoes

### Prioridade Alta

- [ ] [joao]     Refinar niveis de acesso (revisar permissoes por role em todas as telas)

### Prioridade Media

- [ ] [joao]     Performance: reducao de freezes causados por chamadas ao servidor durante navegacao
                 Ideia: exibir indicador de carregamento (spinner ou skeleton) nas views que fazem
                 refresh() ao serem abertas (historico, pedidos, dashboard, etc.), evitando que o
                 usuario perceba travamento enquanto a API responde. Avaliar tambem cache de resultado
                 das ultimas chamadas para que a view ja apareca com dados ao re-navegar.
- [ ] [cappinho] Melhorar personalizacao da tela de configuracao
- [ ] [cappinho] Implementar filtro por vendedor na tela "HISTORICO/BUSCA"
- [ ] [victor]   Adicionar ferramenta Curva no editor de desenho (atalho: tecla C)
- [ ] [victor]   Colocar emojis na impressao dos PDFs
- [ ] [victor]   No PDF, alinhar mais a esquerda o titulo "Requisicao", data e nome do vendedor

### Prioridade Baixa

- [ ] [victor]   Polimento geral do app
- [ ] [joao]     Revisao geral do codigo

---

## Novas Ideias

### Prioridade Alta

- [ ] [victor]   Ajustar design dos pop-ups de notificacoes (minimalista e moderno)

### Prioridade Media

- [ ] [victor]   Definir direcao visual unificada para componentes de feedback (toasts, drawers, modais)

### Prioridade Baixa

- [ ] [victor]   Criar checklist de consistencia visual antes de cada release

---

## Concluido

- [x] 2026-05-25 [joao]     Fix SSE: endpoint de notificacoes segurava conexao de banco por usuario logado (esgotava pool com 10+ usuarios)
- [x] 2026-05-25 [joao]     Backend: adicionar indices de performance nas tabelas requisitions, requisition_items, status_history e notifications
- [x] 2026-05-25 [joao]     Backend: aumentar pool de conexoes para 100 simultaneas (pool_size=25, max_overflow=75)
- [x] 2026-05-25 [joao]     Corrigir alerta "Sem permissao para acessar destino de producao" exibido para vendedores ao login
- [x] 2026-05-24 [joao]     Redirecionar PDF por vendedor: pasta por codigo de usuario em \\10.1.1.140\ti\REQUISICOES (VENDAS)\PDF\VENDEDORES
- [x] 2026-05-24 [joao]     Gerentes redirecionam PDF para pasta do vendedor da requisicao
- [x] 2026-05-24 [joao]     Implementar sistema de atualizacoes (GitHub Actions + executavel via Inno Setup)
- [x] 2026-05-24 [joao]     Corrigir SECRET_KEY padrao exposta no config (adicionada ao .env)
- [x] 2026-05-24 [joao]     Criar icone do app e configurar no executavel e instalador

---

## Como usar este arquivo

- Sempre adicionar item novo na secao correta e com prioridade definida.
- Marcar com [x] quando concluir.
- Incluir data de conclusao ao lado do [x] quando fechar um item. Ex: [x] 2026-05-22
- Se abrir um item novo, indicar o responsavel entre colchetes. Ex: [joao]

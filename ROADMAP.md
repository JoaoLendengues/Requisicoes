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

## v1.2.0 — Em andamento

### Prioridade Alta

- [ ] [victor]   Cursor da caneta como ponto/dot no canvas
- [ ] [joao]     Guia Rapido expandido: slides contextuais por tela (Central de Pedidos, Formulario, Canvas, Historico) alem da sidebar

### Prioridade Media

- [ ] [joao]     Performance: SSE sem backoff pode acumular reconexoes — adicionar espera exponencial na reconexao
- [ ] [joao]     Performance: garantir que todas as chamadas de rede usam QThread (alguns pontos ainda rodam na main thread)
- [ ] [cappinho] Implementar filtro por vendedor na tela "HISTORICO/BUSCA"
- [ ] [victor]   Colocar emojis na impressao dos PDFs
- [ ] [victor]   No PDF, alinhar mais a esquerda o titulo "Requisicao", data e nome do vendedor

### Prioridade Baixa

- [ ] [victor]   Polimento geral do app
- [ ] [joao]     Revisao geral do codigo

---

## Proximas Implementacoes

### Prioridade Alta

- [ ] [joao]     Refinar niveis de acesso (revisar permissoes por role em TODAS as telas — sidebar ja oculta, mas validacoes internas podem estar incompletas)

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

- [x] 2026-05-27 [victor]   Canvas: ferramenta Curva estilo Paint (clique1=inicio, arrasta=fim, move=controle, clique=confirma bezier quadratico)
- [x] 2026-05-27 [victor]   Canvas: selecao hollow em rect/elipse — shape() retorna so a borda (HollowRectItem / HollowEllipseItem)
- [x] 2026-05-27 [victor]   Canvas: espelhamento vertical correto no preview e no PDF
- [x] 2026-05-27 [joao]     Settings: reorganizar em mini-abas horizontais (Aparencia, Conta, Sistema, Login, Backup, Ajuda)
- [x] 2026-05-27 [joao]     Performance: lazy instantiation das views no MainWindow (cria na primeira navegacao)
- [x] 2026-05-27 [joao]     Fix backup endpoint PATCH /settings retornando 404 (Body() explicito no FastAPI)
- [x] 2026-05-27 [joao]     Fix PDF: WinError 1326/5/53 — funcao de acesso seguro a rede com mensagem clara de erro de credenciais
- [x] 2026-05-26 [joao]     Guia rapido por nivel de acesso (spotlight tour com perfis, primeiro login)
- [x] 2026-05-26 [joao]     Sistema de backup periodico do banco de dados (pg_dump agendado, retencao diario/semanal/mensal)
- [x] 2026-05-26 [victor]   Posicionamento inteligente de rotulos no canvas (regua e cota MM sem sobreposicao)
- [x] 2026-05-26 [victor]   Regua e cota MM renderizadas corretamente no PDF gerado
- [x] 2026-05-26 [joao]     Alterar diretorio dos login_backgrounds para o servidor (\\10.1.1.140\ti\REQUISICOES (VENDAS)\login_backgrounds)
- [x] 2026-05-25 [victor]   Melhorar velocidade de linhas no editor de desenho
- [x] 2026-05-25 [joao]     Ajustar botoes do editor de desenho (nomes cortados em diferentes resolucoes)
- [x] 2026-05-25 [joao]     Mudar logo do sidebar nos widgets A&R e Pinheiro Industria
- [x] 2026-05-25 [joao]     Fix SSE: endpoint de notificacoes segurava conexao de banco por usuario logado (esgotava pool com 10+ usuarios)
- [x] 2026-05-25 [joao]     Backend: adicionar indices de performance nas tabelas requisitions, requisition_items, status_history e notifications
- [x] 2026-05-25 [joao]     Backend: aumentar pool de conexoes para 100 simultaneas (pool_size=25, max_overflow=75)
- [x] 2026-05-25 [joao]     Corrigir alerta "Sem permissao para acessar destino de producao" exibido para vendedores ao login
- [x] 2026-05-25 [joao]     Redirecionar PDF por vendedor: pasta por codigo de usuario em \\10.1.1.140\ti\REQUISICOES (VENDAS)\PDF\VENDEDORES
- [x] 2026-05-25 [joao]     Gerentes redirecionam PDF para pasta do vendedor da requisicao
- [x] 2026-05-22 [joao]     Refinar niveis de acesso por perfil (sidebar oculta telas sem permissao; A&R e Industria em leitura)
- [x] 2026-05-24 [joao]     Implementar sistema de atualizacoes (GitHub Actions + executavel via Inno Setup)
- [x] 2026-05-24 [joao]     Corrigir SECRET_KEY padrao exposta no config (adicionada ao .env)
- [x] 2026-05-24 [joao]     Criar icone do app e configurar no executavel e instalador

---

## Como usar este arquivo

- Sempre adicionar item novo na secao correta e com prioridade definida.
- Marcar com [x] quando concluir.
- Incluir data de conclusao ao lado do [x] quando fechar um item. Ex: [x] 2026-05-22
- Se abrir um item novo, indicar o responsavel entre colchetes. Ex: [joao]

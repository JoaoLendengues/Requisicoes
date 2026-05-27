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

## Em andamento

---

## Concluido

- [x] 2026-05-27 [joao]     Guia Rapido expandido: passos contextuais por tela (formulario,
                             historico) com getters de widget in-screen por perfil.
                             Botao ? discreto no formulario de requisicao e no historico.
                             Arquivos: client/views/requisition_form.py,
                                       client/views/history_view.py,
                                       client/views/main_window.py

- [x] 2026-05-27 [victor]   Canvas: cursor da caneta como ponto/dot
- [x] 2026-05-27 [victor]   Canvas: ferramenta Curva estilo Paint (arrasta base, move controle, clica confirma bezier)
- [x] 2026-05-27 [victor]   Canvas: selecao hollow em rect/elipse (shape() retorna so a borda)
- [x] 2026-05-27 [victor]   Canvas: espelhamento vertical correto no preview e no PDF
- [x] 2026-05-27 [victor]   Canvas: linha iniciando em ponto pre-definido (corrigido)
- [x] 2026-05-27 [victor]   Canvas: raio do ima refinado
- [x] 2026-05-27 [victor]   Emojis na impressao dos PDFs
- [x] 2026-05-27 [victor]   PDF: alinhar titulo "Requisicao", data e nome do vendedor mais a esquerda
- [x] 2026-05-27 [victor]   Ajustar design dos pop-ups de notificacoes (minimalista e moderno)
- [x] 2026-05-27 [cappinho] Filtro de datas da tela "HISTORICO/BUSCA" corrigido
- [x] 2026-05-27 [cappinho] Contador de notificacoes no badge corrigido
- [x] 2026-05-27 [cappinho] Calendario com simbolo de seta para abrir
- [x] 2026-05-27 [cappinho] Filtro por vendedor na tela "HISTORICO/BUSCA"
- [x] 2026-05-27 [cappinho] Melhorar personalizacao da tela de configuracao (mini-abas)
- [x] 2026-05-27 [joao]     Settings: mini-abas horizontais (Aparencia, Conta, Sistema, Login, Backup, Ajuda)
- [x] 2026-05-27 [joao]     Performance: lazy instantiation das views no MainWindow
- [x] 2026-05-27 [joao]     Performance: SSE com backoff exponencial na reconexao
- [x] 2026-05-27 [joao]     Performance: todas as chamadas de rede em QThread
- [x] 2026-05-27 [joao]     Fix backup endpoint PATCH /settings retornando 404
- [x] 2026-05-27 [joao]     Fix PDF: WinError 1326/5/53 com mensagem clara de erro de credenciais
- [x] 2026-05-27 [joao]     Refinar niveis de acesso por role em todas as telas
- [x] 2026-05-26 [joao]     Guia rapido por nivel de acesso — spotlight tour no primeiro login
- [x] 2026-05-26 [joao]     Sistema de backup periodico (pg_dump, retencao diario/semanal/mensal)
- [x] 2026-05-26 [victor]   Posicionamento inteligente de rotulos no canvas (regua e cota MM)
- [x] 2026-05-26 [victor]   Regua e cota MM renderizadas corretamente no PDF
- [x] 2026-05-26 [joao]     Alterar diretorio dos login_backgrounds para o servidor
- [x] 2026-05-25 [victor]   Melhorar velocidade de linhas no editor de desenho
- [x] 2026-05-25 [joao]     Ajustar botoes do editor de desenho (nomes cortados em diferentes resolucoes)
- [x] 2026-05-25 [joao]     Mudar logo do sidebar nos widgets A&R e Pinheiro Industria
- [x] 2026-05-25 [joao]     Fix SSE: conexao de banco segurada por usuario (esgotava pool com 10+ usuarios)
- [x] 2026-05-25 [joao]     Backend: indices de performance nas tabelas principais
- [x] 2026-05-25 [joao]     Backend: pool de conexoes aumentado para 100 simultaneas
- [x] 2026-05-25 [joao]     Corrigir alerta "Sem permissao para acessar destino de producao" para vendedores
- [x] 2026-05-25 [joao]     Redirecionar PDF por vendedor (pasta por codigo em \\servidor\...\PDF\VENDEDORES)
- [x] 2026-05-25 [joao]     Gerentes redirecionam PDF para pasta do vendedor da requisicao
- [x] 2026-05-24 [joao]     Sistema de atualizacoes automaticas (GitHub Actions + Inno Setup)
- [x] 2026-05-24 [joao]     Corrigir SECRET_KEY padrao exposta (adicionada ao .env)
- [x] 2026-05-24 [joao]     Criar icone do app e configurar no executavel e instalador

---

## Como usar este arquivo

- Sempre adicionar item novo na secao correta e com prioridade definida.
- Marcar com [x] quando concluir.
- Incluir data de conclusao ao lado do [x] quando fechar um item. Ex: [x] 2026-05-22
- Se abrir um item novo, indicar o responsavel entre colchetes. Ex: [joao]

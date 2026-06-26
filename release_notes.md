## Requisições App v1.4.0

### Novidades

- **Sidebar redimensionável** — arraste a borda direita da sidebar para ajustar a largura ao seu gosto, estilo VSCode. A largura é salva entre sessões.
- **Titlebar temática** — barra de título customizada com botões de minimizar, maximizar e fechar nas cores do tema escolhido (claro ou escuro).
- **Tray icon do servidor** — o servidor FastAPI agora roda com ícone na bandeja do sistema (system tray), com menu para iniciar/parar e ver o status sem abrir janelas.
- **Verificação de atualização periódica** — o app verifica novas versões automaticamente em segundo plano e avisa quando há update disponível, sem precisar reiniciar.
- **Radar Comparativo multi-visão** — o Radar no Painel Gerencial vira um painel empilhável: adicione e remova visões (Destinos, Top Vendedores, Recentes, etc.) independentemente. Começa vazio para o gerente montar do jeito que preferir.
- **Tour guiado reescrito** — o Guia Rápido foi completamente refeito com cobertura total por perfil. Cada função (Vendedor, Gerente, A&R, Pinheiro Indústria, Entregas) tem um tour dedicado que cobre todas as telas acessíveis.
- **Exportar desenho como PNG** — além de JSON, o editor de desenho agora exporta a arte como imagem PNG direto para a pasta compartilhada da rede.
- **Coluna "Data Prevista de Entrega" na produção** — as tabelas de A&R e Pinheiro Indústria mostram a data de entrega de cada requisição/parcela diretamente na listagem.
- **Cronograma semanal de Entregas** — a tela Entregas ganhou um toggle entre vista Lista e Cronograma semanal, com código de cores por status e botão Criar integrado.
- **Mostrar quem cancelou** — a Central de Pedidos (aba Cancelados) exibe o nome do usuário responsável pelo cancelamento de cada requisição.
- **Colunas auto-expandem ao conteúdo** — todas as tabelas do sistema crescem automaticamente para acomodar o texto ao carregar dados, sem perder o redimensionamento manual.

### Melhorias

- **Tela de A&R / Pinheiro Indústria reformulada** — dropdown de máquinas substitui o seletor horizontal; cards com pills de status (Na Fila / Em Produção / Finalizadas) e contadores no combo; mini-tabela "Aguardando na Fila" por máquina; botões em duas linhas para evitar corte em telas menores.
- **Recebimento por atribuição de itens** — ao receber uma requisição, é possível atribuir cada item a uma máquina específica na hora, sem precisar editar depois.
- **Prazo de entrega por parcela** — alterar o prazo em A&R ou Pinheiro agora afeta apenas a parcela selecionada, não a requisição inteira.
- **Finalizar parcelas em qualquer ordem** — removida a regra FIFO de finalização; cada parcela pode ser finalizada independentemente das demais.
- **Canvas: importar sem apagar** — importar um desenho existente agora adiciona ao canvas atual em vez de substituir tudo. Confirmação antes de sobrescrever.
- **Ferramentas do canvas em 2 por linha** — a toolbar vertical do editor de desenho exibe as ferramentas em grade 2×N, desfazer/refazer acima de Selecionar, aproveitando melhor o espaço.
- **Caixa "O que há de novo" aprimorada** — a janela de atualização disponível ganhou scrollbar com gradiente neon, títulos coloridos por nível (azul para seções, rosa para subtítulos) e tipografia mais legível.
- **Filtro de status no Histórico** — reduzido para os 6 status operacionais mais usados, eliminando entradas redundantes.

### Correções

- Guia rápido funcionando corretamente para todos os perfis, incluindo A&R, Pinheiro Indústria e Entregas.
- Cor da titlebar no tema claro: texto e botões agora ficam pretos (não brancos sobre fundo claro).
- Historico: label corrigida de "Finalizada na Produção" para "Finalizado".
- Botão renomeado de "Apenas salvar" para "Salvar" no diálogo de faturamento.
- Criação de múltiplos splits (partes de produção) corrigida — sem duplicação de itens.
- Thread de PDF não gerava double-deleteLater ao fechar requisição rapidamente.
- Entregas: cor verde para registros já entregues no cronograma; ortografia e capitalização corrigidas no formulário Criar.
- Tempo médio por máquina no Painel Gerencial agora considera apenas requisições finalizadas (não em produção).
- Contadores do combo de máquinas sempre visíveis, mesmo com valor zero.

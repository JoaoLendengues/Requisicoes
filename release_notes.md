## Requisições App v1.2.0

### Novas Funcionalidades

- **Guia Rápido expandido** — tour interativo com passos contextuais em todas as telas do sistema. Cada perfil de acesso (Admin, Gerente, Vendedor, Produção, Indústria, Entrega) percorre apenas as telas e funcionalidades disponíveis para ele.
- **Botão `?` em todas as telas** — acesse o Guia Rápido a qualquer momento diretamente da tela em que você está.
- **Scroll automático no tour** — o tour rola automaticamente a tela para exibir o widget destacado, mesmo quando ele está abaixo da área visível (A&R, Pinheiro Indústria e outras telas com conteúdo longo).
- **Canvas: imagens por arrastar e colar** — arraste uma imagem para o editor de desenho ou cole direto da área de transferência.
- **Canvas: seleção de borda em formas** — ao selecionar um retângulo ou elipse, apenas a borda é sensível ao clique (comportamento hollow), facilitando a seleção de formas sobrepostas.
- **Canvas: ferramenta Curva reescrita** — curva de Bézier no estilo Paint: arrasta a linha base, move o ponto de controle e clica para confirmar.

### Melhorias

- **Configurações: mini-abas horizontais** — a tela de configurações ganhou abas organizadas por categoria: Aparência, Conta, Sistema, Login, Backup e Ajuda. Cada perfil vê apenas as abas pertinentes.
- **Performance: carregamento sob demanda** — todas as telas são criadas apenas na primeira navegação, reduzindo o tempo de abertura do aplicativo.

### Correções

- **Tour guiado: telas em branco** — as telas não apareciam no fundo durante o tour. Corrigido: as views são instanciadas antes de serem exibidas.
- **Tour guiado: abas de Configurações incompletas** — somente Aparência e Conta eram exibidas para o Admin. Agora todas as abas são percorridas conforme o perfil.
- **Backup: endpoint de configurações** — o endpoint `PATCH /backup/settings` retornava erro 404. Corrigido com modelo Pydantic correto no servidor.
- **PDF: erros de rede** — mensagens de erro mais claras ao gerar PDF quando a pasta de rede está inacessível (WinError 1326, 5 e 53).

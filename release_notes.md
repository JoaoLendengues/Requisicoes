## Requisições App v1.3.0

### Novidades

- **Editor de desenho com 3 modos de toolbar** — escolha em *Configurações → Aparência → Editor de Desenho* entre **Clássico** (barra horizontal antiga), **Técnico** (barra vertical flutuante no canto, padrão) e **Escritório** (barra vertical fixa na lateral). Cada perfil escolhe o que prefere.
- **Toolbar vertical no canvas** — uma única coluna estreita no canto superior esquerdo, com scroll automático quando o conteúdo passa da altura da tela. Animação "gaveta + cascata" preservada ao abrir/fechar.
- **Tema escuro/claro instantâneo em todas as telas** — novo sistema interno reaplica os estilos de cada widget automaticamente ao trocar de tema. Antes era preciso fechar e reabrir a tela; agora a mudança é imediata e suave.
- **Ícones novos no sidebar** — Entregas e Atualizações agora têm seus próprios ícones, em vez de reaproveitar os da Central de Pedidos e Configurações.

### Melhorias

- **Caixas de confirmação adaptam-se à escala e tamanho de fonte** — todos os botões (`Apenas salvar`, `Pinheiro Indústria`, `Aguardando na fila`, `Cancelar requisição` etc.) agora respeitam as configurações de tamanho do usuário e nunca mais cortam o texto.
- **Seleção de máquina mais legível** — na tela de A&R / Pinheiro Indústria, ao confirmar uma produção, a lista de máquinas vem com texto centralizado, com nomes longos (`GUILHOTINA`, `NEWTON`, operadores completos) cabendo sempre por inteiro.
- **Tabela "Aguardando na fila"** — margens internas ajustadas para melhorar leitura.
- **Painel Gerencial mais responsivo** — títulos, combos e chips (MENSAL / SEMANAL / DIÁRIO) agora reagem instantaneamente à troca de tema.
- **Entregas: cores e cards** — fundo da view, agenda e botões `ALTERAR PRAZO` / `ENTREGUE` / `CANCELAR ENTREGA` recebem a paleta correta em qualquer tema.

### Correções

- **Ferramenta Selecionar do canvas** — a "caixinha" azul de seleção retangular voltou a funcionar. Estava desativada por engano nos últimos builds.
- **Desenho técnico no PDF** — presets 3D (paralelepípedo, cilindro, pingadeira, rufo, calha, bandeja, cantoneira, chapa, perfil — 87 ao todo) e qualquer caneta vetorial com curvas agora reproduzem no PDF exatamente o que está na prévia. Antes, formas com múltiplos sub-traços apareciam "tortas" no PDF.
- **Painel Gerencial e Entregas: fundo escuro residual** — ao trocar do escuro para o claro (ou vice-versa) com essas telas abertas, áreas entre os cards mantinham a cor do tema antigo. Resolvido.
- **Logo da sidebar** — o topo da sidebar não mudava de cor com o tema. Resolvido.
- **Painel Gerencial: títulos sumindo** — IAR GERAL, RADAR COMPARATIVO, Prazo, Produtividade e Cancelamentos não eram mais visíveis depois de trocar tema. Resolvido com cor explícita nos labels.

### Sob o capô

- Sistema unificado de **registry de tema** (`theme.themed`) — qualquer widget novo declarado com esse helper se atualiza automaticamente em toda troca de tema, sem precisar manter listas de reaplicação manual em cada view.
- Pipeline de desenho do PDF agora preserva **sub-paths e curvas Bézier** via deserialização por `segments` (cmd M/L/C), mantendo paridade pixel-com-pixel entre prévia e PDF.
- Limpeza de assets de desenvolvimento (`tmp_3d_previews/`) e regra `tmp_*/` no `.gitignore` para evitar vazamento futuro.

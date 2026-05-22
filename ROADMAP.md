# Roadmap de Mudanças — Ferragens Pinheiro

Registro de melhorias e ajustes a serem aplicados no decorrer do desenvolvimento.

---

## Pendentes

<<<<<<< Updated upstream
### 1. Calculadora de Peso
Adicionar uma calculadora de peso acessível dentro do formulário de requisição.
=======
### Prioridade Alta
- [ ] Ajustar filtro de datas da tela "HISTORICO/BUSCA" (esta puxando datas anteriores, nao somente a data selecionada)
- [ ] Corrigir bug da tela de desenho: linha iniciando em ponto pre-definido
- [ ] Ajustar contador de notificacoes na tela de notificacoes
- [ ] Arrumar o fuso horario do sistema
>>>>>>> Stashed changes

- O resultado **não alimenta nenhum campo** da requisição — é apenas para controle pessoal dos vendedores.
- Pensar no formato: botão flutuante, painel lateral ou dialog modal.

---

### 3. Remover Peso Total da Segunda Grade
Remover o campo/label **Peso Total** da segunda grade de informações da tela de Nova Requisição.

<<<<<<< Updated upstream
---

### 4. Remover Peso da Tabela de Itens
Remover a coluna **Peso** da segunda linha da tabela de itens da requisição.

---
=======
### Prioridade Alta
- [ ] Implementar sistema de atualizacoes (publicar versoes no GitHub e gerar executavel com Inno Setup)
- [ ] Refinar niveis de acesso
- [ ] Implementar sistema de backup periodico do banco de dados

### Prioridade Media
- [ ] Melhorar personalizacao da tela de configuracao
- [ ] Colocar emojis na impressao dos PDFs
- [ ] No PDF, alinhar mais a esquerda o titulo "Requisicao", data e nome do vendedor, aproximando de telefones, email e SIA/TAGUATINGA
- [ ] Implementar filtro por vendedor na tela "HISTORICO/BUSCA"
- [ ] Polimento de experiencia de usuario e performance do sistema
- [ ] Adicionar ferramenta Curva no editor de desenho, com atalho de teclado na letra "C"

### Prioridade Baixa
- [ ] Polimento geral do app
- [ ] Revisao geral do codigo
>>>>>>> Stashed changes

### 6. Código do Produto na Tabela de Itens
Adicionar coluna **Código do Produto** ao lado da coluna **Posição** na tabela de itens.

- O código deve ser puxado da planilha de cadastros (ODS/Excel já importada).
- Pensar em autocomplete ou lookup pelo código.

---

### 8. Botão "Encaminhar para Produção"
Adicionar botão para encaminhar a requisição para a produção, com seleção de destino:

- **A&R**
- **Pinheiro Indústria**

- Pensar no fluxo: o status muda para "Em Produção" ao encaminhar?
- O destino selecionado deve ficar registrado na requisição.

---

---

### 2. Mais Opções de Personalização (Configurações)
Pensar e implementar novas opções na tela de Configurações. Sugestões iniciais:

- Tema claro / escuro
- Nome e unidade do vendedor padrão
- Configuração de colunas visíveis na listagem
- Outras preferências de exibição

---

## Concluídos

| Data | Descrição |
|------|-----------|
| 2026-05-16 | Geração automática de PDF ao salvar requisição |
| 2026-05-16 | Campo de Observações persistido no banco e no formulário |
| 2026-05-16 | Fix thread safety no salvamento (callbacks na main thread) |
| 2026-05-16 | Pasta de PDFs configurável nas Configurações |
| 2026-05-16 | Status simplificados: Em Andamento / Em Produção / Cancelada |
| 2026-05-16 | Histórico exibe nome do cliente e vendedor (em vez dos IDs) |
| 2026-05-16 | Sidebar reorganizada: Nova Req → Dashboard → Histórico → Config |
| 2026-05-16 | Botão ENVIAR WHATSAPP movido para dentro do formulário |
| 2026-05-16 | Botão GERAR PDF removido do sidebar |
| 2026-05-16 | Retirada × Entrega mutuamente exclusivos (já estava implementado) |
| 2026-05-16 | QR Code com WhatsApp do vendedor exibido na tela de Nova Requisição |
| 2026-05-18 | Salvamento bloqueado sem número de PED válido |
| 2026-05-19 | Grade quadriculada no canvas (visual only, drawBackground) |
| 2026-05-19 | Pan por botão do meio e Space+drag no canvas |
| 2026-05-19 | Borracha, linhas pontilhadas/tracejadas no canvas |
| 2026-05-19 | Rotação por grau via toolbar + persistência JSON |
| 2026-05-19 | Alça de rotação livre (arrastar círculo ↻ azul acima do item) |
| 2026-05-19 | Edição inline de texto (duplo clique) |
| 2026-05-19 | Tamanho da fonte ao vivo em textos já colocados (spin_font sincronizado) |

# Roadmap de Mudanças — Ferragens Pinheiro

Registro de melhorias e ajustes a serem aplicados no decorrer do desenvolvimento.

---

## Pendentes

### 1. Calculadora de Peso
Adicionar uma calculadora de peso acessível dentro do formulário de requisição.

- O resultado **não alimenta nenhum campo** da requisição — é apenas para controle pessoal dos vendedores.
- Pensar no formato: botão flutuante, painel lateral ou dialog modal.

---

### 3. Remover Peso Total da Segunda Grade
Remover o campo/label **Peso Total** da segunda grade de informações da tela de Nova Requisição.

---

### 4. Remover Peso da Tabela de Itens
Remover a coluna **Peso** da segunda linha da tabela de itens da requisição.

---

### 5. Bloquear Salvamento sem Número de Pedido
Não permitir salvar a requisição se o campo **PED** estiver vazio ou igual a zero.

- Exibir aviso claro ao vendedor antes de bloquear o salvamento.

---

### 6. Código do Produto na Tabela de Itens
Adicionar coluna **Código do Produto** ao lado da coluna **Posição** na tabela de itens.

- O código deve ser puxado da planilha de cadastros (ODS/Excel já importada).
- Pensar em autocomplete ou lookup pelo código.

---

### 7. QR Code com Número do Vendedor (WhatsApp)
Gerar QR Code que linka diretamente para o WhatsApp do vendedor logado.

- QR Code deve aparecer na tela de Nova Requisição.
- Ao escanear, deve abrir conversa no WhatsApp com o número do vendedor.

---

### 8. Botão "Encaminhar para Produção"
Adicionar botão para encaminhar a requisição para a produção, com seleção de destino:

- **A&R**
- **Pinheiro Indústria**

- Pensar no fluxo: o status muda para "Em Produção" ao encaminhar?
- O destino selecionado deve ficar registrado na requisição.

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

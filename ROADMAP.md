# Roadmap de Mudanças — Ferragens Pinheiro

Registro de melhorias e ajustes a serem aplicados no decorrer do desenvolvimento.

---

## Pendentes

### 1. Status de Produção
Ajustar os status disponíveis no fluxo de produção para:
- **Em Andamento**
- **Cancelada**
- **Em Produção**

> Verificar impacto no histórico de status e nos filtros da listagem.

---

### 2. Calculadora de Peso
Adicionar uma calculadora de peso acessível dentro do formulário de requisição.

- O resultado **não alimenta nenhum campo** da requisição — é apenas para controle pessoal dos vendedores.
- Pensar no formato: botão flutuante, painel lateral ou dialog modal.

---

### 3. Retirada × Entrega — Comportamento Exclusivo
Na tela de Nova Requisição, os botões/checkboxes de **Retirada** e **Entrega** devem se comportar de forma mutuamente exclusiva:

- Ao marcar **Retirada → Sim**, **Entrega** muda automaticamente para **Não**.
- Ao marcar **Entrega → Sim**, **Retirada** muda automaticamente para **Não**.

---

### 4. Mais Opções de Personalização (Configurações)
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

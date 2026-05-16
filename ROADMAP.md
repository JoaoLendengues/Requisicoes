# Roadmap de Mudanças — Ferragens Pinheiro

Registro de melhorias e ajustes a serem aplicados no decorrer do desenvolvimento.

---

## Pendentes

### 1. Calculadora de Peso
Adicionar uma calculadora de peso acessível dentro do formulário de requisição.

- O resultado **não alimenta nenhum campo** da requisição — é apenas para controle pessoal dos vendedores.
- Pensar no formato: botão flutuante, painel lateral ou dialog modal.

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

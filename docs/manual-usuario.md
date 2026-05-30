# Manual do Usuário — Requisições App
**Ferragens Pinheiro** | Versão 1.1.0

---

## Sumário

1. [Primeiro acesso e login](#1-primeiro-acesso-e-login)
2. [Tela principal e navegação](#2-tela-principal-e-navegação)
3. [Central de Pedidos](#3-central-de-pedidos)
4. [Criando uma nova requisição](#4-criando-uma-nova-requisição)
5. [Editor de desenho](#5-editor-de-desenho)
6. [Histórico de requisições](#6-histórico-de-requisições)
7. [Notificações](#7-notificações)
8. [Calculadora de peso](#8-calculadora-de-peso)
9. [Configurações](#9-configurações)
10. [Guia Rápido](#10-guia-rápido)
11. [Perfis de acesso](#11-perfis-de-acesso)
12. [Perguntas frequentes](#12-perguntas-frequentes)

---

## 1. Primeiro acesso e login

### Abrindo o sistema

Clique duas vezes no ícone **Requisições App** na área de trabalho ou na barra de tarefas.

### Fazendo login

1. Digite seu **código de usuário** no primeiro campo.
2. Digite sua **senha** no segundo campo.
3. Clique em **Entrar** ou pressione **Enter**.

> **Primeiro acesso:** Se for a primeira vez que você usa o sistema, será solicitado que você crie uma nova senha. Isso só acontece uma vez.

### Esqueci minha senha

Entre em contato com o administrador do sistema para redefinição de senha.

---

## 2. Tela principal e navegação

Após o login, você verá a tela principal com a **barra lateral (sidebar)** à esquerda.

### Sidebar

A sidebar exibe apenas as telas disponíveis para o seu perfil. Os botões de navegação incluem:

| Ícone | Tela | Disponível para |
|-------|------|-----------------|
| 📊 | Dashboard | Admin, Gerente |
| 📋 | Central de Pedidos | Todos |
| 🏭 | A&R / Indústria | Producao, Indústria, Admin, Gerente |
| 👥 | Gestão de Usuários | Admin |
| 🔧 | Painel Técnico | Admin |
| 🕐 | Histórico | Todos |
| 💬 | Feedback | Todos |
| ⚙️ | Configurações | Todos |

### Alternando tema (claro/escuro)

Clique no ícone de **lua/sol** na parte inferior da sidebar para alternar entre modo claro e escuro.

### Notificações

O ícone de **sino** na sidebar exibe o número de notificações não lidas. Clique nele para abrir o painel de notificações.

---

## 3. Central de Pedidos

A Central de Pedidos é a tela principal do sistema, onde você visualiza, cria e gerencia as requisições.

### Visualizando requisições

- A tabela exibe todas as requisições disponíveis para o seu perfil.
- Clique no cabeçalho de qualquer coluna para **ordenar**.
- Use a barra de busca no topo para **filtrar** por cliente, número do pedido ou vendedor.

### Status das requisições

| Status | Significado |
|--------|-------------|
| 🔵 Em andamento | Requisição em elaboração ou aguardando |
| 🟡 Aguardando recebimento | Material aguardando chegada |
| 🟠 Em produção | Em processamento pela A&R ou Indústria |
| 🟢 Faturado | Pedido faturado e concluído |
| 🔴 Cancelada | Requisição cancelada |

### Abrindo uma requisição

- **Duplo clique** na linha da tabela para abrir a requisição.
- Usuários com perfil de **visualização** (A&R, Indústria, Entrega) podem ver os detalhes mas não editar.

---

## 4. Criando uma nova requisição

> Disponível para: **Vendedor**, **Gerente**, **Admin**

### Passo a passo

1. Na Central de Pedidos, clique no botão **+ Nova Requisição**.
2. **Busque o cliente** digitando nome, código ou CNPJ no campo de busca. Um menu vai aparecer com as sugestões — clique no cliente desejado.
3. Preencha o **número do pedido** (campo PED).
4. Informe se é **retirada** ou **entrega**.
5. **Adicione os itens:**
   - Clique em **+ Adicionar Item**.
   - Busque o produto pelo código ou nome.
   - Informe a quantidade e o preço unitário.
   - Repita para quantos itens forem necessários.
6. Adicione **observações** se necessário.
7. Clique em **Salvar**. O PDF será gerado automaticamente e enviado para a pasta de rede.

### Editor de desenho

Dentro do formulário, clique em **Abrir Editor de Desenho** para adicionar um croqui, medidas ou anotações visuais à requisição. Veja a seção [5. Editor de desenho](#5-editor-de-desenho) para mais detalhes.

---

## 5. Editor de desenho

O editor de desenho permite criar croquis, anotações e medidas diretamente na requisição.

### Abrindo o editor

No formulário de requisição, clique no botão **Desenho** ou no ícone de caneta.

### Ferramentas disponíveis

| Ferramenta | Atalho | Função |
|------------|--------|--------|
| Seleção | **S** | Seleciona e move elementos |
| Caneta | **P** | Desenho livre |
| Linha | **L** | Linha reta com snap nos extremos |
| Seta | **A** | Linha com ponta de seta |
| Retângulo | **R** | Retângulo |
| Triângulo | **T** | Triângulo |
| Texto | **X** | Inserir texto |
| Cota MM | **M** | Medida em milímetros com rótulo automático |
| Borracha | **E** | Apagar elementos |

### Navegação no canvas

- **Scroll do mouse** — zoom in/out
- **Botão do meio pressionado** — arrastar o canvas (pan)
- **Grade** — visível como guia de alinhamento

### Dicas

- Pressione **Esc** para desmarcar a ferramenta ativa sem fechar o editor.
- A ferramenta **Cota MM** posiciona o rótulo automaticamente para evitar sobreposição com outros elementos.
- Use **Ctrl+T** para transformar livremente um elemento selecionado (mover, redimensionar, rotacionar).
- Os desenhos aparecem no PDF gerado.

### Salvando

Clique em **Salvar** no editor ou feche — o conteúdo é salvo junto com a requisição.

---

## 6. Histórico de requisições

O histórico exibe todas as requisições do sistema, independentemente do status.

### Filtros disponíveis

- **Data:** filtre por intervalo de datas.
- **Status:** filtre por um ou mais status.
- **Vendedor/Cliente:** busca por texto.

### Exportando

Clique em **Exportar** para gerar um arquivo Excel com os resultados filtrados.

---

## 7. Notificações

O sistema envia notificações em tempo real para eventos importantes.

### Tipos de notificação

- Nova requisição criada
- Mudança de status em uma requisição
- Alertas do sistema

### Acessando notificações

- O **badge vermelho** no sino da sidebar indica notificações não lidas.
- Clique no sino para abrir o **painel lateral** com todas as notificações.
- Notificações novas aparecem como **toasts** (pop-ups) no canto da tela.

### Marcando como lida

Clique na notificação no painel para marcá-la como lida. O badge é atualizado automaticamente.

---

## 8. Calculadora de peso

A calculadora de peso calcula a massa de materiais metálicos com base em dimensões.

### Acessando

Clique no ícone de **calculadora** na sidebar.

### Como usar

1. Selecione o **tipo de perfil** (chato, quadrado, redondo, tubo etc.).
2. Informe as **dimensões** em milímetros.
3. Informe o **comprimento** em metros.
4. O resultado em **kg** é exibido automaticamente.

> O valor da variável (densidade do aço = 7,865 g/cm³) é fixo e não pode ser alterado.

---

## 9. Configurações

### Acessando

Clique no ícone de **engrenagem** na sidebar.

### Opções disponíveis

| Opção | Função |
|-------|--------|
| Tema | Alterna entre claro e escuro |
| Tamanho da fonte | Ajusta o tamanho da fonte da interface |
| Pasta de backgrounds | Define a pasta de imagens de fundo do login (rede) |
| Alerta de vencimento | Define quantos dias antes de alertar sobre notas a vencer |
| Alterar senha | Permite alterar sua senha de acesso |
| Ver Guia Rápido | Abre o tour interativo do sistema |
| Verificar atualizações | Verifica se há uma nova versão disponível |

---

## 10. Guia Rápido

O Guia Rápido é um tour interativo que apresenta as principais funcionalidades do sistema.

### Quando aparece

Na **primeira vez** que você faz login, o guia aparece automaticamente.

### Abrindo novamente

Vá em **Configurações → Ver Guia Rápido** a qualquer momento.

### Como navegar

- Use os botões **Próximo** e **Anterior** para avançar ou voltar.
- Clique em **Fechar** para encerrar o tour.
- O guia destaca o elemento relevante na tela com uma animação de foco.

---

## 11. Perfis de acesso

O sistema possui seis perfis, cada um com permissões específicas:

| Perfil | O que pode fazer |
|--------|-----------------|
| **Admin** | Acesso total ao sistema, incluindo gestão de usuários, painel técnico e configurações avançadas |
| **Gerente** | Acesso ao dashboard, central de pedidos, histórico e configurações. Pode gerenciar usuários |
| **Vendedor** | Criar, editar e acompanhar suas próprias requisições. Acesso ao histórico |
| **Produção (A&R)** | Visualizar requisições e a tela de A&R em modo leitura |
| **Indústria** | Visualizar requisições e a tela de Indústria em modo leitura |
| **Entrega** | Visualizar requisições da Central de Pedidos em modo leitura |

---

## 12. Perguntas frequentes

**O PDF não foi gerado. O que fazer?**
Verifique se o caminho da pasta de PDFs está acessível na rede. Contate o administrador se o problema persistir.

**Não consigo ver determinada tela.**
Cada perfil tem acesso apenas às telas pertinentes à sua função. Se precisar de acesso adicional, entre em contato com o administrador.

**O sistema avisou que há uma atualização disponível. Posso instalar?**
Sim. Clique em **Atualizar agora** na janela que aparece. O sistema vai baixar, aplicar a atualização e reabrir automaticamente. Seus dados e configurações são preservados.

**A busca de clientes está lenta.**
A busca é feita em tempo real. Se a conexão com o servidor estiver lenta, pode haver um pequeno atraso. Aguarde alguns segundos e tente novamente.

**Esqueci minha senha.**
Entre em contato com o administrador do sistema para redefinição.

---

*Documento gerado em maio de 2026 — Ferragens Pinheiro | Requisições App v1.1.0*

# Proposta Comercial e Jurídica
## Requisições App - Ferragens Pinheiro

**Data:** 28/05/2026  
**Versão de referência do sistema:** v1.1.0  
**Contratante:** [preencher razão social / CNPJ]  
**Contratada:** [preencher razão social / CNPJ]

---

## 1. Objeto

A presente proposta tem por objeto a formalização comercial do **Requisições App**, sistema interno desenvolvido para gestão de requisições, acompanhamento de pedidos, geração automática de PDFs, controle de acesso por perfis, notificações em tempo real, backup de banco de dados e atualização automatizada da aplicação.

O sistema, conforme a documentação técnica do projeto, contempla arquitetura composta por:

- cliente desktop em `Python + PySide6`
- API em `FastAPI`
- banco de dados `PostgreSQL`
- autenticação por `JWT`
- geração de PDF
- notificações em tempo real
- rotinas de backup
- mecanismo de atualização por release

---

## 2. Escopo contemplado nesta proposta

Esta proposta considera a entrega da solução atualmente documentada, incluindo:

- central de pedidos e gestão de requisições
- cadastro e busca de clientes
- cadastro e gestão de usuários com perfis de acesso
- histórico de requisições com filtros e exportações
- editor de desenho/croqui vinculado à requisição
- geração automática de PDF
- notificações em tempo real
- backup automatizado do banco
- instalador e processo de atualização da aplicação
- documentação técnica e manual do usuário já existentes

Não estão incluídos, salvo contratação adicional:

- novas funcionalidades não previstas na versão atual
- integrações externas adicionais
- manutenção evolutiva ilimitada
- hospedagem em nuvem de terceiros
- suporte fora da janela comercial acordada

---

## 3. Modelo comercial recomendado

### Opção A - Licença de uso + implantação

Modelo recomendado quando o desenvolvedor deseja **manter a titularidade do código-fonte** e conceder ao cliente uma licença de uso para operação interna do sistema.

| Item | Descrição | Valor |
|---|---|---:|
| 1 | Licença de uso perpétua, não exclusiva, da versão atual do `Requisições App` para uso interno da contratante | **R$ 42.000,00** |
| 2 | Implantação, parametrização, publicação em ambiente do cliente e validação operacional inicial | **R$ 8.000,00** |
| 3 | Treinamento de usuários-chave, repasse operacional e apoio de entrada em produção | **R$ 6.000,00** |
| 4 | Garantia de correções por 90 dias para falhas da versão entregue | **Incluso** |

**Total da implantação inicial:** **R$ 56.000,00**

### Suporte mensal opcional

| Item | Descrição | Valor |
|---|---|---:|
| Suporte mensal | Correções, ajustes pontuais e atendimento remoto de até 12 horas/mês | **R$ 2.200,00/mês** |
| Hora adicional | Demandas excedentes ou evolutivas fora da franquia mensal | **R$ 180,00/hora** |

---

## 4. Opção alternativa

### Opção B - Cessão patrimonial do software

Modelo indicado quando a negociação exigir **transferência dos direitos patrimoniais do software**, com cessão contratual do ativo intelectual ao cliente.

| Item | Descrição | Valor |
|---|---|---:|
| 1 | Cessão patrimonial do código-fonte, artefatos de build, instalador e documentação do sistema na versão atual | **R$ 95.000,00** |
| 2 | Implantação, parametrização, publicação em ambiente do cliente e validação operacional inicial | **R$ 8.000,00** |
| 3 | Treinamento de usuários-chave, repasse operacional e apoio de entrada em produção | **R$ 6.000,00** |
| 4 | Garantia de correções por 90 dias para falhas da versão entregue | **Incluso** |

**Total da cessão + implantação:** **R$ 109.000,00**

### Observação importante

O valor da cessão é superior ao da licença porque envolve alienação do ativo intelectual, limitação de reuso econômico pelo desenvolvedor e maior exposição jurídica sobre titularidade, manutenção e exploração futura.

---

## 5. Item opcional recomendado

| Item | Descrição | Valor |
|---|---|---:|
| Registro de software | Preparação do material para protocolo de registro de programa de computador perante o INPI | **R$ 2.500,00 + taxas oficiais** |

Observação: o registro não é requisito para a proteção jurídica do software, mas é recomendável como reforço probatório sobre autoria, data e titularidade.

---

## 6. Condições comerciais sugeridas

- validade da proposta: `15 dias`
- forma de pagamento da implantação: `40% na assinatura`, `40% na disponibilização para homologação`, `20% na entrada em produção`
- suporte mensal: faturamento recorrente mensal, mediante contrato específico
- valores em reais
- tributos incidentes serão tratados conforme o regime fiscal da contratada e retenções legais aplicáveis

---

## 7. Prazos sugeridos

- implantação inicial: `10 a 20 dias úteis`, conforme disponibilidade do ambiente do cliente
- treinamento: `1 a 2 dias`
- início do suporte: imediatamente após aceite da implantação ou assinatura do contrato mensal

---

## 8. Bases legais principais

### 8.1. Lei do Software - Lei nº 9.609/1998

Base principal para a proteção do programa de computador no Brasil.

- **Art. 2º:** o regime de proteção da propriedade intelectual do programa de computador segue a lógica autoral aplicável às obras intelectuais, com as especificidades da Lei do Software.
- **Art. 3º:** a proteção do software independe de registro, embora o registro possa ser feito para fins probatórios.
- **Art. 4º:** salvo estipulação em contrário, os direitos relativos ao programa desenvolvido no contexto de contrato de trabalho ou de prestação de serviços podem pertencer ao empregador ou contratante.
- **Art. 9º:** o uso de programa de computador no País deve ser objeto de contrato de licença.

Aplicação prática nesta proposta:

- a **Opção A** deve ser formalizada como **licença de uso**
- a **Opção B** deve conter cláusula expressa de **cessão patrimonial**
- antes de fechar qualquer uma das modalidades, é essencial confirmar a cadeia de titularidade do software

### 8.2. Lei de Direitos Autorais - Lei nº 9.610/1998

Aplica-se de modo complementar, especialmente para disciplinar exploração econômica, autorização de uso e cessão escrita dos direitos patrimoniais.

Aplicação prática nesta proposta:

- a exploração econômica do software e de sua documentação deve constar por escrito
- a aquisição do executável, acesso ao código ou entrega de arquivos não substitui cláusula formal de licença ou cessão

### 8.3. Código Civil - Lei nº 10.406/2002

Base contratual geral para formação, execução e interpretação do negócio.

- **Art. 421:** função social do contrato
- **Art. 422:** boa-fé objetiva e probidade na conclusão e execução
- **Art. 425:** possibilidade de contratos atípicos, desde que observadas as normas gerais
- **Art. 427:** a proposta obriga o proponente, salvo ressalvas do próprio instrumento

Aplicação prática nesta proposta:

- recomenda-se contrato escrito com escopo, limites, aceite, preço, prazo, suporte, confidencialidade e responsabilidade

### 8.4. LGPD - Lei nº 13.709/2018

Aplica-se porque o sistema trata dados pessoais de usuários, clientes, operadores e histórico de ações.

Pontos centrais:

- definição das partes como `controlador` e `operador`, conforme o papel de cada uma no tratamento
- necessidade de base legal adequada para o tratamento dos dados pessoais
- adoção de medidas de segurança técnicas e administrativas
- dever de resposta em caso de incidente de segurança relevante

Aplicação prática nesta proposta:

- o contrato deve definir quem decide as finalidades do tratamento
- a contratada deve atuar apenas nos limites do escopo técnico contratado
- convém prever cláusula específica de confidencialidade, segurança, retenção e incidente

### 8.5. Marco Civil da Internet - Lei nº 12.965/2014

Aplica-se de forma complementar em tudo que envolver uso de aplicação conectada, registros, acesso, segurança e eventual fornecimento de informações por ordem legal.

Aplicação prática nesta proposta:

- manter política mínima de registro e segurança compatível com a operação do sistema
- disciplinar em contrato como serão tratados logs, acessos administrativos e solicitações legais

---

## 9. Cláusulas que recomendamos constar no contrato

- identificação completa das partes
- descrição objetiva do sistema e da versão contratada
- definição expressa entre `licença` ou `cessão`
- preço, forma de pagamento e marco de aceite
- escopo do suporte e do que fica fora dele
- obrigação de confidencialidade
- cláusula de proteção de dados pessoais
- responsabilidade por ambiente, infraestrutura, backup e credenciais
- limitação de responsabilidade por indisponibilidade causada por infraestrutura do cliente
- regras para customizações futuras e cobrança de evolutivas
- tratamento de componentes de terceiros e bibliotecas open source
- eleição de foro

---

## 10. Ponto crítico de titularidade

Existe um ponto jurídico que deve ser verificado antes do envio definitivo desta proposta:

Se este software foi desenvolvido:

- dentro de vínculo empregatício
- dentro de contrato de prestação de serviços com escopo de desenvolvimento
- com recursos, equipamentos, informações internas ou atribuições diretamente ligadas ao cargo ou contrato

então a titularidade pode já estar, total ou parcialmente, submetida ao **art. 4º da Lei nº 9.609/1998**.

Por isso, antes de negociar como `licença` ou `cessão`, recomenda-se revisar:

- contrato de trabalho ou prestação de serviços
- ordens de serviço e e-mails de escopo
- uso de equipamentos e infraestrutura da empresa
- participação de outros desenvolvedores no código

Se houver dúvida sobre isso, a proposta comercial deve ser acompanhada de validação jurídica formal.

---

## 11. Observação sobre componentes de terceiros

As dependências de terceiros utilizadas no projeto permanecem sujeitas às respectivas licenças de software open source e não integram, por si só, cessão exclusiva de titularidade pela contratada.

Assim, a cessão ou licença aqui tratada deve recair sobre:

- código autoral próprio do projeto
- regras de negócio implementadas
- documentação própria
- instaladores, scripts e artefatos autorais do projeto

---

## 12. Texto curto pronto para envio

Segue sugestão de texto comercial resumido:

> Apresentamos proposta para formalização do sistema `Requisições App`, solução interna de gestão de requisições composta por aplicação desktop, API FastAPI e banco PostgreSQL, contemplando controle de pedidos, perfis de acesso, geração automática de PDF, notificações em tempo real, backup automatizado e atualização do sistema.
>
> Na modalidade recomendada de **licença de uso perpétua, não exclusiva**, o valor total para disponibilização da versão atual, implantação, treinamento e entrada em produção é de **R$ 56.000,00**, com **90 dias de garantia** para correções da versão entregue. O suporte mensal opcional poderá ser contratado por **R$ 2.200,00/mês**.
>
> Caso haja interesse em **cessão patrimonial do software**, com transferência dos direitos patrimoniais da versão atual, o valor total passa para **R$ 109.000,00**, mantidas as condições de implantação e garantia.
>
> A contratação deverá ser formalizada por instrumento escrito, com cláusulas de titularidade intelectual, licença ou cessão, confidencialidade, proteção de dados e suporte, nos termos da Lei nº 9.609/1998, Lei nº 9.610/1998, Código Civil e LGPD.

---

## 13. Fontes legais consultadas

- Lei do Software - Lei nº 9.609/1998: <https://planalto.gov.br/ccivil_03/leis/l9609.htm>
- Lei de Direitos Autorais - Lei nº 9.610/1998: <https://www.planalto.gov.br/ccivil_03/leis/l9610.htm>
- Código Civil - Lei nº 10.406/2002: <https://www.planalto.gov.br/ccivil_03/LEIS/2002/L10406compilada.htm>
- LGPD - Lei nº 13.709/2018: <https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm>
- Marco Civil da Internet - Lei nº 12.965/2014: <https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm>

---

## 14. Recomendação final

Se a intenção for **monetizar o trabalho sem transferir definitivamente o ativo**, a melhor saída jurídica e comercial é usar a **Opção A - Licença de uso + implantação + suporte mensal**.

Se a contratante exigir domínio integral do ativo e do código-fonte, a negociação deve migrar para a **Opção B - Cessão patrimonial**, com preço maior e revisão jurídica obrigatória da titularidade antes da assinatura.

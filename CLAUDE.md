# Notas do projeto

## 🗄️ Banco de produção (PostgreSQL)

**Sempre use estes dados ao referenciar o banco:**

| Campo | Valor |
|-------|-------|
| Servidor | Pinheiro Produção |
| Database | `requisicoes` |
| Host | `10.1.1.151` |
| Porta | `5432` |
| Usuário | `tipinheiro` |
| Senha | `Pinheiro123` |

Conexão completa:
```
postgresql://tipinheiro:Pinheiro123@10.1.1.151:5432/requisicoes
```

**O arquivo `.env` do servidor em `C:\Users\administrator.PINHEIROTG\Requisicoes\` precisa apontar para esse banco.**

## ⚠️ Cuidado histórico

- Houve um SQLite local (`requisicoes.db`) na pasta do servidor que sobrescrevia a conexão PostgreSQL. **Não pode existir esse arquivo na pasta do servidor.**
- A tabela `clients` em produção tem apenas: `id, code, name, cnpj, is_active, created_at, updated_at` (sem cnpj_digits, address, city, state, phone, email).

## 📋 Estrutura das tabelas principais

### `clients` (112.529 registros)
- `id, code, name, cnpj, is_active, created_at, updated_at`

### Enum `requisitionstatus` no banco
- `em_andamento, aguardando_recebimento, em_producao, cancelada`
- Não tem `faturado` no enum

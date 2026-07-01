## Requisições App v1.4.1

### Correções

- **Crash ao trocar tema (claro/escuro)** — a troca de tema quebrava com `AttributeError: 'MainWindow' object has no attribute '_sep'`. Era um resquício da migração da sidebar fixa para a sidebar redimensionável via drag (v1.4.0): o separador antigo (`_sep`) foi substituído pelo handle do splitter, mas uma chamada de estilo órfã continuou apontando para o widget removido. Corrigido — a troca de tema volta a funcionar normalmente em todas as telas.

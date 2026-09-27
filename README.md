# Smart Expense Analyzer

Backend para importar extratos financeiros em CSV, normalizar e categorizar
transações e disponibilizar análises de despesas por meio de uma API REST.

> **Aviso:** projeto mono-usuário, de demonstração e **sem autenticação**. A API
> não deve ser exposta à internet nem a uma rede compartilhada. Veja
> [Segurança e limitações](#segurança-e-limitações).

## Funcionalidades

- importação síncrona de arquivos CSV, com validação por linha e deduplicação;
- categorização automática por regras configuráveis;
- consulta paginada de despesas e receitas;
- totais, média, mediana, histograma e distribuição por categoria e
  estabelecimento;
- série mensal de despesas, separada por moeda;
- detecção de possíveis anomalias pelo método IQR;
- documentação OpenAPI gerada pelo FastAPI;
- ambiente reproduzível com Docker Compose e testes automatizados no CI.

## Tecnologias

- Python 3.12;
- FastAPI e Pydantic v2;
- SQLAlchemy 2 e Alembic;
- PostgreSQL 16;
- pandas e NumPy;
- pytest, Ruff e mypy;
- Docker Compose e GitHub Actions.

## Segurança e limitações

A primeira versão é mono-usuário e **sem autenticação** (decisão LAC-01).
Qualquer cliente que alcance a porta da API lê, cria e altera dados
financeiros. Por isso a API não deve ser exposta à internet nem vinculada a
uma interface de rede pública. O Docker Compose publica a API somente em
`127.0.0.1:8000` e não publica a porta do PostgreSQL.

Riscos conhecidos, aceitos para esta versão e registrados como follow-up:

- **CSRF de rede local (FUP-03):** uma página maliciosa aberta no navegador
  da mesma máquina pode enviar requisições para `http://localhost:8000`. O
  bind em loopback não impede esse cenário.
- **Upload sem limite antes do parse (FUP-03):** o endpoint lê no máximo
  `MAX_UPLOAD_MB` + 1 byte e responde 413 acima do limite, mas o Starlette
  grava o corpo multipart inteiro em arquivo temporário antes disso. Um
  upload muito grande ocupa disco temporário antes de ser rejeitado.
- **Custo de `/analytics/monthly` com período extremo (FUP-05, gravidade
  alta):** a série tem um item por mês do período, sem limite. Um intervalo
  como `0001-01-01` a `9999-12-31` gera cerca de 120 mil meses por moeda,
  com alto custo de memória e tempo, podendo esgotar a memória do processo.

Conversão cambial, interface gráfica, integração bancária/Open Finance e
deploy em produção estão fora do escopo inicial.

## Executando com Docker

Pré-requisitos: Docker e Docker Compose. A partir de um clone limpo:

```bash
cp .env.example .env
docker compose up -d --build
```

As migrações Alembic são aplicadas automaticamente antes da inicialização da
API. Depois disso, ficam disponíveis:

- documentação interativa: <http://localhost:8000/docs>;
- especificação OpenAPI: <http://localhost:8000/openapi.json>;
- verificação de saúde: <http://localhost:8000/health>.

Para encerrar o ambiente:

```bash
docker compose down
```

## Variáveis de ambiente

O arquivo `.env.example` traz valores de desenvolvimento local. Copie-o para
`.env` e troque a senha fora do ambiente local.

| Variável | Obrigatória | Padrão | Descrição |
|---|---:|---|---|
| `DATABASE_URL` | sim | — | URL de conexão PostgreSQL para a API |
| `DEFAULT_CURRENCY` | não | `BRL` | moeda ISO 4217 usada quando o CSV não a informa |
| `MAX_UPLOAD_MB` | não | `10` | tamanho máximo de cada arquivo importado |
| `ANOMALY_IQR_K` | não | `1.5` | multiplicador do IQR para detectar anomalias |
| `ANOMALY_MIN_SAMPLE` | não | `8` | amostra mínima por categoria e moeda |
| `LOG_LEVEL` | não | `INFO` | nível de logging da aplicação |
| `POSTGRES_USER` | sim no Compose | — | usuário do PostgreSQL local |
| `POSTGRES_PASSWORD` | sim no Compose | — | senha do PostgreSQL local |
| `POSTGRES_DB` | sim no Compose | — | banco criado pelo PostgreSQL local |

Nunca versione o arquivo `.env` nem credenciais reais.

## Formato do CSV

O arquivo deve usar UTF-8, vírgula como separador e ponto como separador
decimal. O cabeçalho aceita estas colunas:

| Coluna | Obrigatória | Formato |
|---|---:|---|
| `date` | sim | data no formato `AAAA-MM-DD` |
| `description` | sim | descrição não vazia |
| `amount` | sim | decimal; negativo para despesa e positivo para receita |
| `merchant` | não | estabelecimento; usa a descrição quando estiver vazio |
| `currency` | não | código ISO 4217; usa `DEFAULT_CURRENCY` quando estiver vazio |

Exemplo:

```csv
date,description,amount,merchant,currency
2026-01-05,Supermercado,-152.40,Mercado Central,BRL
2026-01-10,Salario,5000.00,Empresa Exemplo,BRL
2026-01-12,Transporte por aplicativo,-24.90,Mobilidade,BRL
```

Valores iguais a zero são inválidos. Linhas inválidas são rejeitadas
individualmente, enquanto as demais continuam sendo importadas.

## API

| Método | Rota | Finalidade |
|---|---|---|
| `POST` | `/imports` | importar um CSV |
| `GET` | `/transactions` | listar e filtrar transações |
| `GET` | `/transactions/{id}` | consultar uma transação |
| `POST` | `/transactions/recategorize` | reaplicar as regras existentes |
| `POST`, `GET` | `/categories` | criar e listar categorias |
| CRUD | `/categorization-rules` | manter regras de categorização |
| `GET` | `/analytics/summary` | consultar resumo estatístico |
| `GET` | `/analytics/categories` | consultar distribuição por categoria |
| `GET` | `/analytics/monthly` | consultar série mensal |
| `GET` | `/anomalies` | listar possíveis anomalias |

## Desenvolvimento local

Requer Python 3.12. Prepare o ambiente com:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Para verificar o projeto:

```bash
ruff check . --output-format=concise
mypy app
pytest -q
```

O pytest usa o `pytest.ini` da raiz (`pythonpath = .`, `--import-mode=importlib`)
e grava o relatório JUnit em `reports/junit.xml`.

Os testes de integração usam PostgreSQL real por meio de Testcontainers e
exigem Docker em execução. Com colima, pode ser necessário apontar o socket:

```bash
TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock pytest -q
```

Se a variável `TEST_DATABASE_URL` estiver definida, os testes usam esse banco
em vez de subir um contêiner. O CI (GitHub Actions, `.github/workflows/ci.yml`)
roda `ruff`, `mypy` e `pytest` a cada push e pull request, com um serviço
`postgres:16-alpine`, e também valida o build da imagem da API.

## Arquitetura

O projeto segue Clean Architecture, com dependências direcionadas ao
domínio:

```text
app/
├── domain/                 # entidades, regras puras e portas
├── application/services/   # casos de uso
├── infrastructure/         # banco de dados e leitura de CSV
├── api/                    # rotas, schemas e tratamento de erros
└── main.py                 # composição da aplicação FastAPI
```

A persistência usa Repository Pattern e Unit of Work. As configurações vêm
de variáveis de ambiente, e as migrações são gerenciadas pelo Alembic.

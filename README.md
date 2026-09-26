# Smart Expense Analyzer

Backend para importar extratos financeiros em CSV, normalizar e categorizar
transações e disponibilizar análises de despesas por meio de uma API REST.

> **Status:** projeto greenfield em fase de planejamento. A especificação está
> concluída, mas a aplicação e os arquivos de infraestrutura descritos abaixo
> ainda serão implementados.

## Funcionalidades planejadas

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

## Segurança e escopo

A primeira versão é mono-usuário e **sem autenticação**. Todos os endpoints
podem ler ou alterar dados financeiros; portanto, a API não deve ser exposta
à internet nem vinculada a uma interface de rede pública. O ambiente Docker
planejado publica a API somente em `127.0.0.1:8000`.

Conversão cambial, interface gráfica, integração bancária/Open Finance e
deploy em produção estão fora do escopo inicial.

## Executando com Docker

Quando os arquivos de aplicação e infraestrutura estiverem implementados, os
pré-requisitos serão Docker e Docker Compose. A inicialização completa será:

```bash
cp .env.example .env
docker compose up -d --build
```

A migração do banco será aplicada automaticamente antes da inicialização da
API. Depois disso, estarão disponíveis:

- documentação interativa: <http://localhost:8000/docs>;
- especificação OpenAPI: <http://localhost:8000/openapi.json>;
- verificação de saúde: <http://localhost:8000/health>.

Para encerrar o ambiente:

```bash
docker compose down
```

## Variáveis de ambiente

O arquivo `.env.example`, previsto na implementação, documentará os valores
seguros para desenvolvimento local.

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

## API planejada

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

Instale as ferramentas de qualidade e testes com `uv`:

```bash
uv tool install pytest && uv tool install ruff && uv tool install mypy
```

Após a criação do `pyproject.toml`, o ambiente de desenvolvimento será
preparado com:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Os testes de integração usam PostgreSQL real por meio de Testcontainers; por
isso, exigem Docker em execução. Para verificar o projeto:

```bash
ruff check . --output-format=concise
mypy app
pytest -q
```

O pytest produzirá o relatório JUnit em `reports/junit.xml`. No CI, a variável
opcional `TEST_DATABASE_URL` apontará para o PostgreSQL efêmero do workflow.

## Arquitetura planejada

O projeto seguirá Clean Architecture, com dependências direcionadas ao
domínio:

```text
app/
├── domain/                 # entidades, regras puras e portas
├── application/services/   # casos de uso
├── infrastructure/         # banco de dados e leitura de CSV
├── api/                    # rotas, schemas e tratamento de erros
└── main.py                 # composição da aplicação FastAPI
```

A persistência utilizará Repository Pattern e Unit of Work. Configurações
virão de variáveis de ambiente, e as migrações serão gerenciadas pelo
Alembic.

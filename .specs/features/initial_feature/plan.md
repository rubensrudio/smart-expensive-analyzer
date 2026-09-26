# Plano Técnico — Smart Expense Analyzer (feature inicial)

## 1. Resumo Executivo

Projeto greenfield: não há código, repositório git nem `.specs/codebase`. Este plano cria do zero um backend
Python 3.12 com FastAPI, Pydantic v2, SQLAlchemy 2, Alembic e PostgreSQL 16. O backend importa CSV de extratos,
valida e normaliza cada linha, deduplica, categoriza por regras configuráveis, persiste tudo e expõe via REST
as transações, as estatísticas por moeda (total, média, mediana, percentual por categoria e histograma), a
série mensal e as anomalias detectadas por IQR. Pandas faz a leitura do CSV e NumPy calcula os quartis.

A arquitetura segue Clean Architecture em quatro camadas: `app/domain` (entidades, regras puras e portas),
`app/application/services` (casos de uso), `app/infrastructure` (SQLAlchemy, leitor CSV) e `app/api`
(FastAPI, schemas, handlers de erro). A persistência passa por Repository Pattern com Unit of Work. As
dependências são injetadas pelo `Depends` do FastAPI e os serviços recebem portas (`Protocol`), nunca a
sessão SQLAlchemy. A configuração vem só de variáveis de ambiente (`pydantic-settings`). Os erros são tratados
num único ponto (`app/api/errors.py`), sempre com o mesmo corpo JSON.

O ambiente sobe com `docker compose up -d --build`. O contêiner da API aplica `alembic upgrade head` antes de
iniciar o Uvicorn. O GitHub Actions executa lint, typecheck e a suíte de testes (unitários e de integração
contra PostgreSQL real) a cada push e pull request. Nos testes de integração locais, cada processo pytest
sobe seu próprio PostgreSQL via Testcontainers. Isso isola as tasks paralelas do `/implement`.

Como o projeto é greenfield, os comandos de verificação da seção 3 ainda não existem em arquivo. Eles são
**definidos aqui e criados pela TASK-001** (`pyproject.toml`), e por isso não puderam ser confirmados por
leitura (ver seção 15, risco R-1).

## 2. Premissas e Lacunas

### 2.1 Decidido pelo humano (de `decisions.md`)
| ID | Decisão | Consequência no plano |
|---|---|---|
| LAC-01 | A: mono-usuário, sem autenticação | Nenhum middleware de auth. Nenhuma entidade User. AS-6 = SIM. O Compose publica a API só em `127.0.0.1:8000` (DA-12). O README avisa que não pode ser exposta. |
| LAC-02 | A: CSV UTF-8, vírgula, colunas `date`,`description`,`amount` (+`merchant`,`currency` opcionais), data AAAA-MM-DD, ponto decimal | `csv_reader.py` (pandas, `dtype=str`) e `csv_rows.py` (CT-12). |
| LAC-03 | B: importar despesas e receitas com `type`; estatísticas só sobre despesas | Coluna `transactions.type`. `list_expenses` filtra `type='despesa'` (CT-7). |
| LAC-04 | B: importar as válidas e registrar as inválidas por linha | Tabela `import_rejections`. Status `concluida_com_rejeicoes`. |
| LAC-05 | C: hash do arquivo (409) + chave por transação | `imports.file_sha256` + `transactions.dedup_key` UNIQUE + `INSERT ... ON CONFLICT DO NOTHING` (DA-6). |
| LAC-06 | A: síncrono, HTTP 201 | `POST /imports` processa tudo na requisição e responde já em estado terminal. |
| LAC-07 | A: 10 MB configurável, 413 | `MAX_UPLOAD_MB` (padrão 10). `FileTooLargeError` → 413. |
| LAC-08 | A: palavra-chave contida, sem caixa nem acento, prioridade numérica | `fold_for_match` + `RuleMatcher` (CT-10, CT-11). Desempate por `created_at` e depois `id`. |
| LAC-09 | A: endpoints mínimos + CRUD de regras + listagem de categorias | Routers `categories` (POST/GET) e `categorization-rules` (CRUD com PUT). |
| LAC-10 | A: Category padrão "Não categorizada" | A migration 0001 insere a categoria com `is_default=true` (índice único parcial). |
| LAC-11 | B: recategorização sob demanda | `POST /transactions/recategorize` + `RecategorizationService`. |
| LAC-12 | A: IQR por (Category, moeda), k=1,5, amostra mínima 8 | `detect_iqr_anomalies` (CT-15). `ANOMALY_IQR_K` e `ANOMALY_MIN_SAMPLE`. |
| LAC-13 | A: recalcular sobre todo o histórico ao fim de cada importação | `AnomalyService.recompute_all()` roda dentro da transação do Import, sob advisory lock (DA-7). |
| LAC-14 | C: percentual por categoria + histograma por faixas | `percentages` (maior resto, DA-9) e `histogram` (CT-13). |
| LAC-15 | A: endpoint dedicado de série mensal | `GET /analytics/monthly`. |
| LAC-16 | B: multimoeda sem conversão | Toda resposta de analytics e todo agrupamento de anomalias são por moeda. |
| LAC-16b | A: `currency` opcional ISO 4217, padrão `DEFAULT_CURRENCY`=BRL | `app/domain/currency.py` com a lista ISO 4217 embutida (DA-10). `DEFAULT_CURRENCY` é validada na inicialização. |
| LAC-17 | A: limit/offset, padrão 50, máximo 500, filtros | `pagination_params` (CT-22) e `TransactionFilters`. |
| LAC-18 | A: todo o histórico quando não há filtro de período | `Period(start=None, end=None)` significa "sem limite". |
| LAC-19 | A: nome de Category único sem distinguir caixa, 409 | Índice único `lower(name)` + checagem no serviço. |
| LAC-21 | B: TASK-014 com risco `médio`, sem âncora | Só afeta o campo `Risco` da TASK-014 em `tasks.md`. A task roda em paralelo na onda 4. |
| LAC-20 | A: negativo = despesa, zero = linha inválida, cálculos usam o módulo | `csv_rows.parse_row` deriva `type`. `ExpenseRecord.value = abs(amount)`. |

### 2.2 Premissas assumidas (lacunas não bloqueantes)
| ID | Premissa | Reversibilidade | Onde impacta |
|---|---|---|---|
| P-01 | Desdobramento por estabelecimento dentro de `GET /analytics/summary` (de `decisions.md`). | alta | contrato de `/analytics/summary` |
| P-02 | Interpretações do spec-writer (de `decisions.md`): SEA-62 sem filtro = todo o histórico, SEA-65 recalcula anomalias, faixas do histograma, moeda em maiúsculas, 409 só contra Import concluído, duplicata no mesmo arquivo. | alta | CT-13, CT-16, CT-17 |
| P-03 | `amount` com mais de 2 casas decimais é arredondado com `ROUND_HALF_UP` para 2 casas. Se o resultado for 0,00, a linha é rejeitada como "valor igual a zero". Aceita sinal `+`/`-` opcional e não aceita separador de milhar nem notação científica ("valor não numérico"). | alta | `app/domain/csv_rows.py` |
| P-04 | Os nomes de coluna do cabeçalho são comparados após `strip()` e `lower()`. Colunas extras são ignoradas. | alta | `app/infrastructure/csv_reader.py` |
| P-05 | Uma linha com mais campos que o cabeçalho faz o pandas falhar. O arquivo inteiro vira "ilegível" (`INVALID_CSV`, 422). Linhas com menos campos têm as células faltantes tratadas como vazias. | média | `csv_reader.py` |
| P-06 | Uma linha com vários problemas lista todos os motivos, separados por "; ", nesta ordem: data, descrição, valor, moeda. | alta | `csv_rows.py` |
| P-07 | O número da linha é o número físico no arquivo, com o cabeçalho na linha 1 e o primeiro dado na linha 2. | alta | rejeições do Import |
| P-08 | Na chave de deduplicação, a descrição normalizada distingue maiúsculas de minúsculas (a normalização de SEA-09 só trata espaços). | alta | `dedup_key` (DA-6) |
| P-09 | O filtro `merchant` (em `/transactions` e `/analytics/summary`) é igualdade sem distinguir caixa, após normalizar espaços. O filtro `category_id` é igualdade por id. | alta | CT-7 |
| P-10 | O filtro de período aceita só `start_date`, só `end_date` ou ambos (intervalo aberto do lado ausente). | alta | CT-22 |
| P-11 | A série mensal usa um único intervalo de meses para todas as moedas: do mês de `start_date` (ou da despesa mais antiga do escopo) ao mês de `end_date` (ou da mais recente). Sem despesas no escopo → `currencies: []`. `by_category` do mês lista só as categorias com despesa naquele mês. | alta | CT-14 |
| P-12 | A prioridade de regra aceita qualquer inteiro, inclusive negativo. A atualização é `PUT` com o corpo completo. | alta | CT-18 |
| P-13 | Valores monetários e percentuais são serializados em JSON como string com 2 casas (`"90.00"`), para evitar ponto flutuante. | média | todos os schemas de resposta |
| P-14 | Os IDs são inteiros (`BIGINT IDENTITY`). Id não inteiro no path → 422 `VALIDATION_ERROR` (SEA-94). | baixa (depois de publicado) | modelos e rotas |
| P-15 | Os arredondamentos de média, mediana, limite IQR e percentual usam `ROUND_HALF_UP`. | alta | CT-13, CT-15 |
| P-16 | O limite IQR usa `numpy.percentile(..., method="linear")` sobre `float`. A comparação é `valor > limite` em `float`, e o limite é persistido arredondado a 2 casas. | alta | CT-15 |

### 2.3 Lacunas ainda abertas
Nenhuma. LAC-21 foi decidida (ver 2.1).

## 3. Ambiente e Comandos de Verificação

Projeto greenfield: **nenhum destes comandos existe hoje em arquivo**. Eles ficam definidos aqui e a TASK-001
os cria no `pyproject.toml` (configuração de `ruff`, `mypy` e `pytest`, com `addopts` gerando o JUnit). A
TASK-030 cria o `docker-compose.yml` e a TASK-031 o workflow de CI. Pré-requisito local para todos os comandos
Python: Python 3.12, um venv ativo com `pip install -e ".[dev]"` na raiz, e Docker em execução (os testes de
integração usam Testcontainers).

| Alvo | Comando | Diretório | Relatório | Origem |
|---|---|---|---|---|
| Lint | `ruff check . --output-format=concise` | `.` | — | a criar: `pyproject.toml` `[tool.ruff]` (TASK-001) |
| Typecheck | `mypy app` | `.` | — | a criar: `pyproject.toml` `[tool.mypy]` strict (TASK-001) |
| Teste (suíte) | `pytest -q` | `.` | `reports/junit.xml` | a criar: `pyproject.toml` `[tool.pytest.ini_options]` addopts `--junitxml=reports/junit.xml` (TASK-001) |
| Teste (relacionado a arquivo) | `pytest -q {files}` | `.` | `reports/junit.xml` | idem (TASK-001) |
| Build | `docker compose build api` | `.` | — | a criar: `docker-compose.yml` + `Dockerfile` (TASK-030). Até lá, falha no baseline (R-1). |
| Subir ambiente local | `docker compose up -d --build` | `.` | — | a criar: `docker-compose.yml` (TASK-030), documentado no `README.md` (TASK-031) |
| URL da aplicação | `http://localhost:8000` | — | — | a criar: `docker-compose.yml` porta `127.0.0.1:8000:8000` (TASK-030). OpenAPI em `/docs` e `/openapi.json`. |
| Credenciais QA | N/A | — | — | API sem autenticação (LAC-01) |

Instalação de ferramentas (uma vez, antes da TASK-001 ter efeito): `python3.12 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`.
A pasta `reports/` entra no `.gitignore` (TASK-001).

Regras para o implementador:
- A variável `TEST_DATABASE_URL` **não** deve estar definida no ambiente local do `/implement`. Sem ela, cada
  processo pytest sobe o seu PostgreSQL descartável (DA-14). Só o CI a define.
- Sem teste de Playwright/e2e de tela: o projeto não tem frontend.

## 4. Estratégia de Testes

Sem `.specs/codebase/TESTING.md` (greenfield). A convenção definida aqui é criada pela TASK-001 e pela TASK-005.

| Camada / pasta | Tipo exigido | Paralelo-seguro |
|---|---|---|
| `tests/unit` | unit | sim |
| `tests/integration` | integration | sim |

- `tests/unit`: domínio puro (`app/domain`), leitor CSV, config, handlers de erro (com app FastAPI mínima
  montada no teste), schemas e parâmetros, e checagens textuais dos arquivos de infra. Sem banco nem rede.
- `tests/integration`: repositórios, Unit of Work, serviços de aplicação e API (via `fastapi.testclient.TestClient`)
  contra PostgreSQL real. **Paralelo-seguro = sim** porque cada processo pytest sobe o seu próprio contêiner
  PostgreSQL (Testcontainers, fixture de sessão). Tasks paralelas em worktrees diferentes nunca compartilham banco.
  Isso só vale com `TEST_DATABASE_URL` ausente (seção 3).
- Pytest roda com `--import-mode=importlib`: as pastas de teste não precisam de `__init__.py` e nomes de arquivo
  repetidos não colidem.
- Fixtures compartilhadas (CT-23) moram **só** em `tests/integration/conftest.py`, criado pela TASK-005. Todas
  usam o mesmo `postgres_url`, a mesma `engine` e a limpeza `clean_db`. Nenhuma task cria outro `conftest.py`.
- Regra de co-location: o teste é escrito **na mesma task** que cria o código.

## 5. Arquitetura Proposta

### 5.1 Visão de Componentes

```
app/
  main.py                         create_app() (factory), lifespan, registro de routers e handlers
  core/config.py                  Settings (pydantic-settings), load_settings_or_exit()
  core/logging.py                 configure_logging(level)
  core/errors.py                  AppError e subclasses (catálogo 8.3)
  domain/currency.py              ISO_4217_CODES, normalize_currency_code()
  domain/entities.py              dataclasses e enums do domínio
  domain/ports.py                 Protocols: repositórios e UnitOfWork
  domain/text.py                  normalize_whitespace(), fold_for_match()
  domain/categorization.py        RuleMatcher
  domain/csv_rows.py              parse_row() → ParsedRow | RowRejection; dedup_key()
  domain/statistics.py            money(), summarize(), histogram(), percentages(), merchant_totals()
  domain/monthly_series.py        monthly_series()
  domain/anomaly_detection.py     detect_iqr_anomalies()
  application/services/
    import_service.py             ImportService.import_csv()
    anomaly_service.py            AnomalyService.recompute_all(), list()
    category_service.py           CategoryService
    categorization_rule_service.py CategorizationRuleService
    transaction_service.py        TransactionService
    recategorization_service.py   RecategorizationService
    analytics_service.py          AnalyticsService
  infrastructure/csv_reader.py    read_csv_rows() (pandas)
  infrastructure/db/session.py    create_engine_from_url(), create_session_factory()
  infrastructure/db/models.py     modelos ORM (seção 7)
  infrastructure/db/unit_of_work.py SqlAlchemyUnitOfWork
  infrastructure/db/repositories/ categories.py, categorization_rules.py, transactions.py, imports.py, anomalies.py
  api/deps.py                     get_settings, get_uow, get_uow_factory
  api/errors.py                   register_exception_handlers()
  api/params.py                   period_params, pagination_params
  api/schemas/                    common.py, imports.py, transactions.py, categories.py,
                                  categorization_rules.py, analytics.py, anomalies.py
  api/routers/                    imports.py, transactions.py, categories.py,
                                  categorization_rules.py, analytics.py, anomalies.py
alembic/ env.py, versions/0001_initial_schema.py
```

Regra de dependência: `api` → `application` → `domain` ← `infrastructure`. `domain` não importa FastAPI,
SQLAlchemy nem pandas. `application` importa só `domain` e `core`. Routers não acessam repositórios diretamente.

### 5.2 Fluxo Principal

```mermaid
sequenceDiagram
  participant C as Cliente
  participant R as routers/imports.py
  participant S as ImportService
  participant CSV as csv_reader + csv_rows
  participant U as SqlAlchemyUnitOfWork
  participant A as AnomalyService
  participant DB as PostgreSQL
  C->>R: POST /imports (multipart file)
  R->>R: lê até MAX_UPLOAD_MB+1 bytes
  R->>S: import_csv(filename, content)
  S->>S: tamanho > limite? → FileTooLargeError (413)
  S->>CSV: read_csv_rows(content)
  CSV-->>S: RawRow[] ou EmptyFile/InvalidCsv/MissingColumns (422)
  S->>U: abre UoW (transação)
  S->>U: imports.find_completed_by_hash(sha256)
  U-->>S: id existente → DuplicateFileError (409)
  S->>U: imports.create_processing(...)
  S->>CSV: parse_row() por linha → ParsedRow | RowRejection
  S->>S: deduplica dentro do arquivo, RuleMatcher.match()
  S->>U: transactions.insert_ignoring_duplicates() (ON CONFLICT DO NOTHING)
  S->>U: imports.finish(status, contagens, rejeições)
  S->>A: recompute_all() (advisory lock, substitui anomalies)
  S->>U: commit
  U->>DB: COMMIT
  S-->>R: Import (terminal)
  R-->>C: 201 ImportOut
  Note over S,U: SQLAlchemyError → rollback; novo UoW grava Import "falhou"; 503
```

Narrativa: o router só cuida do HTTP e do limite de leitura. Toda a regra fica no `ImportService`. A leitura e
a validação estrutural acontecem antes de abrir a transação, então um arquivo recusado nunca cria Import
(SEA-90 a SEA-92, SEA-104). Transações, Import terminal e anomalias são gravados numa única transação de banco:
ou tudo persiste, ou nada (SEA-97). As consultas (`GET`) passam por serviços finos que chamam repositórios, e os
analytics buscam as despesas filtradas no banco e calculam em Python com `Decimal` (funções puras do domínio).

### 5.3 Decisões Arquiteturais

| # | Decisão | Alternativas rejeitadas | Por quê |
|---|---|---|---|
| DA-1 | Clean Architecture em 4 camadas (`domain`, `application`, `infrastructure`, `api`) com portas `typing.Protocol` em `domain/ports.py` | camadas por feature (vertical slices), serviços acessando `Session` direto | É exigência do spec (objetivo 8). Protocols deixam os serviços independentes de SQLAlchemy sem ABCs pesadas. |
| DA-2 | Unit of Work (`SqlAlchemyUnitOfWork`) expõe os 5 repositórios. Os serviços recebem `UnitOfWork` (ou uma fábrica dela). Só o serviço chama `commit()`. | commit por repositório, sessão por request com autocommit | Garante a atomicidade do Import (SEA-97) e deixa a fronteira de transação explícita. |
| DA-3 | DI via `Depends`: `app/api/deps.py` fornece `get_settings`, `get_uow` e `get_uow_factory`. Cada router define seu próprio provider de serviço. | container de DI (dependency-injector) | Sem biblioteca nova. Evita que todas as tasks de router editem `deps.py`. |
| DA-4 | Factory `create_app(settings: Settings | None = None)` executada com `uvicorn app.main:create_app --factory` | `app = FastAPI()` no import do módulo | Os testes montam a app com `Settings` de teste. A validação de ambiente (SEA-03) roda num ponto controlado. |
| DA-5 | Leitura do CSV com `pandas.read_csv(BytesIO, dtype=str, keep_default_na=False, na_filter=False, skip_blank_lines=False, encoding="utf-8")`, precedida de `content.decode("utf-8-sig")` estrito e rejeição de byte NUL | módulo `csv` da stdlib, `pandas` com inferência de tipos | Pandas é parte da stack pedida. `dtype=str` impede inferência que perderia precisão. `skip_blank_lines=False` preserva o número da linha (P-07). |
| DA-6 | Deduplicação: `dedup_key = sha256("{date.isoformat()}|{amount:.2f}|{description}|{currency}")` em `CHAR(64) UNIQUE`, com inserção `INSERT ... ON CONFLICT (dedup_key) DO NOTHING RETURNING id` | UNIQUE composto em (date, amount, description, currency) | A descrição é `TEXT` sem limite. Índice btree sobre texto longo estoura o limite de 2704 bytes. O hash tem tamanho fixo. `ON CONFLICT` resolve a corrida entre imports paralelos (SEA-106) no banco. |
| DA-7 | Recálculo de anomalias: `pg_advisory_xact_lock(815001)`, `DELETE FROM anomalies` e `INSERT` do novo conjunto, na mesma transação do caller | recálculo incremental, tabela versionada | O spec manda substituir o conjunto (SEA-60). O lock serializa imports e recategorizações concorrentes, e o unique `(transaction_id, method)` garante SEA-30. |
| DA-8 | Estatísticas (total, média, mediana, percentuais, histograma) calculadas em Python com `Decimal` sobre as despesas filtradas no banco. Quartis do IQR com `numpy.percentile`. Agrupamentos da detecção com `pandas.DataFrame.groupby`. | agregação SQL (`percentile_cont`), tudo em float | Exatidão decimal (SEA-26). Regras puras testáveis sem banco. O volume é de demonstração (seção 10 do spec). |
| DA-9 | Percentual por categoria pelo método do maior resto (Hamilton) em centésimos, garantindo soma exata de 100,00 por moeda | arredondar cada percentual isoladamente | O arredondamento isolado pode desviar mais que 0,01 com 4 ou mais categorias (SEA-55). |
| DA-10 | Lista ISO 4217 embutida como `frozenset` em `app/domain/currency.py` (códigos ativos da tabela A.1) | biblioteca `pycountry` | Evita dependência para ~180 códigos estáveis. |
| DA-11 | Erros de domínio herdam de `AppError(code, message, http_status, details)`. `register_exception_handlers` traduz `AppError`, `RequestValidationError`, `StarletteHTTPException`, `sqlalchemy.exc.OperationalError`/`InterfaceError` (503) e `Exception` (500 com `error_id`) para o corpo `ErrorResponse` | `HTTPException` espalhada nos routers | Um único formato (SEA-05). O domínio não conhece HTTP além de um inteiro de status. |
| DA-12 | Compose publica a API em `127.0.0.1:8000:8000` e não publica a porta do PostgreSQL | publicar `0.0.0.0` | Mitigação exigida pelo risco aceito LAC-01 (seção 10 do spec). |
| DA-13 | O contêiner da API executa `alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --no-access-log` | serviço de migração separado | Uma única subida sem passo manual (SEA-01). `--no-access-log` evita logar query strings com estabelecimento (seção 14). |
| DA-14 | Testes de integração com `testcontainers[postgres]` (`postgres:16-alpine`) por sessão pytest. Se `TEST_DATABASE_URL` estiver definida (CI), usa essa URL. As migrações são aplicadas pelo próprio Alembic na fixture `engine`. | SQLite em memória, banco fixo compartilhado | PostgreSQL real (`ON CONFLICT`, advisory lock, `lower()`). Isolamento entre tasks paralelas. Os testes exercitam a migration de verdade. |
| DA-15 | `engine` criado com `hide_parameters=True` e `pool_pre_ping=True` | padrão | Impede que mensagens de erro do SQLAlchemy levem descrições e valores para o log (AS-3). O pre-ping transforma a queda do banco em `OperationalError` → 503. |
| DA-16 | Falha no import: a exceção desfaz o UoW. Em seguida, um **novo** UoW grava `imports` com status `falhou` e `failure_reason` (nome da classe da exceção) e faz commit (melhor esforço). Depois a exceção é relançada: `SQLAlchemyError` vira `ServiceUnavailableError` (503) e as demais seguem para o handler de 500. | gravar o Import antes, em transação separada | "Processando" nunca é visível (seção 7 do spec) e nenhuma transação parcial fica gravada. |

## 6. Reuso Obrigatório

Greenfield: **não há código a reaproveitar no repositório** (confirmado: a raiz só contém `.specs/`). O reuso
obrigatório é interno à feature. Cada item é criado uma vez pela task produtora e depois **importado**, nunca
reimplementado:

| Precisa de | Já existe em (após a task) | Como usar |
|---|---|---|
| Normalizar espaços (descrição, estabelecimento, palavra-chave, filtro merchant) | `app/domain/text.py` (TASK-013) | `normalize_whitespace(value)` |
| Comparar sem caixa e sem acento | `app/domain/text.py` (TASK-013) | `fold_for_match(value)` |
| Escolher a Category de uma transação (import e recategorização) | `app/domain/categorization.py` (TASK-013) | `RuleMatcher(rules, default_category_id).match(description, merchant)` |
| Validar/normalizar código de moeda (CSV e `DEFAULT_CURRENCY`) | `app/domain/currency.py` (TASK-001) | `normalize_currency_code(raw)` |
| Arredondar dinheiro a 2 casas | `app/domain/statistics.py` (TASK-015) | `money(value)`, também em `monthly_series.py` e `anomaly_detection.py` |
| Recalcular anomalias (import e recategorização) | `app/application/services/anomaly_service.py` (TASK-018) | `AnomalyService(uow, k, min_sample).recompute_all()` dentro do UoW aberto |
| Validar período e paginação em qualquer rota | `app/api/params.py` (TASK-011) | `period: Period = Depends(period_params)`, `page: Page = Depends(pagination_params)` |
| Serializar transação e categoria na resposta | `app/api/schemas/common.py` (TASK-011) | `TransactionOut.from_entity(t)`, `CategoryRef`, tipo `Money` |
| Corpo de erro | `app/core/errors.py` (TASK-003) | lançar a subclasse de `AppError`. Nunca `HTTPException` nos routers. |
| Sessão de banco nos serviços | `app/api/deps.py` (TASK-010) | `uow: UnitOfWork = Depends(get_uow)` ou `Depends(get_uow_factory)` |
| Fixtures de teste de integração | `tests/integration/conftest.py` (TASK-005) | `postgres_url`, `engine`, `session_factory`, `uow_factory`, `uow`, `client`, `settings`, `clean_db` (autouse). Todas sobre a **mesma** `engine`/`postgres_url`, então os dados commitados por um são vistos pelos outros. |

Padrões a copiar:
- Provider de serviço por router: `def get_<x>_service(uow: UnitOfWork = Depends(get_uow)) -> <X>Service`, definido no próprio arquivo do router (DA-3).
- Router: `APIRouter(prefix="/<recurso>", tags=["<recurso>"])`, registrado em `app/main.py` com `app.include_router(...)`.
- Schemas de resposta com `model_config = ConfigDict(from_attributes=True)` quando convertem entidades.

## 7. Modelos de Dados

Todas as tabelas nascem na migration `alembic/versions/0001_initial_schema.py` (revision `0001`, down_revision `None`).
IDs são `BIGINT GENERATED BY DEFAULT AS IDENTITY`. Timestamps são `TIMESTAMPTZ` com default `now()`.
Campos com dado pessoal (financeiro) estão marcados **[PII]**.

**categories** (`CategoryModel`)
| Campo | Tipo | Obrig. | Observação |
|---|---|---|---|
| id | BIGINT identity | sim | PK |
| name | VARCHAR(100) | sim | gravado com `normalize_whitespace` |
| is_default | BOOLEAN | sim | default false |
| created_at | TIMESTAMPTZ | sim | default now() |
Índices: `uq_categories_name_ci` UNIQUE em `lower(name)`; `uq_categories_default` UNIQUE em `(is_default) WHERE is_default`.
Seed na 0001: `('Não categorizada', true)`.

**categorization_rules** (`CategorizationRuleModel`)
| Campo | Tipo | Obrig. | Observação |
|---|---|---|---|
| id | BIGINT identity | sim | PK |
| keyword | VARCHAR(200) | sim | com `normalize_whitespace`, não vazio |
| category_id | BIGINT FK categories(id) ON DELETE RESTRICT | sim | |
| priority | INTEGER | sim | menor vence |
| created_at | TIMESTAMPTZ | sim | desempate |
Índice: `ix_rules_order` em `(priority, created_at, id)`.

**imports** (`ImportModel`)
| Campo | Tipo | Obrig. | Observação |
|---|---|---|---|
| id | BIGINT identity | sim | PK |
| filename | VARCHAR(255) | sim | nome enviado, truncado em 255 |
| file_sha256 | CHAR(64) | sim | hash do conteúdo |
| status | VARCHAR(32) | sim | CHECK in (`processando`,`concluida`,`concluida_com_rejeicoes`,`falhou`) |
| received_at | TIMESTAMPTZ | sim | |
| finished_at | TIMESTAMPTZ | não | |
| rows_read | INTEGER | sim | default 0 (linhas de dados não vazias) |
| imported_count | INTEGER | sim | default 0 |
| rejected_count | INTEGER | sim | default 0 |
| duplicate_count | INTEGER | sim | default 0 |
| failure_reason | VARCHAR(500) | não | só em `falhou` (nome da exceção, nunca dados) |
Índice: `ix_imports_sha256_status` em `(file_sha256, status)`.

**import_rejections** (`ImportRejectionModel`)
| Campo | Tipo | Obrig. | Observação |
|---|---|---|---|
| id | BIGINT identity | sim | PK |
| import_id | BIGINT FK imports(id) ON DELETE CASCADE | sim | índice |
| line_number | INTEGER | sim | P-07 |
| reason | VARCHAR(500) | sim | só o motivo ("data inválida"), sem conteúdo da linha |

**transactions** (`TransactionModel`)
| Campo | Tipo | Obrig. | Observação |
|---|---|---|---|
| id | BIGINT identity | sim | PK |
| import_id | BIGINT FK imports(id) | sim | índice `ix_transactions_import` |
| date | DATE | sim | índice `ix_transactions_date` |
| description | TEXT | sim | **[PII]** normalizada |
| merchant | TEXT | sim | **[PII]** normalizado, ou a descrição (SEA-37) |
| amount | NUMERIC(14,2) | sim | **[PII]** com sinal, como no CSV. CHECK `amount <> 0` |
| currency | CHAR(3) | sim | ISO 4217 em maiúsculas |
| type | VARCHAR(10) | sim | CHECK in (`despesa`,`receita`) |
| category_id | BIGINT FK categories(id) ON DELETE RESTRICT | sim | índice `ix_transactions_category` |
| dedup_key | CHAR(64) | sim | UNIQUE `uq_transactions_dedup_key` (DA-6) |
| created_at | TIMESTAMPTZ | sim | |
Índice adicional: `ix_transactions_currency_type` em `(currency, type)`.

**anomalies** (`AnomalyModel`)
| Campo | Tipo | Obrig. | Observação |
|---|---|---|---|
| id | BIGINT identity | sim | PK |
| transaction_id | BIGINT FK transactions(id) ON DELETE CASCADE | sim | |
| method | VARCHAR(10) | sim | `IQR` |
| value | NUMERIC(14,2) | sim | limite `Q3 + k·IQR` do grupo |
| reason | TEXT | sim | motivo legível (CT-15) |
| detected_at | TIMESTAMPTZ | sim | |
Constraint: `uq_anomalies_transaction_method` UNIQUE `(transaction_id, method)`.

Migrations necessárias: só a `0001` (criação de estrutura vazia e seed da categoria padrão). O `downgrade()` remove
todas as tabelas, em ordem reversa de FK.

## 8. Contratos

### 8.1 Contratos externos (API)

Convenções gerais:
- JSON UTF-8. Datas `AAAA-MM-DD`. Dinheiro e percentual como string com 2 casas (P-13). Nenhum endpoint exige
  cabeçalho de autenticação (SEA-35).
- Todo erro usa `ErrorResponse`: `{"code": str, "message": str, "details": list[object] | null, "error_id": str | null}`.
- Parâmetros de período (onde indicado): `start_date`, `end_date` (query, opcionais, ISO). Formato inválido → 422
  `VALIDATION_ERROR`. Início maior que fim → 422 `INVALID_PERIOD`.

**POST /imports** (multipart/form-data, campo `file`)
- 201 `ImportOut`: `{"id": int, "filename": str, "status": "concluida"|"concluida_com_rejeicoes", "received_at": datetime,
  "rows_read": int, "imported_count": int, "rejected_count": int, "duplicate_count": int,
  "rejections": [{"line": int, "reason": "Linha 12: data inválida"}]}`
- 409 `DUPLICATE_FILE` · 413 `FILE_TOO_LARGE` · 422 `EMPTY_FILE` | `INVALID_CSV` | `MISSING_COLUMNS` (details = `["date", ...]`) | `VALIDATION_ERROR` (sem campo `file`) · 503 `SERVICE_UNAVAILABLE` · 500 `INTERNAL_ERROR`

**GET /transactions**
- Query: `start_date`, `end_date`, `category_id: int`, `merchant: str`, `import_id: int`, `limit: int = 50`, `offset: int = 0`.
- 200 `{"items": [TransactionOut], "total": int, "limit": int, "offset": int}`, ordenado por `date DESC, id DESC`.
- `TransactionOut`: `{"id": int, "date": date, "description": str, "merchant": str, "amount": "-45.90", "currency": "BRL",
  "type": "despesa"|"receita", "category": {"id": int, "name": str}, "import_id": int}`
- 422 `INVALID_PAGINATION` (limit < 1, limit > 500, offset < 0) | `INVALID_PERIOD` | `VALIDATION_ERROR`. Category inexistente no filtro → 200 com `items: []`, `total: 0` (SEA-101).

**GET /transactions/{transaction_id}** → 200 `TransactionOut` · 404 `TRANSACTION_NOT_FOUND` · 422 `VALIDATION_ERROR` (id não inteiro)

**POST /transactions/recategorize** (sem corpo) → 200 `{"evaluated": int, "changed": int}`

**POST /categories** body `{"name": str | null}` → 201 `{"id": int, "name": str}` · 409 `CATEGORY_ALREADY_EXISTS` · 422 `CATEGORY_NAME_REQUIRED` (ausente, vazio ou só espaços)

**GET /categories** → 200 `[{"id": int, "name": str}]` ordenado por `name`, incluindo "Não categorizada".

**/categorization-rules**
- `POST` body `RuleIn {"keyword": str, "category_id": int, "priority": StrictInt}` → 201 `RuleOut {"id", "keyword", "category_id", "priority", "created_at"}`
- `GET` → 200 `[RuleOut]`, ordenado por `priority, created_at, id`
- `GET /{rule_id}` → 200 `RuleOut` · 404 `RULE_NOT_FOUND`
- `PUT /{rule_id}` body `RuleIn` → 200 `RuleOut` · 404 `RULE_NOT_FOUND`
- `DELETE /{rule_id}` → 204 sem corpo · 404 `RULE_NOT_FOUND`
- POST/PUT: keyword vazia ou só espaços, prioridade ausente ou não inteira → 422 `VALIDATION_ERROR`. Category inexistente → 422 `RULE_CATEGORY_NOT_FOUND`.

**GET /analytics/summary** (query: período, `category_id`, `merchant`)
- 200 `{"currencies": [{"currency": "BRL", "total": "90.00", "count": 3, "mean": "30.00", "median": "20.00",
  "by_merchant": [{"merchant": str, "total": "...", "count": int}],
  "histogram": [{"range_start": "0.00", "range_end": "50.00", "count": int, "total": "..."}, ..., {"range_start": "500.00", "range_end": null, ...}]}]}`
- Sem despesas no escopo → `{"currencies": []}` (SEA-95). `by_merchant` ordenado por total desc e merchant asc. O histograma sempre tem as 4 faixas.

**GET /analytics/categories** (query: período)
- 200 `{"currencies": [{"currency": "BRL", "total": "...", "categories": [{"category_id": int, "category_name": str,
  "total": "...", "count": int, "mean": "...", "median": "...", "percentage": "33.33"}]}]}`. Categorias ordenadas por total desc e nome asc. Soma de `percentage` = `100.00`.

**GET /analytics/monthly** (query: período)
- 200 `{"currencies": [{"currency": "BRL", "months": [{"month": "2026-01", "total": "...", "count": int,
  "by_category": [{"category_id": int, "category_name": str, "total": "...", "count": int}]}]}]}` (P-11)

**GET /anomalies** (query: período)
- 200 `{"items": [{"id": int, "method": "IQR", "value": "70.00", "reason": str, "transaction": TransactionOut}]}`, ordenado por data da transação desc e id desc. Sem anomalias → `items: []`.

Endpoints sem negócio, gerados pelo FastAPI: `GET /docs`, `GET /openapi.json`. Mais `GET /health` → 200 `{"status": "ok"}` (sem acesso ao banco).

### 8.2 Contratos internos entre tasks

| ID | Contrato (assinatura / rota / tipo) | Produzido por | Consumido por |
|---|---|---|---|
| CT-1 | `app/core/config.py`: `class Settings(BaseSettings)` com `database_url: str` (obrig.), `default_currency: str = "BRL"` (validada e normalizada por `normalize_currency_code`), `max_upload_mb: int = 10` (>0), `anomaly_iqr_k: float = 1.5` (>0), `anomaly_min_sample: int = 8` (>=2), `log_level: str = "INFO"`. Env: `DATABASE_URL`, `DEFAULT_CURRENCY`, `MAX_UPLOAD_MB`, `ANOMALY_IQR_K`, `ANOMALY_MIN_SAMPLE`, `LOG_LEVEL`. `def load_settings_or_exit() -> Settings` (em erro: loga `Configuração inválida: <VAR> <motivo>` para cada variável e levanta `SystemExit(1)`). `app/core/logging.py`: `def configure_logging(level: str) -> None` | TASK-002 | TASK-005, TASK-010, TASK-012, TASK-019, TASK-022 |
| CT-2 | `app/domain/currency.py`: `ISO_4217_CODES: frozenset[str]`; `def normalize_currency_code(raw: str) -> str \| None` (strip + upper; `None` se vazio ou fora da lista) | TASK-001 | TASK-002, TASK-014 |
| CT-3 | `app/core/errors.py`: `class AppError(Exception)` com atributos `code: str`, `message: str`, `http_status: int`, `details: list[Any] \| None`. Subclasses sem argumentos, salvo indicação: `EmptyFileError`, `InvalidCsvError`, `MissingColumnsError(missing: list[str])`, `FileTooLargeError(limit_mb: int)`, `DuplicateFileError(import_id: int)`, `TransactionNotFoundError`, `CategoryNameRequiredError`, `CategoryAlreadyExistsError`, `RuleCategoryNotFoundError`, `RuleNotFoundError`, `InvalidPeriodError`, `InvalidPaginationError`, `ServiceUnavailableError`. `app/api/errors.py`: `def register_exception_handlers(app: FastAPI) -> None`, `class ErrorResponse(BaseModel)` | TASK-003 | TASK-011, TASK-012, TASK-014, TASK-019, TASK-020, TASK-021 |
| CT-4 | `app/infrastructure/db/models.py`: `Base(DeclarativeBase)`, `CategoryModel`, `CategorizationRuleModel`, `ImportModel`, `ImportRejectionModel`, `TransactionModel`, `AnomalyModel` (tabelas/colunas da seção 7). `app/infrastructure/db/session.py`: `def create_engine_from_url(url: str) -> Engine` (`hide_parameters=True`, `pool_pre_ping=True`), `def create_session_factory(engine: Engine) -> sessionmaker[Session]` (`expire_on_commit=False`) | TASK-004 | TASK-005, TASK-007, TASK-008, TASK-009, TASK-010, TASK-012 |
| CT-5 | Schema do banco pela migration `0001` + seed "Não categorizada" (`is_default=true`). `alembic/env.py` usa `config.get_main_option("sqlalchemy.url")` se definida, senão `load_settings_or_exit().database_url`; `target_metadata = Base.metadata` | TASK-005 | TASK-007, TASK-008, TASK-009, TASK-030 |
| CT-6 | `app/domain/entities.py` (dataclasses `frozen=True, slots=True`): `TransactionType(StrEnum)` `EXPENSE="despesa"`, `INCOME="receita"`; `ImportStatus(StrEnum)` `PROCESSING="processando"`, `COMPLETED="concluida"`, `COMPLETED_WITH_REJECTIONS="concluida_com_rejeicoes"`, `FAILED="falhou"`; `Category(id:int, name:str, is_default:bool)`; `CategorizationRule(id:int, keyword:str, category_id:int, priority:int, created_at:datetime)`; `NewTransaction(date:date, description:str, merchant:str, amount:Decimal, currency:str, type:TransactionType, category_id:int, import_id:int, dedup_key:str)`; `Transaction(id:int, date:date, description:str, merchant:str, amount:Decimal, currency:str, type:TransactionType, category_id:int, category_name:str, import_id:int)`; `CategorizableTransaction(id:int, description:str, merchant:str, category_id:int)`; `RowRejection(line_number:int, reason:str)`; `ImportRecord(id:int, filename:str, status:ImportStatus, received_at:datetime, rows_read:int, imported_count:int, rejected_count:int, duplicate_count:int, rejections:tuple[RowRejection, ...])`; `ExpenseRecord(transaction_id:int, date:date, value:Decimal, currency:str, category_id:int, category_name:str, merchant:str)` (value = módulo); `AnomalyCandidate(transaction_id:int, method:str, value:Decimal, reason:str)`; `Anomaly(id:int, method:str, value:Decimal, reason:str, transaction:Transaction)`; `Period(start:date\|None=None, end:date\|None=None)`; `Page(limit:int=50, offset:int=0)`; `TransactionFilters(period:Period=Period(), category_id:int\|None=None, merchant:str\|None=None, import_id:int\|None=None)`; `ExpenseFilters(period:Period=Period(), category_id:int\|None=None, merchant:str\|None=None)`; `PageResult(Generic[T])(items:list[T], total:int)`; `def TransactionType.from_amount(amount: Decimal) -> TransactionType` (negativo → EXPENSE, positivo → INCOME; zero → `ValueError`) | TASK-006 | TASK-007, TASK-008, TASK-009, TASK-010, TASK-011, TASK-013, TASK-014, TASK-015, TASK-016, TASK-017, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022, TASK-023 |
| CT-7 | `app/domain/ports.py` (Protocols). `CategoryRepository`: `add(name:str)->Category`, `get(category_id:int)->Category\|None`, `get_by_name_ci(name:str)->Category\|None`, `get_default()->Category`, `list_all()->list[Category]`. `CategorizationRuleRepository`: `add(keyword:str, category_id:int, priority:int)->CategorizationRule`, `get(rule_id:int)->CategorizationRule\|None`, `list_all()->list[CategorizationRule]` (ordem priority, created_at, id), `update(rule_id:int, keyword:str, category_id:int, priority:int)->CategorizationRule\|None`, `delete(rule_id:int)->bool`. `TransactionRepository`: `insert_ignoring_duplicates(items:Sequence[NewTransaction])->int`, `get(transaction_id:int)->Transaction\|None`, `list(filters:TransactionFilters, page:Page)->PageResult[Transaction]`, `list_expenses(filters:ExpenseFilters)->list[ExpenseRecord]` (só `type='despesa'`, value=abs), `list_all_for_categorization()->list[CategorizableTransaction]`, `update_categories(changes:Mapping[int,int])->None`. `ImportRepository`: `find_completed_by_hash(file_sha256:str)->int\|None` (status concluida ou concluida_com_rejeicoes), `create_processing(filename:str, file_sha256:str, received_at:datetime)->int`, `finish(import_id:int, status:ImportStatus, rows_read:int, imported_count:int, rejected_count:int, duplicate_count:int, rejections:Sequence[RowRejection])->ImportRecord`, `record_failure(filename:str, file_sha256:str, received_at:datetime, reason:str)->int`. `AnomalyRepository`: `replace_all(candidates:Sequence[AnomalyCandidate])->None` (DA-7), `list(period:Period)->list[Anomaly]`. `UnitOfWork`: atributos `categories`, `rules`, `transactions`, `imports`, `anomalies`; `commit()->None`; `rollback()->None`; `__enter__()->Self`; `__exit__(...)->None` (rollback se exceção, sempre fecha a sessão) | TASK-006 | TASK-007, TASK-008, TASK-009, TASK-010, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022, TASK-023 |
| CT-8 | `app/infrastructure/db/repositories/categories.py`: `SqlAlchemyCategoryRepository(session: Session)`; `app/infrastructure/db/repositories/categorization_rules.py`: `SqlAlchemyCategorizationRuleRepository(session: Session)`. Cumprem `CategoryRepository` e `CategorizationRuleRepository` (CT-7). `add` de categoria com nome duplicado propaga `IntegrityError` (o serviço traduz) | TASK-007 | TASK-010 |
| CT-9 | `app/infrastructure/db/unit_of_work.py`: `class SqlAlchemyUnitOfWork(session_factory: sessionmaker[Session])` cumprindo `UnitOfWork`. `app/api/deps.py`: `def get_settings(request: Request) -> Settings` (lê `request.app.state.settings`), `def get_uow(request: Request) -> Iterator[UnitOfWork]` (abre com `with` sobre `request.app.state.session_factory`), `def get_uow_factory(request: Request) -> Callable[[], UnitOfWork]` | TASK-010 | TASK-012, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022, TASK-023, TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029 |
| CT-10 | `app/domain/text.py`: `def normalize_whitespace(value: str) -> str` (strip + colapsa espaços internos em um); `def fold_for_match(value: str) -> str` (NFKD, remove combinantes, `casefold()`) | TASK-013 | TASK-014, TASK-019, TASK-020 |
| CT-11 | `app/domain/categorization.py`: `class RuleMatcher: def __init__(self, rules: Sequence[CategorizationRule], default_category_id: int) -> None; def match(self, description: str, merchant: str) -> int` (menor priority, depois created_at, depois id; sem casamento → default) | TASK-013 | TASK-019, TASK-022 |
| CT-12 | `app/infrastructure/csv_reader.py`: `REQUIRED_COLUMNS = ("date", "description", "amount")`; `@dataclass(frozen=True) RawRow(line_number: int, values: Mapping[str, str])`; `def read_csv_rows(content: bytes) -> list[RawRow]` (só linhas não vazias; levanta `EmptyFileError`, `InvalidCsvError`, `MissingColumnsError`). `app/domain/csv_rows.py`: `@dataclass(frozen=True) ParsedRow(line_number:int, date:date, description:str, merchant:str, amount:Decimal, currency:str, type:TransactionType)`; `def parse_row(line_number: int, values: Mapping[str, str], default_currency: str) -> ParsedRow \| RowRejection`; `def dedup_key(date: date, amount: Decimal, description: str, currency: str) -> str` (DA-6); `def format_rejection(rejection: RowRejection) -> str` → `"Linha {n}: {motivo}"` | TASK-014 | TASK-019, TASK-024 |
| CT-13 | `app/domain/statistics.py`: `def money(value: Decimal) -> Decimal` (quantize 0.01 HALF_UP); `@dataclass SummaryStats(total, count, mean, median)`; `def summarize(values: Sequence[Decimal]) -> SummaryStats` (count=0 → tudo zero); `HISTOGRAM_BOUNDS = (Decimal(0), Decimal(50), Decimal(100), Decimal(500))`; `@dataclass HistogramBucket(range_start: Decimal, range_end: Decimal \| None, count: int, total: Decimal)`; `def histogram(values: Sequence[Decimal]) -> list[HistogramBucket]` (sempre 4); `def percentages(totals: Sequence[Decimal]) -> list[Decimal]` (maior resto, soma 100.00; total 0 → zeros); `@dataclass MerchantTotal(merchant: str, total: Decimal, count: int)`; `def merchant_totals(records: Sequence[ExpenseRecord]) -> list[MerchantTotal]` | TASK-015 | TASK-016, TASK-017, TASK-023 |
| CT-14 | `app/domain/monthly_series.py`: `@dataclass CategoryMonthTotal(category_id:int, category_name:str, total:Decimal, count:int)`; `@dataclass MonthPoint(month:str, total:Decimal, count:int, by_category:list[CategoryMonthTotal])`; `@dataclass CurrencySeries(currency:str, months:list[MonthPoint])`; `def monthly_series(records: Sequence[ExpenseRecord], period: Period) -> list[CurrencySeries]` (P-11; moedas em ordem alfabética) | TASK-016 | TASK-023 |
| CT-15 | `app/domain/anomaly_detection.py`: `IQR_METHOD: Final = "IQR"`; `def detect_iqr_anomalies(records: Sequence[ExpenseRecord], k: float, min_sample: int) -> list[AnomalyCandidate]` (grupos por (category_id, currency); grupo com n < min_sample ignorado; `value` = limite com `money`; reason = `"Valor {valor} {moeda} acima do limite IQR {limite} (Q3 {q3} + {k} × IQR {iqr}) na categoria {categoria}, grupo de {n} despesas."`; saída ordenada por transaction_id) | TASK-017 | TASK-018 |
| CT-16 | `app/application/services/anomaly_service.py`: `class AnomalyService: def __init__(self, uow: UnitOfWork, k: float, min_sample: int) -> None; def recompute_all(self) -> int` (lê `uow.transactions.list_expenses(ExpenseFilters())`, detecta, `uow.anomalies.replace_all`; **não** faz commit; retorna a quantidade); `def list(self, period: Period) -> list[Anomaly]` | TASK-018 | TASK-019, TASK-022, TASK-029 |
| CT-17 | `app/application/services/import_service.py`: `class ImportService: def __init__(self, uow_factory: Callable[[], UnitOfWork], settings: Settings) -> None; def import_csv(self, filename: str, content: bytes) -> ImportRecord` (fluxo 5.2 + DA-16) | TASK-019 | TASK-024 |
| CT-18 | `app/application/services/category_service.py`: `class CategoryService(uow: UnitOfWork)`: `create(name: str \| None) -> Category`, `list() -> list[Category]`. `categorization_rule_service.py`: `class CategorizationRuleService(uow: UnitOfWork)`: `create(keyword: str, category_id: int, priority: int) -> CategorizationRule`, `get(rule_id: int) -> CategorizationRule`, `list() -> list[CategorizationRule]`, `update(rule_id: int, keyword: str, category_id: int, priority: int) -> CategorizationRule`, `delete(rule_id: int) -> None`. Toda escrita faz `commit()` | TASK-020 | TASK-026, TASK-027 |
| CT-19 | `app/application/services/transaction_service.py`: `class TransactionService(uow: UnitOfWork)`: `get(transaction_id: int) -> Transaction` (`TransactionNotFoundError`), `list(filters: TransactionFilters, page: Page) -> PageResult[Transaction]` (merchant normalizado com `normalize_whitespace` antes de consultar) | TASK-021 | TASK-025 |
| CT-20 | `app/application/services/recategorization_service.py`: `@dataclass RecategorizationResult(evaluated: int, changed: int)`; `class RecategorizationService(uow: UnitOfWork, settings: Settings)`: `recategorize() -> RecategorizationResult` (reaplica `RuleMatcher`, `update_categories`, `AnomalyService.recompute_all()`, `commit()`) | TASK-022 | TASK-025 |
| CT-21 | `app/application/services/analytics_service.py`: `@dataclass CurrencySummary(currency, stats: SummaryStats, by_merchant: list[MerchantTotal], histogram: list[HistogramBucket])`; `@dataclass CategoryBreakdown(category_id, category_name, stats: SummaryStats, percentage: Decimal)`; `@dataclass CurrencyCategories(currency, total: Decimal, categories: list[CategoryBreakdown])`; `class AnalyticsService(uow: UnitOfWork)`: `summary(filters: ExpenseFilters) -> list[CurrencySummary]`, `categories(period: Period) -> list[CurrencyCategories]`, `monthly(period: Period) -> list[CurrencySeries]`. Moedas em ordem alfabética | TASK-023 | TASK-028 |
| CT-22 | `app/api/params.py`: `def period_params(start_date: date \| None = Query(None), end_date: date \| None = Query(None)) -> Period` (`InvalidPeriodError` se start > end); `def pagination_params(limit: int = Query(50), offset: int = Query(0)) -> Page` (`InvalidPaginationError` fora de 1..500 / <0). `app/api/schemas/common.py`: `Money = Annotated[Decimal, PlainSerializer(..., return_type=str)]` (2 casas); `class CategoryRef(BaseModel)(id:int, name:str)`; `class TransactionOut(BaseModel)` (campos de 8.1) com `@classmethod from_entity(cls, t: Transaction) -> TransactionOut` | TASK-011 | TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029 |
| CT-23 | `tests/integration/conftest.py` — fixtures: `postgres_url` (session; `TEST_DATABASE_URL` ou `PostgresContainer("postgres:16-alpine", driver="psycopg")`), `engine` (session; `alembic.command.upgrade(cfg, "head")` com `sqlalchemy.url=postgres_url`, depois `create_engine_from_url`), `session_factory` (session), `settings` (function; `Settings(database_url=postgres_url, _env_file=None)`), `clean_db` (autouse, function; depois do teste: `TRUNCATE anomalies, transactions, import_rejections, imports, categorization_rules RESTART IDENTITY CASCADE` e `DELETE FROM categories WHERE NOT is_default`), `uow_factory` (import tardio de `SqlAlchemyUnitOfWork`, retorna `lambda: SqlAlchemyUnitOfWork(session_factory)`), `uow` (`with uow_factory() as u: yield u`), `client` (import tardio de `create_app`; `with TestClient(create_app(settings)) as c: yield c`) | TASK-005 | TASK-007, TASK-008, TASK-009, TASK-010, TASK-012, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022, TASK-023, TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029, TASK-032 |
| CT-24 | `app/infrastructure/db/repositories/transactions.py`: `SqlAlchemyTransactionRepository(session: Session)` cumprindo `TransactionRepository` (CT-7) | TASK-008 | TASK-010 |
| CT-25 | `app/infrastructure/db/repositories/imports.py` `SqlAlchemyImportRepository(session)` e `anomalies.py` `SqlAlchemyAnomalyRepository(session)` + `ANOMALY_LOCK_KEY` | TASK-009 | TASK-010 |
| CT-26 | `app/main.py`: `def create_app(settings: Settings \| None = None) -> FastAPI` (None → `load_settings_or_exit()`; `configure_logging`; `app.state.settings`, `app.state.engine`, `app.state.session_factory`; `register_exception_handlers`; `GET /health`; lifespan faz `engine.dispose()` no shutdown). Routers são registrados com `app.include_router(<router>)` pelas tasks de router | TASK-012 | TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029, TASK-030, TASK-032 |
| CT-27 | Rotas HTTP da seção 8.1 (paths, métodos, status e corpos) | TASK-024 (imports), TASK-025 (transactions), TASK-026 (categories), TASK-027 (categorization-rules), TASK-028 (analytics), TASK-029 (anomalies) — contrato externo, sem produtor único na tabela de tasks | TASK-032 |

Observação: os repositórios SQLAlchemy estão divididos em CT-8 (TASK-007), CT-24 (TASK-008) e CT-25 (TASK-009), um produtor por contrato. CT-27 é referência externa: as tasks de router citam só CT-22 e CT-26, e a TASK-032 depende de todas as
tasks de router.

### 8.3 Catálogo de erros
| Código | Quando ocorre | Mensagem ao usuário | HTTP |
|---|---|---|---|
| `VALIDATION_ERROR` | `RequestValidationError` do FastAPI/Pydantic (tipo inválido, campo obrigatório ausente, data fora de ISO, id não inteiro, keyword vazia, priority não inteira). `details` = `[{"field": "<loc>", "message": "<msg>"}]` | "Dados de entrada inválidos." | 422 |
| `EMPTY_FILE` | CSV sem bytes, só cabeçalho, ou só cabeçalho e linhas vazias (SEA-90) | "O arquivo enviado não contém transações." | 422 |
| `INVALID_CSV` | Não decodifica em UTF-8, contém byte NUL, ou o pandas não consegue interpretar (SEA-91, P-05) | "Não foi possível ler o arquivo como CSV." | 422 |
| `MISSING_COLUMNS` | Falta `date`, `description` ou `amount` (SEA-92). `details` = lista das ausentes | "Colunas obrigatórias ausentes: {lista}." | 422 |
| `FILE_TOO_LARGE` | Conteúdo > `MAX_UPLOAD_MB` MiB (SEA-104) | "O arquivo excede o tamanho máximo de {limite} MB." | 413 |
| `DUPLICATE_FILE` | Hash igual ao de Import `concluida`/`concluida_com_rejeicoes` (SEA-43) | "Este arquivo já foi importado (importação {id})." | 409 |
| `TRANSACTION_NOT_FOUND` | `GET /transactions/{id}` inexistente (SEA-93) | "Transação não encontrada." | 404 |
| `CATEGORY_NAME_REQUIRED` | Nome ausente, vazio ou só espaços (SEA-16) | "O nome da categoria é obrigatório." | 422 |
| `CATEGORY_ALREADY_EXISTS` | Nome igual sem distinguir caixa (SEA-53), inclusive via `IntegrityError` de `uq_categories_name_ci` | "Já existe uma categoria com este nome." | 409 |
| `RULE_CATEGORY_NOT_FOUND` | Regra aponta para Category inexistente (SEA-18) | "Categoria informada na regra não existe." | 422 |
| `RULE_NOT_FOUND` | GET/PUT/DELETE de regra inexistente (SEA-49) | "Regra de categorização não encontrada." | 404 |
| `INVALID_PERIOD` | `start_date` > `end_date` (SEA-99) | "A data inicial deve ser anterior ou igual à data final." | 422 |
| `INVALID_PAGINATION` | limit < 1 ou > 500, offset < 0 (SEA-105) | "Parâmetros de paginação inválidos: limit deve estar entre 1 e 500 e offset não pode ser negativo." | 422 |
| `SERVICE_UNAVAILABLE` | `sqlalchemy.exc.OperationalError` / `InterfaceError`, ou `ServiceUnavailableError` (SEA-97) | "Serviço temporariamente indisponível. Tente novamente." | 503 |
| `INTERNAL_ERROR` | Qualquer outra exceção. `error_id` = `uuid4().hex`, presente no corpo e no log (SEA-06) | "Erro interno. Identificador: {id}." | 500 |
| `NOT_FOUND` / `METHOD_NOT_ALLOWED` / `HTTP_<status>` | `StarletteHTTPException` (rota inexistente, método não permitido) | "Recurso não encontrado." / "Método não permitido." / texto do Starlette | 404 / 405 / status |

Motivos de rejeição de linha (`import_rejections.reason`, exibidos como `"Linha {n}: {motivo}"`): `data ausente`, `data inválida`,
`descrição vazia`, `valor ausente`, `valor não numérico`, `valor igual a zero`, `moeda fora da ISO 4217` (P-06: vários motivos juntados por "; ").

## 9. Componentes Afetados

Todos os arquivos são **novos** (greenfield).

| Arquivo / módulo | Tipo de impacto | Requisitos atendidos |
|---|---|---|
| `pyproject.toml` | novo | `SEA-04` |
| `.gitignore` | novo (wiring TASK-001) | — |
| `app/__init__.py`, `app/core/__init__.py`, `app/domain/__init__.py`, `app/api/__init__.py`, `app/api/routers/__init__.py`, `app/api/schemas/__init__.py`, `app/application/__init__.py`, `app/application/services/__init__.py`, `app/infrastructure/__init__.py`, `app/infrastructure/db/__init__.py`, `app/infrastructure/db/repositories/__init__.py` | novo (vazios, wiring TASK-001) | — |
| `app/domain/currency.py` | novo | `SEA-38`, `SEA-108` |
| `app/core/config.py` | novo | `SEA-03`, `SEA-108`, `SEA-58`, `SEA-59` |
| `app/core/logging.py` | novo | `SEA-14`, `SEA-06` |
| `app/core/errors.py` | novo | `SEA-05`, `SEA-90`–`SEA-93`, `SEA-99`, `SEA-104`, `SEA-105` |
| `app/api/errors.py` | novo | `SEA-05`, `SEA-06`, `SEA-97`, `SEA-100` |
| `app/infrastructure/db/models.py` | novo | `SEA-07`, `SEA-09`, `SEA-39` |
| `app/infrastructure/db/session.py` | novo | `SEA-97` |
| `alembic.ini`, `alembic/script.py.mako` | novo (wiring TASK-005) | `SEA-01` |
| `alembic/env.py` | novo | `SEA-01` |
| `alembic/versions/0001_initial_schema.py` | novo | `SEA-01`, `SEA-52` |
| `app/domain/entities.py` | novo | `SEA-39` |
| `app/domain/ports.py` | novo | — (portas) |
| `app/infrastructure/db/repositories/categories.py` | novo | `SEA-51`, `SEA-53` |
| `app/infrastructure/db/repositories/categorization_rules.py` | novo | `SEA-47`, `SEA-48` |
| `app/infrastructure/db/repositories/transactions.py` | novo | `SEA-11`, `SEA-13`, `SEA-21`, `SEA-25`, `SEA-39`, `SEA-44`, `SEA-67`, `SEA-68`, `SEA-101`, `SEA-106` |
| `app/infrastructure/db/repositories/imports.py` | novo | `SEA-41`, `SEA-43`, `SEA-107` |
| `app/infrastructure/db/repositories/anomalies.py` | novo | `SEA-27`, `SEA-30`, `SEA-31` |
| `app/infrastructure/db/unit_of_work.py` | novo | `SEA-97` |
| `app/api/deps.py` | novo | — (DI) |
| `app/api/params.py` | novo | `SEA-13`, `SEA-57`, `SEA-67`, `SEA-99`, `SEA-100`, `SEA-105` |
| `app/api/schemas/common.py` | novo | `SEA-11`, `SEA-40` |
| `app/main.py` | novo | `SEA-02` |
| `app/domain/text.py` | novo | `SEA-09`, `SEA-46` |
| `app/domain/categorization.py` | novo | `SEA-17`, `SEA-19`, `SEA-46`, `SEA-47`, `SEA-52` |
| `app/infrastructure/csv_reader.py` | novo | `SEA-10`, `SEA-36`, `SEA-90`, `SEA-91`, `SEA-92` |
| `app/domain/csv_rows.py` | novo | `SEA-09`, `SEA-36`–`SEA-39`, `SEA-41`, `SEA-110` |
| `app/domain/statistics.py` | novo | `SEA-20`, `SEA-22`, `SEA-26`, `SEA-54`, `SEA-55`, `SEA-56` |
| `app/domain/monthly_series.py` | novo | `SEA-32`, `SEA-33`, `SEA-34`, `SEA-54`, `SEA-62` |
| `app/domain/anomaly_detection.py` | novo | `SEA-28`, `SEA-29`, `SEA-54`, `SEA-58`, `SEA-59`, `SEA-96` |
| `app/application/services/anomaly_service.py` | novo | `SEA-27`, `SEA-29`, `SEA-30`, `SEA-31`, `SEA-57`, `SEA-60` |
| `app/application/services/import_service.py` | novo | `SEA-07`, `SEA-08`, `SEA-14`, `SEA-17`, `SEA-41`–`SEA-45`, `SEA-60`, `SEA-97`, `SEA-98`, `SEA-102`–`SEA-104`, `SEA-106`, `SEA-107` |
| `app/application/services/category_service.py` | novo | `SEA-15`, `SEA-16`, `SEA-51`, `SEA-53` |
| `app/application/services/categorization_rule_service.py` | novo | `SEA-18`, `SEA-48`, `SEA-49`, `SEA-50`, `SEA-64` |
| `app/application/services/transaction_service.py` | novo | `SEA-11`, `SEA-12`, `SEA-93` |
| `app/application/services/recategorization_service.py` | novo | `SEA-63`, `SEA-65`, `SEA-66`, `SEA-109` |
| `app/application/services/analytics_service.py` | novo | `SEA-20`–`SEA-25`, `SEA-54`–`SEA-57`, `SEA-61`, `SEA-62`, `SEA-95`, `SEA-101` |
| `app/api/routers/imports.py`, `app/api/schemas/imports.py` | novo | `SEA-07`, `SEA-08`, `SEA-35`, `SEA-42`, `SEA-43`, `SEA-45`, `SEA-90`–`SEA-92`, `SEA-104` |
| `app/api/routers/transactions.py`, `app/api/schemas/transactions.py` | novo | `SEA-11`–`SEA-13`, `SEA-35`, `SEA-40`, `SEA-63`, `SEA-67`, `SEA-68`, `SEA-93`, `SEA-94` |
| `app/api/routers/categories.py`, `app/api/schemas/categories.py` | novo | `SEA-15`, `SEA-16`, `SEA-35`, `SEA-51`, `SEA-53` |
| `app/api/routers/categorization_rules.py`, `app/api/schemas/categorization_rules.py` | novo | `SEA-18`, `SEA-35`, `SEA-48`, `SEA-49`, `SEA-50` |
| `app/api/routers/analytics.py`, `app/api/schemas/analytics.py` | novo | `SEA-20`–`SEA-24`, `SEA-35`, `SEA-54`–`SEA-57`, `SEA-61`, `SEA-95` |
| `app/api/routers/anomalies.py`, `app/api/schemas/anomalies.py` | novo | `SEA-27`, `SEA-31`, `SEA-35`, `SEA-96` |
| `Dockerfile`, `docker-compose.yml` | novo | `SEA-01` |
| `.env.example`, `.dockerignore` | novo (wiring TASK-030) | `SEA-01` |
| `.github/workflows/ci.yml` | novo | `SEA-04` |
| `README.md` | novo | `SEA-01`, `SEA-04` |
| `samples/transacoes_exemplo.csv` | novo | `SEA-02`, `SEA-35` (critérios de sucesso do spec) |
| `tests/unit/**`, `tests/integration/**` (incl. `tests/integration/conftest.py`) | novo | todos (co-location) |

## 10. Rastreabilidade Requisito → Componente

| ID do spec | Componentes / camadas | Contrato |
|---|---|---|
| `SEA-01` | `alembic/versions/0001_initial_schema.py`, `alembic/env.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `README.md` | CT-5, CT-26 |
| `SEA-02` | `app/main.py`, todos os routers, `samples/transacoes_exemplo.csv` (teste de aceitação) | CT-26, CT-27 |
| `SEA-03` | `app/core/config.py` | CT-1 |
| `SEA-04` | `.github/workflows/ci.yml`, `pyproject.toml` | — |
| `SEA-05` | `app/core/errors.py`, `app/api/errors.py` | CT-3 |
| `SEA-06` | `app/api/errors.py`, `app/core/logging.py` | CT-3, CT-1 |
| `SEA-07` | `import_service.py`, `routers/imports.py`, `repositories/transactions.py` | CT-17, CT-24 |
| `SEA-08` | `import_service.py`, `schemas/imports.py` | CT-17 |
| `SEA-09` | `domain/csv_rows.py`, `domain/text.py`, `models.py` (NUMERIC(14,2), DATE) | CT-12, CT-10, CT-4 |
| `SEA-10` | `infrastructure/csv_reader.py` | CT-12 |
| `SEA-11` | `transaction_service.py`, `routers/transactions.py`, `schemas/common.py`, `repositories/transactions.py` | CT-19, CT-22 |
| `SEA-12` | `transaction_service.py`, `routers/transactions.py` | CT-19 |
| `SEA-13` | `repositories/transactions.py`, `api/params.py`, `routers/transactions.py` | CT-24, CT-22 |
| `SEA-14` | `import_service.py`, `core/logging.py` | CT-17 |
| `SEA-15` | `category_service.py`, `routers/categories.py` | CT-18 |
| `SEA-16` | `category_service.py`, `routers/categories.py` | CT-18, CT-3 |
| `SEA-17` | `domain/categorization.py`, `import_service.py` | CT-11 |
| `SEA-18` | `categorization_rule_service.py`, `routers/categorization_rules.py` | CT-18 |
| `SEA-19` | `domain/categorization.py` | CT-11 |
| `SEA-20` | `domain/statistics.py`, `analytics_service.py`, `routers/analytics.py` | CT-13, CT-21 |
| `SEA-21` | `repositories/transactions.py` (`list_expenses`), `analytics_service.py`, `routers/analytics.py` | CT-24, CT-21 |
| `SEA-22` | `domain/statistics.py` (`merchant_totals`), `analytics_service.py`, `schemas/analytics.py` | CT-13, CT-21 |
| `SEA-23` | `analytics_service.py`, `routers/analytics.py` | CT-21 |
| `SEA-24` | `analytics_service.py`, `routers/analytics.py`, `api/params.py` | CT-21, CT-22 |
| `SEA-25` | `repositories/transactions.py` (`list_expenses` filtra despesa), `analytics_service.py` | CT-7, CT-21 |
| `SEA-26` | `domain/statistics.py` | CT-13 |
| `SEA-27` | `anomaly_service.py`, `repositories/anomalies.py`, `routers/anomalies.py` | CT-16, CT-25 |
| `SEA-28` | `domain/anomaly_detection.py` | CT-15 |
| `SEA-29` | `domain/anomaly_detection.py`, `anomaly_service.py` (usa `list_expenses`) | CT-15, CT-16 |
| `SEA-30` | `repositories/anomalies.py` (`replace_all`, unique), `anomaly_service.py` | CT-25, CT-16 |
| `SEA-31` | `repositories/anomalies.py` (`list(period)`), `routers/anomalies.py` | CT-25, CT-22 |
| `SEA-32` | `domain/monthly_series.py`, `analytics_service.py`, `routers/analytics.py` | CT-14, CT-21 |
| `SEA-33` | `domain/monthly_series.py` | CT-14 |
| `SEA-34` | `domain/monthly_series.py`, `schemas/analytics.py` | CT-14 |
| `SEA-35` | todos os routers (sem dependência de auth), teste de aceitação | CT-27 |
| `SEA-36` | `csv_reader.py`, `csv_rows.py` | CT-12 |
| `SEA-37` | `csv_rows.py` | CT-12 |
| `SEA-38` | `domain/currency.py`, `csv_rows.py` | CT-2, CT-12 |
| `SEA-39` | `csv_rows.py`, `entities.py` (`TransactionType.from_amount`), `repositories/transactions.py` | CT-12, CT-6 |
| `SEA-40` | `schemas/common.py` (`TransactionOut`), `routers/transactions.py` | CT-22 |
| `SEA-41` | `csv_rows.py`, `import_service.py`, `repositories/imports.py` | CT-12, CT-17, CT-25 |
| `SEA-42` | `import_service.py`, `schemas/imports.py` | CT-17 |
| `SEA-43` | `repositories/imports.py` (`find_completed_by_hash`), `import_service.py`, `routers/imports.py` | CT-25, CT-17 |
| `SEA-44` | `repositories/transactions.py` (`insert_ignoring_duplicates`), `import_service.py`, `csv_rows.py` (`dedup_key`) | CT-24, CT-12 |
| `SEA-45` | `import_service.py`, `routers/imports.py` | CT-17 |
| `SEA-46` | `domain/text.py`, `domain/categorization.py` | CT-10, CT-11 |
| `SEA-47` | `domain/categorization.py`, `repositories/categorization_rules.py` (ordem) | CT-11, CT-8 |
| `SEA-48` | `categorization_rule_service.py`, `routers/categorization_rules.py`, `repositories/categorization_rules.py` | CT-18, CT-8 |
| `SEA-49` | `categorization_rule_service.py`, `routers/categorization_rules.py` | CT-18 |
| `SEA-50` | `schemas/categorization_rules.py`, `categorization_rule_service.py` | CT-18 |
| `SEA-51` | `repositories/categories.py`, `category_service.py`, `routers/categories.py` | CT-8, CT-18 |
| `SEA-52` | `0001_initial_schema.py` (seed), `domain/categorization.py` (default) | CT-5, CT-11 |
| `SEA-53` | `repositories/categories.py`, `category_service.py`, `routers/categories.py` | CT-8, CT-18 |
| `SEA-54` | `statistics.py`, `monthly_series.py`, `anomaly_detection.py`, `analytics_service.py`, `routers/analytics.py` | CT-13, CT-14, CT-15, CT-21 |
| `SEA-55` | `statistics.py` (`percentages`), `analytics_service.py` | CT-13, CT-21 |
| `SEA-56` | `statistics.py` (`histogram`), `analytics_service.py` | CT-13, CT-21 |
| `SEA-57` | `analytics_service.py`, `anomaly_service.py`, `api/params.py` | CT-21, CT-16, CT-22 |
| `SEA-58` | `anomaly_detection.py`, `core/config.py` (`ANOMALY_IQR_K`) | CT-15, CT-1 |
| `SEA-59` | `anomaly_detection.py`, `core/config.py` (`ANOMALY_MIN_SAMPLE`) | CT-15, CT-1 |
| `SEA-60` | `anomaly_service.py`, `import_service.py` | CT-16, CT-17 |
| `SEA-61` | `routers/analytics.py`, `analytics_service.py` | CT-21 |
| `SEA-62` | `monthly_series.py`, `analytics_service.py` | CT-14, CT-21 |
| `SEA-63` | `recategorization_service.py`, `routers/transactions.py` | CT-20 |
| `SEA-64` | `categorization_rule_service.py` (não toca transações) | CT-18 |
| `SEA-65` | `recategorization_service.py` | CT-20, CT-16 |
| `SEA-66` | `recategorization_service.py` | CT-20 |
| `SEA-67` | `repositories/transactions.py`, `api/params.py`, `routers/transactions.py` | CT-24, CT-22 |
| `SEA-68` | `repositories/transactions.py`, `routers/transactions.py` | CT-24 |
| `SEA-90` | `csv_reader.py`, `routers/imports.py` | CT-12, CT-3 |
| `SEA-91` | `csv_reader.py`, `routers/imports.py` | CT-12, CT-3 |
| `SEA-92` | `csv_reader.py`, `routers/imports.py` | CT-12, CT-3 |
| `SEA-93` | `transaction_service.py`, `routers/transactions.py` | CT-19, CT-3 |
| `SEA-94` | `routers/transactions.py` (path `int`), `api/errors.py` | CT-3 |
| `SEA-95` | `analytics_service.py`, `routers/analytics.py` | CT-21 |
| `SEA-96` | `anomaly_detection.py`, `routers/anomalies.py` | CT-15 |
| `SEA-97` | `api/errors.py` (503), `session.py` (pre-ping), `import_service.py` (DA-16), `unit_of_work.py` | CT-3, CT-17, CT-9 |
| `SEA-98` | `import_service.py`, `repositories/transactions.py` | CT-17 |
| `SEA-99` | `api/params.py` | CT-22 |
| `SEA-100` | `api/params.py`, `api/errors.py` | CT-22, CT-3 |
| `SEA-101` | `repositories/transactions.py`, `analytics_service.py` | CT-24, CT-21 |
| `SEA-102` | `import_service.py` | CT-17 |
| `SEA-103` | `import_service.py` | CT-17 |
| `SEA-104` | `import_service.py`, `routers/imports.py` | CT-17, CT-3 |
| `SEA-105` | `api/params.py` | CT-22 |
| `SEA-106` | `repositories/transactions.py` (`ON CONFLICT`), `import_service.py` | CT-24, CT-17 |
| `SEA-107` | `repositories/imports.py`, `import_service.py` | CT-25, CT-17 |
| `SEA-108` | `core/config.py`, `domain/currency.py` | CT-1, CT-2 |
| `SEA-109` | `recategorization_service.py` | CT-20 |
| `SEA-110` | `csv_rows.py` | CT-12 |

## 11. Dependências Externas

Todas são novas, porque o projeto é greenfield. As versões mínimas vão no `pyproject.toml` (TASK-001):

| Pacote | Faixa | Uso / justificativa |
|---|---|---|
| fastapi | `>=0.115,<1` | stack definida |
| uvicorn[standard] | `>=0.30` | servidor ASGI |
| pydantic | `>=2.7,<3` | stack definida |
| pydantic-settings | `>=2.3,<3` | configuração por env (objetivo 8). Pacote oficial do Pydantic. |
| sqlalchemy | `>=2.0,<2.1` | stack definida |
| alembic | `>=1.13` | stack definida |
| psycopg[binary] | `>=3.1,<4` | driver PostgreSQL (URL `postgresql+psycopg://`) |
| pandas | `>=2.2,<3` | stack definida (leitura CSV, groupby) |
| numpy | `>=1.26,<3` | stack definida (quartis) |
| python-multipart | `>=0.0.9` | exigido pelo FastAPI para `UploadFile` |
| dev: pytest | `>=8` | stack definida |
| dev: httpx | `>=0.27` | exigido pelo `TestClient` |
| dev: testcontainers[postgres] | `>=4.4` | PostgreSQL descartável por processo de teste (DA-14) |
| dev: ruff | `>=0.5` | lint |
| dev: mypy | `>=1.10` | typecheck (type hints obrigatórios) |
| dev: pandas-stubs | `>=2.2` | tipos do pandas para `mypy --strict` |

Variáveis de ambiente (documentadas em `.env.example`, **sem segredos reais**): `DATABASE_URL`, `DEFAULT_CURRENCY`,
`MAX_UPLOAD_MB`, `ANOMALY_IQR_K`, `ANOMALY_MIN_SAMPLE`, `LOG_LEVEL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
(estas três só para o serviço `db` do Compose). Nos testes, `TEST_DATABASE_URL` (opcional, só no CI).

Infra: imagem `python:3.12-slim` (API) e `postgres:16-alpine` (banco, CI e testes). Nenhum serviço de terceiro.

## 12. Áreas Sensíveis

| ID | Eixo | Situação | Componentes envolvidos |
|---|---|---|---|
| AS-1 | Autenticação / autorização / sessão | NÃO (LAC-01 remove autenticação; nada a escrever) | — |
| AS-2 | Pagamento / faturamento / cálculo financeiro | NÃO (estatística descritiva de gastos já feitos, sem mover dinheiro) | — |
| AS-3 | Dados pessoais ou sensíveis (PII, saúde, financeiro) | SIM: descrições, estabelecimentos e valores de lançamentos financeiros pessoais são lidos do CSV, persistidos e podem vazar por log ou por mensagem de erro | `app/infrastructure/csv_reader.py`, `app/domain/csv_rows.py`, `app/application/services/import_service.py`, `app/infrastructure/db/repositories/transactions.py`, `app/core/logging.py`, `app/api/errors.py` |
| AS-4 | Migration com dados existentes em produção | NÃO (greenfield: a 0001 cria tabelas vazias) | — |
| AS-5 | Lógica regulatória / fiscal / compliance | NÃO | — |
| AS-6 | Endpoint público sem autenticação | SIM: todos os endpoints leem e alteram dados financeiros sem credencial (LAC-01, risco aceito). Mitigação DA-12. | `app/api/routers/imports.py`, `app/api/routers/transactions.py`, `app/api/routers/categories.py`, `app/api/routers/categorization_rules.py`, `app/api/routers/analytics.py`, `app/api/routers/anomalies.py` |
| AS-7 | Criptografia / manuseio de chaves e segredos | NÃO (só leitura de `DATABASE_URL` do ambiente. O SHA-256 é para deduplicação, não para segurança.) | — |
| AS-8 | Integração externa nova com terceiro | NÃO | — |

## 13. Migração e Rollback

- **Script de ida**: `alembic/versions/0001_initial_schema.py` `upgrade()` cria as 6 tabelas, constraints e índices da seção 7 e insere "Não categorizada" (`is_default=true`). É aplicado automaticamente no start do contêiner (`alembic upgrade head`, DA-13) e na fixture `engine` dos testes.
- **Script de volta**: `downgrade()` remove `anomalies`, `transactions`, `import_rejections`, `imports`, `categorization_rules` e `categories`, nesta ordem. Comando: `alembic downgrade base` (dentro do contêiner: `docker compose run --rm api alembic downgrade base`). A TASK-005 testa ida → volta → ida.
- **Compatibilidade**: não se aplica. Não existe versão anterior do código nem do schema (greenfield).
- **Backfill**: não há. O único dado inserido é a categoria padrão (1 linha). O `INSERT` é idempotente por natureza da migration (roda uma vez por revisão).
- **Janela**: não exige. Ambiente local de demonstração, sem produção (seção 3 do spec).

## 14. Observabilidade

Formato: texto `"%(asctime)s %(levelname)s %(name)s %(message)s"`, com a mensagem em `evento chave=valor`. Nível por `LOG_LEVEL`. Loggers `logging.getLogger(__name__)`.

- **Logar**:
  - `import_started import_id=<id> filename=<nome> size_bytes=<n>` (INFO, SEA-14)
  - `import_finished import_id=<id> filename=<nome> status=<status> rows_read=<n> imported=<n> rejected=<n> duplicates=<n> duration_ms=<n>` (INFO, SEA-14)
  - `import_rejected_structural filename=<nome> code=<EMPTY_FILE|INVALID_CSV|MISSING_COLUMNS|FILE_TOO_LARGE|DUPLICATE_FILE>` (INFO)
  - `import_failed import_id=<id|none> filename=<nome> reason=<NomeDaExcecao>` (ERROR, SEA-97)
  - `anomalies_recomputed count=<n> groups_evaluated=<n>` (INFO)
  - `recategorization_finished evaluated=<n> changed=<n>` (INFO)
  - `unexpected_error error_id=<hex> path=<rota> method=<verbo>` + traceback via `logger.exception` (ERROR, SEA-06)
  - `database_unavailable path=<rota>` (ERROR, SEA-97)
  - Configuração inválida: `Configuração inválida: <VARIAVEL> <motivo>` (CRITICAL, SEA-03, SEA-108)
- **NÃO logar**: conteúdo de linhas do CSV, `description`, `merchant`, `amount` de transações, `keyword` de regras, query strings (`--no-access-log`, DA-13), parâmetros SQL (`hide_parameters=True`, DA-15), valor de `DATABASE_URL` ou senha (o log de config cita só o **nome** da variável). Rejeições gravam só o motivo, nunca o valor da célula.
- **Métricas / alertas**: não se aplica nesta feature (sem stack de métricas pedida). A contagem por import fica nos logs e na tabela `imports`.
- **Auditoria**: a tabela `imports` guarda nome do arquivo, hash, status, contagens, motivo de falha e horários de cada envio, e `import_rejections` guarda as linhas recusadas. Retenção: enquanto existir o volume do banco (não há exclusão pela API, LAC-09).

## 15. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| R-1: Comandos da seção 3 não confirmados em arquivo (greenfield). O baseline do `/implement` roda antes da TASK-001 e todos os alvos falham ou ficam cegos. `docker compose build api` só funciona depois da TASK-030. | alta | médio | A TASK-001 cria o `pyproject.toml` com a configuração exata. O Done when da TASK-001 exige rodar lint, typecheck e suíte com sucesso. O build fica cego (G4) até a TASK-030. |
| R-2: Docker indisponível na máquina do `/implement` quebra todos os testes de integração (Testcontainers). | média | alto | Docker já é requisito do spec (Compose). O `doctor`/baseline mostra a falha cedo. Alternativa sem mudar código: exportar `TEST_DATABASE_URL` apontando para um PostgreSQL local, mas aí as tasks de integração **não** podem rodar em paralelo. |
| R-3: O comportamento de `pandas.read_csv` com `skip_blank_lines=False` / `na_filter=False` difere do previsto e distorce o número de linha ou a detecção de linha vazia. | média | médio | A TASK-014 tem testes explícitos de número de linha com linhas vazias intercaladas (P-07, SEA-10). A detecção de vazia trata `""` e `NaN`. |
| R-4: Corrida entre imports concorrentes no recálculo de anomalias gera deadlock ou violação de unique. | baixa | médio | Advisory lock transacional (DA-7), tomado só ao final do import. Teste de concorrência na TASK-019 (SEA-98, SEA-106). |
| R-5: `lower()` do PostgreSQL não trata acentos se o banco usar locale C, e "NÃO CATEGORIZADA" passaria na unicidade. | baixa | baixo | A imagem `postgres:16-alpine` usa `en_US.utf8` por padrão. O serviço também compara com `get_by_name_ci`. Teste com "não categorizada" na TASK-020. |
| R-6: TASK-014 em `médio` (LAC-21 = B) roda sem QA semântico dedicado. | baixa | médio | Mais de 18 testes unitários exigidos no Done when, incluindo número de linha, rejeições e ausência de conteúdo de célula nas mensagens. |
| R-7: API aberta sem autenticação (risco aceito LAC-01) exposta por engano. | baixa | alto | DA-12 (bind em 127.0.0.1) + aviso no README (TASK-031). |
| R-8: `mypy --strict` com pandas/numpy gera ruído de tipos. | média | baixo | `pandas-stubs` no dev. Uso de pandas/numpy confinado a `csv_reader.py` e `anomaly_detection.py`. `# type: ignore[<código>]` só com código específico. |

Nenhuma stack ou framework fora da lista definida pelo usuário, exceto os complementos obrigatórios da própria stack
(pydantic-settings, psycopg, python-multipart, httpx) e as ferramentas de qualidade (ruff, mypy, testcontainers,
pandas-stubs), justificados na seção 11. Nenhum exige aprovação adicional.

## 16. Critérios de Aceite Técnicos

- [ ] `ruff check . --output-format=concise` sai com código 0.
- [ ] `mypy app` (strict) sai com código 0.
- [ ] `pytest -q` passa com 0 falhas e gera `reports/junit.xml`. Todo ID `SEA-*` do spec tem ao menos um teste que o cita no nome ou na docstring.
- [ ] `docker compose up -d --build` a partir de `cp .env.example .env` deixa `GET http://localhost:8000/health` = 200 e `GET /openapi.json` com os 12 caminhos de 8.1.
- [ ] `docker compose run --rm api alembic downgrade base` e depois `alembic upgrade head` executam sem erro.
- [ ] O workflow `.github/workflows/ci.yml` roda em `push` e `pull_request`, com serviço `postgres:16-alpine`, e executa `ruff`, `mypy` e `pytest`.
- [ ] Nenhuma linha de log gerada pelos testes de import contém a descrição de uma transação do CSV de teste (teste na TASK-019).

## Autoverificação do plano

Itens de julgamento sob responsabilidade do plan-architect (os mecânicos ficam com o `check_plan.py`):

- [x] **B3**: as 21 decisões de `decisions.md` (LAC-01 a LAC-20 e LAC-16b) estão na seção 2.1 com consequência. LAC-21 (risco da TASK-014 = médio) também está em 2.1.
- [x] **B4**: as premissas P-01 e P-02 de `decisions.md` e as premissas novas P-03 a P-16 estão na 2.2, com reversibilidade.
- [ ] **C1**: os comandos da seção 3 **não** estão confirmados em arquivo, porque o projeto é greenfield e não há `pyproject.toml`. Estão definidos aqui e são criados pela TASK-001 e pela TASK-030. Registrado como R-1. Esta é uma falha conhecida e aceita pelo orquestrador ("comandos precisam ser definidos no plan e criados pela primeira task").
- [x] **C4**: typecheck, suíte e build têm comando. Até a TASK-030 o build falha no baseline e fica cego (G4). Ressalva destacada em R-1.
- [x] **D2**: todo contrato consumido tem task produtora (CT-1 a CT-26). CT-27 é contrato externo, produzido pelas 6 tasks de router e consumido pela TASK-032, que depende de todas elas. Nenhum contrato vem de código existente (greenfield).
- [x] **I5**: a seção 6 justifica a ausência de reuso de código existente (confirmado: raiz só com `.specs/`) e lista o reuso interno obrigatório.
- [x] **I6**: seção 13 preenchida (ida, volta, compatibilidade, backfill, janela).
- [x] **I7**: seção 14 preenchida para AS-3 e AS-6 (logar, não logar, métricas, auditoria).
- [x] **I8**: diagrama mermaid do fluxo principal em 5.2.
- [x] Toda task paralela previsível tem CT-n (repositórios × UoW, serviços × routers, fixtures CT-23).
- [x] Toda AS `SIM` lista arquivos concretos da seção 9.
- [x] Todo arquivo que as tasks criam aparece na seção 9.
- [x] Nenhum trecho de implementação: só assinaturas, tipos, SQL de índice e comandos.

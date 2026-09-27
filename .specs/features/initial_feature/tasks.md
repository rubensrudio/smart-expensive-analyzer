# Tarefas — Smart Expense Analyzer (feature inicial)

Gate padrão de toda task: `pytest -q {files}` com os `Arquivos de teste` da task (seção 3 do plan), mais
`ruff check . --output-format=concise` e `mypy app` sem erros novos. Os testes de integração exigem Docker em
execução e `TEST_DATABASE_URL` ausente (plan, seção 3).

Conferência de sanidade de risco (`risco.md`): 7 tasks `alto` de 32 (22%), abaixo do teto de 30%. A TASK-014 ficou
em `médio` por decisão humana (LAC-21 = B). Nenhuma `crítico`: AS-1, AS-2, AS-4, AS-5 e AS-7
estão NÃO. AS-3 é ancorada pela TASK-019 e AS-6 pelas TASK-024 a TASK-029.

### TASK-001 — Fundação do projeto e códigos de moeda ISO 4217
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-04`, `SEA-38`, `SEA-108`
- **Tipo**: infra
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: —
- **Arquivos de produção**:
  - `pyproject.toml`
  - `app/domain/currency.py`
- **Arquivos de teste**:
  - `tests/unit/domain/test_currency.py`
- **Wiring permitido**:
  - `.gitignore` (apenas `.venv/`, `__pycache__/`, `reports/`, `.env`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`)
  - `app/__init__.py` (vazio)
  - `app/core/__init__.py` (vazio)
  - `app/domain/__init__.py` (vazio)
  - `app/api/__init__.py` (vazio)
  - `app/api/routers/__init__.py` (vazio)
  - `app/api/schemas/__init__.py` (vazio)
  - `app/application/__init__.py` (vazio)
  - `app/application/services/__init__.py` (vazio)
  - `app/infrastructure/__init__.py` (vazio)
  - `app/infrastructure/db/__init__.py` (vazio)
  - `app/infrastructure/db/repositories/__init__.py` (vazio)
- **Reusa**: —
- **Contrato**: CT-2 — `normalize_currency_code(raw: str) -> str | None`, `ISO_4217_CODES: frozenset[str]` (produz)
- **Testes**: unit
- **Descrição**: Criar o `pyproject.toml` (setuptools, `requires-python = ">=3.12"`, pacote `app`) com as dependências e o extra `dev` da seção 11 do plan. Incluir `[tool.ruff]` (line-length 100, `select = ["E","F","I","UP","B","SIM"]`), `[tool.mypy]` (`strict = true`, `plugins = ["pydantic.mypy"]`, `packages = ["app"]`) e `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `addopts = "--junitxml=reports/junit.xml --import-mode=importlib"`). Criar `currency.py` com os códigos ativos da ISO 4217 (DA-10) e `normalize_currency_code` (strip + upper; `None` se vazio ou desconhecido).
- **Done when**:
  - [ ] `pip install -e ".[dev]"` conclui sem erro num venv Python 3.12
  - [ ] `ruff check . --output-format=concise` e `mypy app` saem com código 0
  - [ ] `pytest -q tests/unit/domain/test_currency.py` verde com ≥ 5 testes: "brl" → "BRL", " usd " → "USD", "XYZ" → None, "" → None, `len(ISO_4217_CODES) >= 150`
  - [ ] `reports/junit.xml` é gerado pela execução acima
- **Não fazer**:
  - Não criar `conftest.py` (o de integração é da TASK-005)
  - Não adicionar dependência fora da seção 11 do plan

---

### TASK-002 — Configuração por variáveis de ambiente e logging
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-03`, `SEA-108`, `SEA-58`, `SEA-59`
- **Tipo**: config
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-001
- **Arquivos de produção**:
  - `app/core/config.py`
  - `app/core/logging.py`
- **Arquivos de teste**:
  - `tests/unit/core/test_config.py`
  - `tests/unit/core/test_logging.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/currency.py` → `normalize_currency_code`
- **Contrato**: CT-1 — `Settings`, `load_settings_or_exit() -> Settings`, `configure_logging(level: str) -> None` (produz); CT-2 (consome)
- **Testes**: unit
- **Descrição**: `Settings(BaseSettings)` com os campos, defaults e validações de CT-1 (`env_file=".env"`, `extra="ignore"`). `default_currency` passa por `normalize_currency_code`, e código inválido gera erro de validação (SEA-108). `load_settings_or_exit()` captura `ValidationError`, loga em CRITICAL `Configuração inválida: <NOME_DA_VARIAVEL_EM_MAIUSCULAS> <motivo>` para cada erro, sem o valor, e levanta `SystemExit(1)` (SEA-03). `configure_logging` aplica o formato da seção 14 do plan e o nível recebido.
- **Done when**:
  - [ ] `pytest -q tests/unit/core/test_config.py tests/unit/core/test_logging.py` verde com ≥ 7 testes
  - [ ] Teste: sem `DATABASE_URL` → `SystemExit` com código 1 e log contendo `DATABASE_URL`
  - [ ] Teste: `DEFAULT_CURRENCY=XYZ` → `SystemExit(1)` com log contendo `DEFAULT_CURRENCY`. `DEFAULT_CURRENCY=usd` → `settings.default_currency == "USD"`
  - [ ] Teste: `MAX_UPLOAD_MB=0` e `ANOMALY_MIN_SAMPLE=1` são rejeitados; os defaults são 10, 1.5, 8, "BRL" e "INFO"
  - [ ] Teste: com `DATABASE_URL=postgresql+psycopg://u:segredo@h/db` inválido em outro campo, o log não contém "segredo"
- **Não fazer**:
  - Não criar engine nem conectar ao banco aqui
  - Não logar valores de variáveis de ambiente

---

### TASK-003 — Erros de domínio e tratamento centralizado de exceções
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-05`, `SEA-06`, `SEA-97`, `SEA-100`
- **Tipo**: infra
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-001
- **Arquivos de produção**:
  - `app/core/errors.py`
  - `app/api/errors.py`
- **Arquivos de teste**:
  - `tests/unit/api/test_errors.py`
- **Wiring permitido**: —
- **Reusa**: —
- **Contrato**: CT-3 — `AppError(code, message, http_status, details)` e subclasses; `register_exception_handlers(app: FastAPI) -> None`; `ErrorResponse` (produz)
- **Testes**: unit
- **Descrição**: Implementar a hierarquia de CT-3 com os códigos, mensagens e status da seção 8.3 do plan (as mensagens com `{limite}`, `{id}` e `{lista}` são formatadas no construtor). `register_exception_handlers` registra handlers para `AppError`, `RequestValidationError` (`VALIDATION_ERROR` com `details` `[{field, message}]`), `StarletteHTTPException`, `OperationalError`/`InterfaceError` do SQLAlchemy (503) e `Exception` (500 com `error_id = uuid4().hex` no corpo e em `logger.exception`). Corpo sempre `ErrorResponse` (DA-11), sem stack trace nem SQL.
- **Done when**:
  - [ ] `pytest -q tests/unit/api/test_errors.py` verde com ≥ 8 testes, usando uma app FastAPI mínima criada no teste com rotas que levantam cada tipo de erro
  - [ ] Teste: rota que levanta `RuntimeError("SELECT secreto")` → 500, corpo com `code="INTERNAL_ERROR"`, `error_id` de 32 hex, mensagem `"Erro interno. Identificador: <error_id>."`, e o corpo não contém "SELECT" nem "Traceback"
  - [ ] Teste: o mesmo `error_id` aparece no log capturado (`caplog`)
  - [ ] Teste: rota que levanta `sqlalchemy.exc.OperationalError` → 503 `SERVICE_UNAVAILABLE`
  - [ ] Teste: query `?d=2026-13-01` num parâmetro `date` → 422 `VALIDATION_ERROR` com `details` não vazio
  - [ ] Teste: rota inexistente → 404 com o corpo padrão (`code="NOT_FOUND"`)
- **Não fazer**:
  - Não criar `app/main.py` (TASK-012)
  - Não usar `HTTPException` para erros de domínio

---

### TASK-004 — Modelos ORM e fábrica de sessão
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-09`, `SEA-39`
- **Tipo**: infra
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-001
- **Arquivos de produção**:
  - `app/infrastructure/db/models.py`
  - `app/infrastructure/db/session.py`
- **Arquivos de teste**:
  - `tests/unit/infrastructure/test_models.py`
- **Wiring permitido**: —
- **Reusa**: —
- **Contrato**: CT-4 — `Base`, `CategoryModel`, `CategorizationRuleModel`, `ImportModel`, `ImportRejectionModel`, `TransactionModel`, `AnomalyModel`; `create_engine_from_url(url: str) -> Engine`; `create_session_factory(engine: Engine) -> sessionmaker[Session]` (produz)
- **Testes**: unit
- **Descrição**: Modelos SQLAlchemy 2 (`Mapped`/`mapped_column`) exatamente com as tabelas, colunas, tipos, CHECKs, FKs, índices e constraints da seção 7 do plan, incluindo `uq_categories_name_ci` sobre `func.lower(name)`, o índice parcial `uq_categories_default`, `uq_transactions_dedup_key` e `uq_anomalies_transaction_method`. `create_engine_from_url` usa `hide_parameters=True` e `pool_pre_ping=True` (DA-15).
- **Done when**:
  - [ ] `pytest -q tests/unit/infrastructure/test_models.py` verde com ≥ 6 testes que inspecionam `Base.metadata` (sem banco)
  - [ ] Teste: `Base.metadata.tables` tem exatamente `categories`, `categorization_rules`, `imports`, `import_rejections`, `transactions`, `anomalies`
  - [ ] Teste: `transactions.amount` é `Numeric(14, 2)`, `transactions.date` é `Date` e `transactions.dedup_key` tem constraint UNIQUE
  - [ ] Teste: `create_engine_from_url("postgresql+psycopg://u:p@localhost/x")` retorna engine com `hide_parameters` verdadeiro, sem conectar
  - [ ] `mypy app` sai com código 0
- **Não fazer**:
  - Não escrever a migration (TASK-005)
  - Não colocar regra de negócio nos modelos

---

### TASK-005 — Migration inicial Alembic e fixtures de integração
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-01`, `SEA-52`
- **Tipo**: migration
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-002, TASK-004
- **Arquivos de produção**:
  - `alembic/env.py`
  - `alembic/versions/0001_initial_schema.py`
- **Arquivos de teste**:
  - `tests/integration/conftest.py`
  - `tests/integration/test_migrations.py`
- **Wiring permitido**:
  - `alembic.ini` (apenas `script_location = alembic`, `prepend_sys_path = .` e seções de logging; sem `sqlalchemy.url`)
  - `alembic/script.py.mako` (template padrão do Alembic)
- **Reusa**:
  - `app/core/config.py` → `load_settings_or_exit`
  - `app/infrastructure/db/models.py` → `Base.metadata`
- **Contrato**: CT-5 — schema 0001 + seed "Não categorizada" (produz); CT-23 — fixtures de `tests/integration/conftest.py` (produz); CT-1, CT-4 (consome)
- **Testes**: integration
- **Descrição**: `env.py` conforme CT-5 (modos online e offline). A migration `0001` (revision `"0001"`) cria a seção 7 do plan explicitamente (`op.create_table`, sem autogenerate em runtime), insere `('Não categorizada', true)` e tem `downgrade()` completo. Criar `tests/integration/conftest.py` com **todas** as fixtures de CT-23 (DA-14). `uow_factory` e `client` fazem import tardio dentro da fixture, porque `SqlAlchemyUnitOfWork` e `create_app` só existem depois das TASK-010 e TASK-012.
- **Done when**:
  - [ ] `pytest -q tests/integration/test_migrations.py` verde com ≥ 4 testes
  - [ ] Teste: após `upgrade head`, as 6 tabelas existem e `SELECT name FROM categories WHERE is_default` retorna exatamente `["Não categorizada"]`
  - [ ] Teste: `downgrade base` remove as 6 tabelas e um novo `upgrade head` funciona
  - [ ] Teste: inserir categoria "NÃO CATEGORIZADA" viola `uq_categories_name_ci`
  - [ ] Teste: inserir duas transações com o mesmo `dedup_key` viola `uq_transactions_dedup_key`
- **Não fazer**:
  - Não usar `Base.metadata.create_all` nos testes (o schema vem só do Alembic)
  - Não criar outros `conftest.py`

---

### TASK-006 — Entidades de domínio e portas (repositórios e Unit of Work)
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-39`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-001
- **Arquivos de produção**:
  - `app/domain/entities.py`
  - `app/domain/ports.py`
- **Arquivos de teste**:
  - `tests/unit/domain/test_entities.py`
- **Wiring permitido**: —
- **Reusa**: —
- **Contrato**: CT-6 — entidades, enums e filtros de domínio (produz); CT-7 — Protocols `CategoryRepository`, `CategorizationRuleRepository`, `TransactionRepository`, `ImportRepository`, `AnomalyRepository`, `UnitOfWork` (produz)
- **Testes**: unit
- **Descrição**: Declarar exatamente os tipos de CT-6 (dataclasses `frozen=True, slots=True`, `StrEnum`) e os Protocols de CT-7 (DA-1). `TransactionType.from_amount` implementa LAC-20. Sem import de FastAPI, SQLAlchemy ou pandas.
- **Done when**:
  - [ ] `pytest -q tests/unit/domain/test_entities.py` verde com ≥ 5 testes
  - [ ] Teste: `from_amount(Decimal("-10.00")) == TransactionType.EXPENSE`, `from_amount(Decimal("5")) == TransactionType.INCOME`, `from_amount(Decimal("0"))` levanta `ValueError`
  - [ ] Teste: `ImportStatus.COMPLETED_WITH_REJECTIONS.value == "concluida_com_rejeicoes"` e `TransactionType.EXPENSE.value == "despesa"`
  - [ ] Teste: `Period()` tem `start` e `end` `None`; `Page()` tem limit 50 e offset 0
  - [ ] `grep -E "sqlalchemy|fastapi|pandas" app/domain/entities.py app/domain/ports.py` não retorna nada
- **Não fazer**:
  - Não implementar repositórios aqui
  - Não adicionar campos fora de CT-6/CT-7 sem atualizar o plan

---

### TASK-007 — Repositórios SQLAlchemy de Category e CategorizationRule
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-47`, `SEA-48`, `SEA-51`, `SEA-53`
- **Tipo**: crud-padrão
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-004, TASK-005, TASK-006
- **Arquivos de produção**:
  - `app/infrastructure/db/repositories/categories.py`
  - `app/infrastructure/db/repositories/categorization_rules.py`
- **Arquivos de teste**:
  - `tests/integration/repositories/test_category_repositories.py`
- **Wiring permitido**: —
- **Reusa**:
  - fixtures `session_factory`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-8 — `SqlAlchemyCategoryRepository(session)`, `SqlAlchemyCategorizationRuleRepository(session)` (produz); CT-4, CT-5, CT-6, CT-7, CT-23 (consome)
- **Testes**: integration
- **Descrição**: Implementar os métodos de CT-7 para Category e CategorizationRule, convertendo modelos em entidades de CT-6. `get_by_name_ci` compara `func.lower(name) == name.strip().lower()`. `list_all` de categorias ordena por `name`. A de regras ordena por `priority, created_at, id`. Nenhum método faz commit (é papel do UoW).
- **Done when**:
  - [ ] `pytest -q tests/integration/repositories/test_category_repositories.py` verde com ≥ 8 testes
  - [ ] Teste: `get_default().name == "Não categorizada"`; `get_by_name_ci("  não CATEGORIZADA ")` a encontra
  - [ ] Teste: `list_all` de regras com prioridades (2, 1, 1), criadas nessa ordem, retorna a de prioridade 1 criada primeiro, depois a outra de prioridade 1, depois a de 2
  - [ ] Teste: `update` e `delete` com id inexistente retornam `None` e `False`
- **Não fazer**:
  - Não chamar `session.commit()` nos repositórios
  - Não traduzir `IntegrityError` em erro HTTP aqui (é do serviço, TASK-020)

---

### TASK-008 — Repositório SQLAlchemy de Transaction
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-11`, `SEA-13`, `SEA-21`, `SEA-25`, `SEA-39`, `SEA-44`, `SEA-67`, `SEA-68`, `SEA-101`, `SEA-106`
- **Tipo**: crud-padrão
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-004, TASK-005, TASK-006
- **Arquivos de produção**:
  - `app/infrastructure/db/repositories/transactions.py`
- **Arquivos de teste**:
  - `tests/integration/repositories/test_transaction_repository.py`
- **Wiring permitido**: —
- **Reusa**:
  - fixtures `session_factory`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-24 — `SqlAlchemyTransactionRepository(session)` cumprindo `TransactionRepository` (produz); CT-4, CT-5, CT-6, CT-7, CT-23 (consome)
- **Testes**: integration
- **Descrição**: `insert_ignoring_duplicates` usa `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_nothing(index_elements=["dedup_key"]).returning(id)` e retorna quantas linhas entraram (DA-6). `list` aplica os filtros de `TransactionFilters` (período fechado, `category_id`, merchant por `lower()` = P-09, `import_id`), faz `COUNT` total e ordena por `date DESC, id DESC` com limit/offset. `list_expenses` retorna só `type='despesa'` com `value = abs(amount)` e o nome da categoria (join). `update_categories` faz update em lote.
- **Done when**:
  - [ ] `pytest -q tests/integration/repositories/test_transaction_repository.py` verde com ≥ 10 testes
  - [ ] Teste: inserir 3 itens, 1 com `dedup_key` já existente → retorna 2 e a tabela tem 1 linha por chave
  - [ ] Teste: filtro de período `[2026-01-10, 2026-01-20]` inclui as datas 10 e 20 e exclui 9 e 21
  - [ ] Teste: `limit=2, offset=2` sobre 5 transações retorna 2 itens e `total == 5`; filtro por `category_id` inexistente retorna `items == []`, `total == 0`
  - [ ] Teste: `list_expenses` ignora receitas e devolve `value` positivo para `amount = -45.90`
- **Não fazer**:
  - Não calcular estatística aqui (TASK-015, TASK-023)
  - Não chamar `commit()`

---

### TASK-009 — Repositórios SQLAlchemy de Import e Anomaly
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-27`, `SEA-30`, `SEA-31`, `SEA-41`, `SEA-43`, `SEA-107`
- **Tipo**: crud-padrão
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-004, TASK-005, TASK-006
- **Arquivos de produção**:
  - `app/infrastructure/db/repositories/imports.py`
  - `app/infrastructure/db/repositories/anomalies.py`
- **Arquivos de teste**:
  - `tests/integration/repositories/test_import_anomaly_repositories.py`
- **Wiring permitido**: —
- **Reusa**:
  - fixtures `session_factory`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-25 — `SqlAlchemyImportRepository(session)`, `SqlAlchemyAnomalyRepository(session)`, `ANOMALY_LOCK_KEY = 815001` (produz); CT-4, CT-5, CT-6, CT-7, CT-23 (consome)
- **Testes**: integration
- **Descrição**: `find_completed_by_hash` só considera status `concluida` e `concluida_com_rejeicoes` (SEA-43, SEA-107). `finish` grava status, contagens, `finished_at` e as rejeições, e devolve `ImportRecord`. `record_failure` cria Import com status `falhou`. `replace_all` executa `SELECT pg_advisory_xact_lock(815001)`, `DELETE FROM anomalies` e insere os candidatos (DA-7). `list(period)` faz join com a transação e a categoria e filtra pela data da transação, ordenando por data desc e id desc.
- **Done when**:
  - [ ] `pytest -q tests/integration/repositories/test_import_anomaly_repositories.py` verde com ≥ 8 testes
  - [ ] Teste: hash de Import `falhou` → `find_completed_by_hash` retorna `None`; hash de Import `concluida` → retorna o id
  - [ ] Teste: `finish` com 2 rejeições persiste 2 linhas em `import_rejections` e o `ImportRecord` traz as duas
  - [ ] Teste: `replace_all` chamado 2 vezes com os mesmos candidatos deixa exatamente 1 linha por (transaction_id, method)
  - [ ] Teste: `list(Period(start, end))` exclui anomalias de transações fora do intervalo
- **Não fazer**:
  - Não detectar anomalias aqui (TASK-017)
  - Não chamar `commit()`

---

### TASK-010 — Unit of Work SQLAlchemy e providers de injeção de dependência
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-97`
- **Tipo**: infra
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-002, TASK-005, TASK-007, TASK-008, TASK-009
- **Arquivos de produção**:
  - `app/infrastructure/db/unit_of_work.py`
  - `app/api/deps.py`
- **Arquivos de teste**:
  - `tests/integration/test_unit_of_work.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/infrastructure/db/repositories/*.py` → classes de CT-8, CT-24 e CT-25
  - fixtures `session_factory`, `uow_factory`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-9 — `SqlAlchemyUnitOfWork(session_factory)`, `get_settings`, `get_uow`, `get_uow_factory` (produz); CT-1, CT-7, CT-8, CT-23, CT-24, CT-25 (consome)
- **Testes**: integration
- **Descrição**: `SqlAlchemyUnitOfWork` abre a sessão no `__enter__`, instancia os 5 repositórios com a mesma sessão, faz rollback em `__exit__` se houver exceção ou se `commit()` não foi chamado, e sempre fecha a sessão (DA-2). `deps.py` lê `request.app.state.settings` e `request.app.state.session_factory` (CT-9, DA-3).
- **Done when**:
  - [ ] `pytest -q tests/integration/test_unit_of_work.py` verde com ≥ 4 testes
  - [ ] Teste: adicionar categoria e sair do `with` sem `commit()` → a categoria não existe num UoW novo
  - [ ] Teste: adicionar categoria, `commit()` → ela existe num UoW novo
  - [ ] Teste: exceção dentro do `with` → rollback e a exceção é propagada
- **Não fazer**:
  - Não criar providers de serviço aqui (cada router cria o seu, DA-3)
  - Não criar `app/main.py`

---

### TASK-011 — Parâmetros comuns da API (período, paginação) e schemas compartilhados
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-11`, `SEA-13`, `SEA-40`, `SEA-57`, `SEA-67`, `SEA-99`, `SEA-100`, `SEA-105`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-003, TASK-006
- **Arquivos de produção**:
  - `app/api/params.py`
  - `app/api/schemas/common.py`
- **Arquivos de teste**:
  - `tests/unit/api/test_params.py`
  - `tests/unit/api/test_common_schemas.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/core/errors.py` → `InvalidPeriodError`, `InvalidPaginationError`
  - `app/api/errors.py` → `register_exception_handlers` (na app de teste)
- **Contrato**: CT-22 — `period_params(...) -> Period`, `pagination_params(...) -> Page`, `Money`, `CategoryRef`, `TransactionOut.from_entity(t: Transaction)` (produz); CT-3, CT-6 (consome)
- **Testes**: unit
- **Descrição**: Dependências de CT-22 (P-10: limites opcionais, sem filtro = todo o histórico, SEA-57). `pagination_params` recebe `int` sem restrição no `Query` e valida no corpo para usar `INVALID_PAGINATION` com a mensagem do catálogo. `Money` serializa `Decimal` como string `"{:.2f}"` (P-13). `TransactionOut` tem os campos de 8.1, com `amount` com sinal, `type` e `currency` (SEA-40).
- **Done when**:
  - [ ] `pytest -q tests/unit/api/test_params.py tests/unit/api/test_common_schemas.py` verde com ≥ 9 testes (app FastAPI mínima montada no teste)
  - [ ] Teste: `start_date=2026-02-01&end_date=2026-01-01` → 422 `INVALID_PERIOD`; `start_date=01/02/2026` → 422 `VALIDATION_ERROR`
  - [ ] Teste: `limit=0`, `limit=501` e `offset=-1` → 422 `INVALID_PAGINATION`; `limit=500` → aceito; sem parâmetros → `Page(50, 0)`
  - [ ] Teste: `TransactionOut.from_entity(...)` serializa `amount` `Decimal("-45.9")` como `"-45.90"` e traz `category.name`
- **Não fazer**:
  - Não criar schemas específicos de um recurso (ficam nas tasks de router)

---

### TASK-012 — Factory da aplicação FastAPI
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-02`
- **Tipo**: infra
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-002, TASK-003, TASK-005, TASK-010
- **Arquivos de produção**:
  - `app/main.py`
- **Arquivos de teste**:
  - `tests/integration/api/test_app.py`
- **Wiring permitido**:
  - `tests/integration/conftest.py` (só a ordem de imports)
- **Reusa**:
  - `app/core/config.py` → `load_settings_or_exit`; `app/core/logging.py` → `configure_logging`
  - `app/api/errors.py` → `register_exception_handlers`
  - `app/infrastructure/db/session.py` → `create_engine_from_url`, `create_session_factory`
  - fixture `client` de `tests/integration/conftest.py`
- **Contrato**: CT-26 — `create_app(settings: Settings | None = None) -> FastAPI` (produz); CT-1, CT-3, CT-4, CT-9, CT-23 (consome)
- **Testes**: integration
- **Descrição**: `create_app` conforme CT-26 e DA-4: título "Smart Expense Analyzer", `version="0.1.0"`, `GET /health` → `{"status": "ok"}`, estado da app (settings, engine, session_factory), handlers de erro, e lifespan que descarta o engine. Nenhum router de negócio ainda: cada task de router adiciona o seu `include_router` aqui.
- **Done when**:
  - [ ] `pytest -q tests/integration/api/test_app.py` verde com ≥ 4 testes
  - [ ] Teste: `GET /health` → 200 `{"status": "ok"}`, sem cabeçalho de autenticação
  - [ ] Teste: `GET /openapi.json` → 200 com `info.title == "Smart Expense Analyzer"`
  - [ ] Teste: `GET /rota-inexistente` → 404 com corpo `ErrorResponse`
  - [ ] Teste: `create_app()` sem `DATABASE_URL` no ambiente levanta `SystemExit`
- **Não fazer**:
  - Não criar routers de negócio nem middleware de autenticação (LAC-01)

---

### TASK-013 — Normalização de texto e casamento de regras de categorização
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-09`, `SEA-17`, `SEA-19`, `SEA-46`, `SEA-47`, `SEA-52`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-006
- **Arquivos de produção**:
  - `app/domain/text.py`
  - `app/domain/categorization.py`
- **Arquivos de teste**:
  - `tests/unit/domain/test_text.py`
  - `tests/unit/domain/test_categorization.py`
- **Wiring permitido**: —
- **Reusa**: —
- **Contrato**: CT-10 — `normalize_whitespace(value: str) -> str`, `fold_for_match(value: str) -> str` (produz); CT-11 — `RuleMatcher(rules, default_category_id).match(description, merchant) -> int` (produz); CT-6 (consome)
- **Testes**: unit
- **Descrição**: `normalize_whitespace` faz strip e colapsa qualquer sequência de espaço em branco em um espaço. `fold_for_match` aplica NFKD, remove caracteres combinantes e faz `casefold()`. `RuleMatcher` ordena as regras por `(priority, created_at, id)` uma vez no construtor. `match` retorna a primeira cuja `fold_for_match(keyword)` está contida em `fold_for_match(description)` ou em `fold_for_match(merchant)`. Sem casamento, retorna `default_category_id` (LAC-08, LAC-10).
- **Done when**:
  - [ ] `pytest -q tests/unit/domain/test_text.py tests/unit/domain/test_categorization.py` verde com ≥ 10 testes
  - [ ] Teste: `normalize_whitespace("  PADARIA   São\tJoão ") == "PADARIA São João"`
  - [ ] Teste: a regra "acai" casa com a descrição "AÇAÍ DA PRAIA"; "uber" casa com o merchant "Uber Trip"
  - [ ] Teste: duas regras que casam, com prioridades 5 e 1 → vence a de prioridade 1; mesma prioridade → vence a de `created_at` menor
  - [ ] Teste: nenhuma regra casa → `default_category_id`; o mesmo input 2 vezes → o mesmo resultado (SEA-19)
- **Não fazer**:
  - Não acessar banco; as regras chegam por parâmetro

---

### TASK-014 — Leitura do CSV e validação por linha
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-09`, `SEA-10`, `SEA-36`, `SEA-37`, `SEA-38`, `SEA-39`, `SEA-41`, `SEA-90`, `SEA-91`, `SEA-92`, `SEA-110`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-001, TASK-003, TASK-006, TASK-013
- **Arquivos de produção**:
  - `app/infrastructure/csv_reader.py`
  - `app/domain/csv_rows.py`
- **Arquivos de teste**:
  - `tests/unit/infrastructure/test_csv_reader.py`
  - `tests/unit/domain/test_csv_rows.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/currency.py` → `normalize_currency_code`
  - `app/domain/text.py` → `normalize_whitespace`
  - `app/core/errors.py` → `EmptyFileError`, `InvalidCsvError`, `MissingColumnsError`
- **Contrato**: CT-12 — `read_csv_rows(content: bytes) -> list[RawRow]`, `parse_row(line_number, values, default_currency) -> ParsedRow | RowRejection`, `dedup_key(...) -> str`, `format_rejection(r) -> str` (produz); CT-2, CT-3, CT-6, CT-10 (consome)
- **Testes**: unit
- **Descrição**: `read_csv_rows` decodifica com `utf-8-sig` estrito e recusa byte NUL (`InvalidCsvError`), lê com pandas conforme DA-5, normaliza os nomes de coluna (P-04), valida as obrigatórias (`MissingColumnsError` com as ausentes em ordem `date, description, amount`), descarta linhas totalmente vazias e numera as linhas pela posição física (P-07). Nenhuma linha não vazia → `EmptyFileError`. `parse_row` valida data (`date.fromisoformat` com formato `AAAA-MM-DD` exato), descrição, valor (P-03, zero inválido) e moeda (CT-2, padrão `default_currency`), deriva merchant (SEA-37) e tipo (LAC-20) e junta os motivos por "; " (P-06). As mensagens de erro nunca incluem o conteúdo das células (AS-3).
- **Done when**:
  - [ ] `pytest -q tests/unit/infrastructure/test_csv_reader.py tests/unit/domain/test_csv_rows.py` verde com ≥ 18 testes
  - [ ] Teste: arquivo `b""`, só cabeçalho, e cabeçalho + 2 linhas vazias → `EmptyFileError`
  - [ ] Teste: bytes `b"\xff\xfe\x00d"` → `InvalidCsvError`; cabeçalho `date,amount` → `MissingColumnsError(["description"])`
  - [ ] Teste: cabeçalho + linha 2 válida + linha 3 vazia + linha 4 válida → 2 `RawRow` com `line_number` 2 e 4
  - [ ] Teste: `amount="-45.9"` → `ParsedRow(amount=Decimal("-45.90"), type=EXPENSE)`; `"0.00"` → rejeição "valor igual a zero"; `"1,50"` → "valor não numérico"; `"2026-02-30"` → "data inválida"; `currency="xx1"` → "moeda fora da ISO 4217"; `currency="usd"` → `"USD"`; `currency` vazia → `default_currency`
  - [ ] Teste: `merchant` vazio → merchant = descrição normalizada; `description="  a   b "` → `"a b"`
  - [ ] Teste: `format_rejection(RowRejection(12, "data inválida")) == "Linha 12: data inválida"`; `dedup_key` é determinístico e tem 64 caracteres hex
- **Não fazer**:
  - Não acessar banco nem categorizar (TASK-019)
  - Não logar valores de células

---

### TASK-015 — Estatísticas descritivas, histograma e percentuais
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-20`, `SEA-22`, `SEA-26`, `SEA-54`, `SEA-55`, `SEA-56`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-006
- **Arquivos de produção**:
  - `app/domain/statistics.py`
- **Arquivos de teste**:
  - `tests/unit/domain/test_statistics.py`
- **Wiring permitido**: —
- **Reusa**: —
- **Contrato**: CT-13 — `money`, `summarize`, `histogram`, `percentages`, `merchant_totals`, `SummaryStats`, `HistogramBucket`, `MerchantTotal` (produz); CT-6 (consome)
- **Testes**: unit
- **Descrição**: Funções puras com `Decimal` (DA-8, P-15). Mediana: com n par, a média dos dois centrais. `histogram` devolve sempre as 4 faixas de `HISTOGRAM_BOUNDS`, com a última `range_end=None`. `percentages` usa o maior resto em centésimos (DA-9). `merchant_totals` ordena por total desc e merchant asc.
- **Done when**:
  - [ ] `pytest -q tests/unit/domain/test_statistics.py` verde com ≥ 10 testes
  - [ ] Teste: `summarize([10, 20, 60])` → total 90.00, count 3, mean 30.00, median 20.00; `summarize([10, 20, 30, 40])` → median 25.00; `summarize([])` → tudo zero
  - [ ] Teste: `histogram([49.99, 50, 100, 500, 1000])` → contagens (1, 1, 1, 2)
  - [ ] Teste: `percentages([1, 1, 1])` → (33.34, 33.33, 33.33) com soma exata 100.00; 7 totais iguais também somam 100.00
  - [ ] Teste: `money(Decimal("2.345")) == Decimal("2.35")`
- **Não fazer**:
  - Não agrupar por moeda aqui (é do serviço, TASK-023)

---

### TASK-016 — Série mensal de despesas
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-32`, `SEA-33`, `SEA-34`, `SEA-54`, `SEA-62`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-006, TASK-015
- **Arquivos de produção**:
  - `app/domain/monthly_series.py`
- **Arquivos de teste**:
  - `tests/unit/domain/test_monthly_series.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/statistics.py` → `money`
- **Contrato**: CT-14 — `monthly_series(records, period) -> list[CurrencySeries]` (produz); CT-6, CT-13 (consome)
- **Testes**: unit
- **Descrição**: Agrupar por moeda e mês `AAAA-MM`, preencher todos os meses do intervalo de P-11 com total 0.00 e count 0, e incluir `by_category` (ordenado por total desc e nome asc) nos meses com despesas. Pode usar `pandas.period_range` ou aritmética de mês. Moedas em ordem alfabética.
- **Done when**:
  - [ ] `pytest -q tests/unit/domain/test_monthly_series.py` verde com ≥ 6 testes
  - [ ] Teste: despesas em 2026-01 e 2026-03, `Period(2026-01-01, 2026-03-31)` → meses `["2026-01", "2026-02", "2026-03"]` e fevereiro com total `0.00` e count 0
  - [ ] Teste: `Period()` → intervalo do mês mais antigo ao mais recente dos registros
  - [ ] Teste: registros BRL e USD → 2 séries, sem somar moedas; registros vazios → `[]`
- **Não fazer**:
  - Não consultar banco

---

### TASK-017 — Detecção de anomalias por IQR
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-28`, `SEA-29`, `SEA-54`, `SEA-58`, `SEA-59`, `SEA-96`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-006, TASK-015
- **Arquivos de produção**:
  - `app/domain/anomaly_detection.py`
- **Arquivos de teste**:
  - `tests/unit/domain/test_anomaly_detection.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/statistics.py` → `money`
- **Contrato**: CT-15 — `detect_iqr_anomalies(records, k, min_sample) -> list[AnomalyCandidate]`, `IQR_METHOD = "IQR"` (produz); CT-6, CT-13 (consome)
- **Testes**: unit
- **Descrição**: Agrupar com `pandas.DataFrame.groupby(["category_id", "currency"])`, ignorar grupos com n < `min_sample`, calcular Q1 e Q3 com `numpy.percentile(..., [25, 75], method="linear")` e marcar `value > Q3 + k·IQR` (P-16). Motivo no formato de CT-15. Os registros de entrada já são só despesas (SEA-29 é garantido pelo `list_expenses`), e o teste confirma que a função não depende do sinal.
- **Done when**:
  - [ ] `pytest -q tests/unit/domain/test_anomaly_detection.py` verde com ≥ 7 testes
  - [ ] Teste SEA-28: 20 despesas entre 40.00 e 60.00 e uma de 5000.00 na mesma categoria e moeda → exatamente 1 candidato, o de 5000.00, com `method == "IQR"` e reason contendo "5000.00"
  - [ ] Teste SEA-59: grupo com 7 despesas (uma discrepante) e `min_sample=8` → `[]`
  - [ ] Teste: mesmo conjunto em BRL e USD é avaliado separadamente; `k=3.0` marca menos que `k=1.5` num conjunto moderado
  - [ ] Teste: 2 chamadas com a mesma entrada → listas iguais (SEA-30)
- **Não fazer**:
  - Não implementar Z-Score (fora de LAC-12)
  - Não persistir nada

---

### TASK-018 — Serviço de anomalias (recálculo e listagem)
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-27`, `SEA-29`, `SEA-30`, `SEA-31`, `SEA-57`, `SEA-60`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-010, TASK-017
- **Arquivos de produção**:
  - `app/application/services/anomaly_service.py`
- **Arquivos de teste**:
  - `tests/integration/application/test_anomaly_service.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/anomaly_detection.py` → `detect_iqr_anomalies`
  - fixtures `uow_factory`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-16 — `AnomalyService(uow, k, min_sample).recompute_all() -> int`, `.list(period) -> list[Anomaly]` (produz); CT-6, CT-7, CT-9, CT-15, CT-23 (consome)
- **Testes**: integration
- **Descrição**: `recompute_all` lê todas as despesas (`ExpenseFilters()`), chama a detecção e `uow.anomalies.replace_all`, loga `anomalies_recomputed` e **não** faz commit (quem comita é o caller). `list` repassa o período ao repositório.
- **Done when**:
  - [ ] `pytest -q tests/integration/application/test_anomaly_service.py` verde com ≥ 5 testes
  - [ ] Teste: com os dados de SEA-28 persistidos, `recompute_all()` + `commit()` → 1 anomalia; rodar de novo → continua 1 (SEA-30)
  - [ ] Teste: receitas de valor alto não geram anomalia (SEA-29)
  - [ ] Teste: `list(Period(...))` fora da data da anomalia → `[]`; `list(Period())` → todas (SEA-57)
- **Não fazer**:
  - Não chamar `uow.commit()` dentro de `recompute_all`

---

### TASK-019 — Serviço de importação de CSV
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-07`, `SEA-08`, `SEA-14`, `SEA-17`, `SEA-41`, `SEA-42`, `SEA-43`, `SEA-44`, `SEA-45`, `SEA-60`, `SEA-97`, `SEA-98`, `SEA-102`, `SEA-103`, `SEA-104`, `SEA-106`, `SEA-107`
- **Tipo**: lógica-negócio
- **Risco**: alto
- **Âncora de risco**: AS-3 (dados financeiros pessoais — `app/application/services/import_service.py`)
- **Perfil**: backend
- **Depende de**: TASK-003, TASK-010, TASK-013, TASK-014, TASK-018
- **Arquivos de produção**:
  - `app/application/services/import_service.py`
- **Arquivos de teste**:
  - `tests/integration/application/test_import_service.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/infrastructure/csv_reader.py` → `read_csv_rows`; `app/domain/csv_rows.py` → `parse_row`, `dedup_key`
  - `app/domain/categorization.py` → `RuleMatcher`
  - `app/application/services/anomaly_service.py` → `AnomalyService.recompute_all`
  - fixtures `uow_factory`, `settings`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-17 — `ImportService(uow_factory, settings).import_csv(filename: str, content: bytes) -> ImportRecord` (produz); CT-1, CT-3, CT-9, CT-11, CT-12, CT-16, CT-23 (consome)
- **Testes**: integration
- **Descrição**: Implementar o fluxo da seção 5.2 do plan: limite de tamanho (`FileTooLargeError`), SHA-256, `read_csv_rows` antes de abrir o UoW, `DuplicateFileError` por hash, `create_processing`, `parse_row`, dedup dentro do arquivo (a primeira vence, SEA-103), `RuleMatcher`, `insert_ignoring_duplicates`, contagens (`duplicate_count` = duplicatas no arquivo + (válidas únicas − inseridas)), status terminal, `finish`, `recompute_all` e `commit`. Falhas seguem DA-16 (Import `falhou` em UoW novo, `SQLAlchemyError` → `ServiceUnavailableError`). Logs da seção 14 do plan com duração em ms, **sem** descrição, merchant nem valor.
- **Done when**:
  - [ ] `pytest -q tests/integration/application/test_import_service.py` verde com ≥ 14 testes
  - [ ] Teste: CSV com 10 linhas válidas e 1 vazia → status `concluida`, `rows_read=10`, `imported_count=10`, 10 transações vinculadas ao Import (SEA-07, SEA-10)
  - [ ] Teste: 2 válidas + 1 com data inválida → `concluida_com_rejeicoes`, `rejected_count=1`, rejeição com a linha certa; todas inválidas → `imported_count=0` e status `concluida_com_rejeicoes` (SEA-102)
  - [ ] Teste: reenviar o mesmo conteúdo → `DuplicateFileError` e nenhuma transação ou Import novo (SEA-43); após um Import `falhou` com o mesmo hash → aceito (SEA-107)
  - [ ] Teste: arquivo novo com uma linha já persistida e uma linha repetida dentro do próprio arquivo → `duplicate_count=2` (SEA-44, SEA-103)
  - [ ] Teste: `content` maior que `max_upload_mb` → `FileTooLargeError` sem Import criado (SEA-104)
  - [ ] Teste: regra "UBER" → Transporte; a linha "UBER TRIP" fica em Transporte e "PADARIA" em "Não categorizada" (SEA-17)
  - [ ] Teste: `insert_ignoring_duplicates` substituído para levantar `OperationalError` → `ServiceUnavailableError`, 0 transações persistidas, 1 Import com status `falhou` (SEA-97)
  - [ ] Teste: 2 threads importando arquivos diferentes ao mesmo tempo → contagens corretas e independentes (SEA-98); 2 threads com o mesmo conteúdo → cada chave de deduplicação existe 1 vez (SEA-106)
  - [ ] Teste: após o import, as anomalias do conjunto de SEA-28 estão persistidas (SEA-60)
  - [ ] Teste: `caplog` contém `import_started` e `import_finished` com `import_id` e `duration_ms`, e nenhum registro contém a descrição do CSV de teste (SEA-14, AS-3)
- **Não fazer**:
  - Não ler o `UploadFile` aqui (é do router, TASK-024)
  - Não processar em background (LAC-06)

---

### TASK-020 — Serviços de Category e CategorizationRule
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-15`, `SEA-16`, `SEA-18`, `SEA-48`, `SEA-49`, `SEA-50`, `SEA-51`, `SEA-53`, `SEA-64`
- **Tipo**: crud-padrão
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-003, TASK-010, TASK-013
- **Arquivos de produção**:
  - `app/application/services/category_service.py`
  - `app/application/services/categorization_rule_service.py`
- **Arquivos de teste**:
  - `tests/integration/application/test_category_service.py`
  - `tests/integration/application/test_categorization_rule_service.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/text.py` → `normalize_whitespace`
  - fixtures `uow`, `uow_factory`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-18 — `CategoryService`, `CategorizationRuleService` (produz); CT-3, CT-7, CT-9, CT-10, CT-23 (consome)
- **Testes**: integration
- **Descrição**: `CategoryService.create` normaliza o nome, recusa vazio (`CategoryNameRequiredError`), checa `get_by_name_ci` (`CategoryAlreadyExistsError`), traduz `IntegrityError` de corrida para o mesmo erro e faz commit. `CategorizationRuleService` normaliza a keyword, valida a categoria (`RuleCategoryNotFoundError`), usa `RuleNotFoundError` para id inexistente, faz commit nas escritas e nunca toca transações (SEA-64).
- **Done when**:
  - [ ] `pytest -q tests/integration/application/test_category_service.py tests/integration/application/test_categorization_rule_service.py` verde com ≥ 12 testes
  - [ ] Teste: `create("  ")` e `create(None)` → `CategoryNameRequiredError`; `create("não categorizada")` → `CategoryAlreadyExistsError`; `create("Transporte")` 2 vezes → a segunda levanta `CategoryAlreadyExistsError`
  - [ ] Teste: `list()` inclui "Não categorizada"
  - [ ] Teste: regra com `category_id=999999` → `RuleCategoryNotFoundError`; `get`/`update`/`delete` de id inexistente → `RuleNotFoundError`
  - [ ] Teste: criar, atualizar e excluir regra não altera o `category_id` de transações já persistidas (SEA-64)
- **Não fazer**:
  - Não implementar edição ou exclusão de Category (fora de escopo, LAC-09)
  - Não disparar recategorização automática (LAC-11)

---

### TASK-021 — Serviço de consulta de transações
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-11`, `SEA-12`, `SEA-93`
- **Tipo**: crud-padrão
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-003, TASK-010, TASK-013
- **Arquivos de produção**:
  - `app/application/services/transaction_service.py`
- **Arquivos de teste**:
  - `tests/integration/application/test_transaction_service.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/text.py` → `normalize_whitespace`
  - fixtures `uow`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-19 — `TransactionService(uow).get(id) -> Transaction`, `.list(filters, page) -> PageResult[Transaction]` (produz); CT-3, CT-7, CT-9, CT-10, CT-23 (consome)
- **Testes**: integration
- **Descrição**: Serviço fino sobre `uow.transactions`. `get` levanta `TransactionNotFoundError`. `list` normaliza `filters.merchant` com `normalize_whitespace` (P-09) antes de consultar.
- **Done when**:
  - [ ] `pytest -q tests/integration/application/test_transaction_service.py` verde com ≥ 4 testes
  - [ ] Teste: `get(999999)` → `TransactionNotFoundError`; `get(id_existente)` traz `category_name`
  - [ ] Teste: `list(TransactionFilters(merchant="  uber   trip "), Page())` encontra o merchant "UBER TRIP"
- **Não fazer**:
  - Não implementar recategorização (TASK-022)

---

### TASK-022 — Serviço de recategorização
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-63`, `SEA-65`, `SEA-66`, `SEA-109`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-002, TASK-010, TASK-013, TASK-018
- **Arquivos de produção**:
  - `app/application/services/recategorization_service.py`
- **Arquivos de teste**:
  - `tests/integration/application/test_recategorization_service.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/categorization.py` → `RuleMatcher`
  - `app/application/services/anomaly_service.py` → `AnomalyService.recompute_all`
  - fixtures `uow_factory`, `settings`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-20 — `RecategorizationService(uow, settings).recategorize() -> RecategorizationResult` (produz); CT-1, CT-7, CT-9, CT-11, CT-16, CT-23 (consome)
- **Testes**: integration
- **Descrição**: Carregar as regras e a categoria padrão, avaliar cada transação de `list_all_for_categorization` com `RuleMatcher`, chamar `update_categories` só com as que mudaram, rodar `AnomalyService.recompute_all()`, fazer commit e logar `recategorization_finished`.
- **Done when**:
  - [ ] `pytest -q tests/integration/application/test_recategorization_service.py` verde com ≥ 4 testes
  - [ ] Teste: "UBER TRIP" em "Não categorizada", criar a regra "UBER"→Transporte, `recategorize()` → `evaluated=1, changed=1` e a transação fica em Transporte
  - [ ] Teste: segunda chamada seguida → `changed=0` (SEA-66); sem transações → `(0, 0)` (SEA-109)
  - [ ] Teste: mover despesas de categoria altera o conjunto de anomalias persistido (SEA-65)
- **Não fazer**:
  - Não recategorizar automaticamente no CRUD de regras

---

### TASK-023 — Serviço de analytics (resumo, categorias, série mensal)
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-20`, `SEA-21`, `SEA-22`, `SEA-23`, `SEA-24`, `SEA-25`, `SEA-54`, `SEA-55`, `SEA-56`, `SEA-57`, `SEA-61`, `SEA-62`, `SEA-95`, `SEA-101`
- **Tipo**: lógica-negócio
- **Risco**: médio
- **Perfil**: backend
- **Depende de**: TASK-010, TASK-015, TASK-016
- **Arquivos de produção**:
  - `app/application/services/analytics_service.py`
- **Arquivos de teste**:
  - `tests/integration/application/test_analytics_service.py`
- **Wiring permitido**: —
- **Reusa**:
  - `app/domain/statistics.py` → `summarize`, `histogram`, `percentages`, `merchant_totals`
  - `app/domain/monthly_series.py` → `monthly_series`
  - fixtures `uow`, `clean_db` de `tests/integration/conftest.py`
- **Contrato**: CT-21 — `AnalyticsService(uow).summary(filters)`, `.categories(period)`, `.monthly(period)` (produz); CT-6, CT-7, CT-9, CT-13, CT-14, CT-23 (consome)
- **Testes**: integration
- **Descrição**: Buscar `list_expenses` com os filtros e agrupar por moeda em ordem alfabética (SEA-54). `summary` monta estatísticas, `by_merchant` e histograma por moeda. `categories` agrupa por categoria dentro da moeda e calcula os percentuais pelo total da moeda. `monthly` delega a `monthly_series`. Escopo sem despesas → lista vazia (SEA-95).
- **Done when**:
  - [ ] `pytest -q tests/integration/application/test_analytics_service.py` verde com ≥ 8 testes
  - [ ] Teste: despesas 10.00, 20.00 e 60.00 + uma receita de 1000.00 → `summary` BRL com total 90.00, mean 30.00, median 20.00, count 3 (SEA-25, SEA-26)
  - [ ] Teste: despesas BRL e USD → 2 grupos, nenhum somando moedas
  - [ ] Teste: `categories` → percentuais de cada moeda somam 100.00
  - [ ] Teste: filtro `category_id` inexistente → `[]` (SEA-101); sem dados → `[]` (SEA-95)
- **Não fazer**:
  - Não calcular estatística em SQL (DA-8)

---

### TASK-024 — Endpoint POST /imports
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-07`, `SEA-08`, `SEA-35`, `SEA-42`, `SEA-43`, `SEA-45`, `SEA-90`, `SEA-91`, `SEA-92`, `SEA-104`
- **Tipo**: crud-padrão
- **Risco**: alto
- **Âncora de risco**: AS-6 (endpoint aberto sem autenticação — `app/api/routers/imports.py`)
- **Perfil**: backend
- **Depende de**: TASK-011, TASK-012, TASK-014, TASK-019
- **Arquivos de produção**:
  - `app/api/routers/imports.py`
  - `app/api/schemas/imports.py`
- **Arquivos de teste**:
  - `tests/integration/api/test_imports_api.py`
- **Wiring permitido**:
  - `app/main.py` (apenas importar o router e `app.include_router`)
- **Reusa**:
  - `app/api/deps.py` → `get_uow_factory`, `get_settings`
  - `app/domain/csv_rows.py` → `format_rejection`
  - fixture `client` de `tests/integration/conftest.py`
- **Contrato**: CT-22, CT-26, CT-17, CT-12 — (consome)
- **Testes**: integration
- **Descrição**: `POST /imports` com `file: UploadFile` lê `await file.read(max_bytes + 1)` e chama `ImportService.import_csv(file.filename or "arquivo.csv", content)`. Responde 201 com `ImportOut` (8.1), sendo `rejections[].reason` = `format_rejection(...)`. O provider `get_import_service` fica no próprio router (DA-3). Declarar em `responses=` os códigos 409, 413, 422 e 503 com `ErrorResponse` para o OpenAPI. Sem nenhuma dependência de autenticação.
- **Done when**:
  - [ ] `pytest -q tests/integration/api/test_imports_api.py` verde com ≥ 8 testes
  - [ ] Teste: CSV válido com 3 linhas → 201, `status="concluida"`, `imported_count=3`, `rejections=[]`, sem cabeçalho de autenticação (SEA-35)
  - [ ] Teste: mesmo arquivo de novo → 409 `DUPLICATE_FILE` com a mensagem contendo o id
  - [ ] Teste: arquivo vazio → 422 `EMPTY_FILE`; binário → 422 `INVALID_CSV`; sem `amount` → 422 `MISSING_COLUMNS` com `details == ["amount"]`
  - [ ] Teste: com `settings.max_upload_mb=1`, arquivo de 1 MiB + 1 byte → 413 `FILE_TOO_LARGE`
  - [ ] Teste: linha com data inválida → 201 `concluida_com_rejeicoes` com `rejections[0].reason` começando por `"Linha "`
- **Não fazer**:
  - Não colocar regra de importação no router
  - Não adicionar autenticação (LAC-01)

---

### TASK-025 — Endpoints de transações e recategorização

- **Requisito**: `SEA-11`, `SEA-12`, `SEA-13`, `SEA-35`, `SEA-40`, `SEA-63`, `SEA-67`, `SEA-68`, `SEA-93`, `SEA-94`
- **Tipo**: crud-padrão
- **Risco**: alto
- **Âncora de risco**: AS-6 (endpoint aberto sem autenticação — `app/api/routers/transactions.py`)
- **Perfil**: backend
- **Depende de**: TASK-011, TASK-012, TASK-021, TASK-022
- **Arquivos de produção**:
  - `app/api/routers/transactions.py`
  - `app/api/schemas/transactions.py`
- **Arquivos de teste**:
  - `tests/integration/api/test_transactions_api.py`
- **Wiring permitido**:
  - `app/main.py` (apenas importar o router e `app.include_router`)
- **Reusa**:
  - `app/api/params.py` → `period_params`, `pagination_params`
  - `app/api/schemas/common.py` → `TransactionOut`
  - `app/api/deps.py` → `get_uow`, `get_settings`
  - fixture `client` de `tests/integration/conftest.py`
- **Contrato**: CT-22, CT-26, CT-19, CT-20 — (consome)
- **Testes**: integration
- **Descrição**: `GET /transactions` (filtros `category_id`, `merchant`, `import_id`, período e paginação) → `TransactionPage {items, total, limit, offset}`. `GET /transactions/{transaction_id}` (path `int`) → `TransactionOut`. `POST /transactions/recategorize` → `RecategorizeOut {evaluated, changed}`. Declarar a rota `POST /transactions/recategorize` antes de `/{transaction_id}`. Providers no próprio router.
- **Done when**:
  - [ ] `pytest -q tests/integration/api/test_transactions_api.py` verde com ≥ 9 testes
  - [ ] Teste: após importar 3 linhas, `GET /transactions` → 200, `total=3`, cada item com `type`, `currency`, `category.name` e `import_id` (SEA-11, SEA-40)
  - [ ] Teste: `GET /transactions/999999` → 404 `TRANSACTION_NOT_FOUND`; `GET /transactions/abc` → 422 `VALIDATION_ERROR`
  - [ ] Teste: `limit=501` → 422 `INVALID_PAGINATION`; filtros combinados `start_date` + `merchant` retornam só as que atendem a ambos (SEA-68)
  - [ ] Teste: `POST /transactions/recategorize` → 200 `{"evaluated": n, "changed": m}`, sem cabeçalho de autenticação
- **Não fazer**:
  - Não criar endpoint de alteração manual de categoria (fora de escopo)

---

### TASK-026 — Endpoints de categorias
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-15`, `SEA-16`, `SEA-35`, `SEA-51`, `SEA-53`
- **Tipo**: crud-padrão
- **Risco**: alto
- **Âncora de risco**: AS-6 (endpoint aberto sem autenticação — `app/api/routers/categories.py`)
- **Perfil**: backend
- **Depende de**: TASK-011, TASK-012, TASK-020
- **Arquivos de produção**:
  - `app/api/routers/categories.py`
  - `app/api/schemas/categories.py`
- **Arquivos de teste**:
  - `tests/integration/api/test_categories_api.py`
- **Wiring permitido**:
  - `app/main.py` (apenas importar o router e `app.include_router`)
- **Reusa**:
  - `app/api/schemas/common.py` → `CategoryRef`
  - `app/api/deps.py` → `get_uow`
  - fixture `client` de `tests/integration/conftest.py`
- **Contrato**: CT-22, CT-26, CT-18 — (consome)
- **Testes**: integration
- **Descrição**: `POST /categories` com body `CategoryIn {name: str | None = None}` → 201 `CategoryRef`. A validação de nome vazio fica no serviço, para gerar `CATEGORY_NAME_REQUIRED`. `GET /categories` → lista de `CategoryRef`.
- **Done when**:
  - [ ] `pytest -q tests/integration/api/test_categories_api.py` verde com ≥ 5 testes
  - [ ] Teste: `POST {"name": "Transporte"}` → 201 com `id` e `name`
  - [ ] Teste: `POST {"name": "   "}` e `POST {}` → 422 `CATEGORY_NAME_REQUIRED`
  - [ ] Teste: `POST {"name": "NÃO CATEGORIZADA"}` → 409 `CATEGORY_ALREADY_EXISTS`
  - [ ] Teste: `GET /categories` inclui "Não categorizada", sem cabeçalho de autenticação
- **Não fazer**:
  - Não criar PUT/DELETE de categoria (LAC-09)

---

### TASK-027 — Endpoints CRUD de regras de categorização
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-18`, `SEA-35`, `SEA-48`, `SEA-49`, `SEA-50`
- **Tipo**: crud-padrão
- **Risco**: alto
- **Âncora de risco**: AS-6 (endpoint aberto sem autenticação — `app/api/routers/categorization_rules.py`)
- **Perfil**: backend
- **Depende de**: TASK-011, TASK-012, TASK-020
- **Arquivos de produção**:
  - `app/api/routers/categorization_rules.py`
  - `app/api/schemas/categorization_rules.py`
- **Arquivos de teste**:
  - `tests/integration/api/test_categorization_rules_api.py`
- **Wiring permitido**:
  - `app/main.py` (apenas importar o router e `app.include_router`)
  - `app/infrastructure/db/repositories/categorization_rules.py` (só update e delete atômicos)
  - `tests/integration/api/test_categorization_rules_api.py` (inclui os testes de concorrência de update e delete)
- **Reusa**:
  - `app/api/deps.py` → `get_uow`
  - fixture `client` de `tests/integration/conftest.py`
- **Contrato**: CT-22, CT-26, CT-18 — (consome)
- **Testes**: integration
- **Descrição**: Router com prefixo `/categorization-rules`: POST (201), GET lista, GET `/{rule_id}`, PUT `/{rule_id}` e DELETE `/{rule_id}` (204). `RuleIn` usa `keyword: str` com validador que recusa vazio ou só espaços, `category_id: int` e `priority: StrictInt`. `RuleOut` conforme 8.1.
- **Done when**:
  - [ ] `pytest -q tests/integration/api/test_categorization_rules_api.py` verde com ≥ 8 testes
  - [ ] Teste: ciclo completo POST 201 → GET 200 → PUT 200 (priority alterada) → DELETE 204 → GET 404 `RULE_NOT_FOUND`
  - [ ] Teste: `keyword="  "` → 422 `VALIDATION_ERROR`; `priority=1.5` → 422; `priority` ausente → 422; `priority="1"` → 422
  - [ ] Teste: `category_id` inexistente → 422 `RULE_CATEGORY_NOT_FOUND`
  - [ ] Teste: PUT e DELETE de id inexistente → 404 `RULE_NOT_FOUND`
- **Não fazer**:
  - Não recategorizar transações ao alterar regras (SEA-64)

---

### TASK-028 — Endpoints de analytics

- **Requisito**: `SEA-20`, `SEA-21`, `SEA-22`, `SEA-23`, `SEA-24`, `SEA-35`, `SEA-54`, `SEA-55`, `SEA-56`, `SEA-57`, `SEA-61`, `SEA-95`
- **Tipo**: crud-padrão
- **Risco**: alto
- **Âncora de risco**: AS-6 (endpoint aberto sem autenticação — `app/api/routers/analytics.py`)
- **Perfil**: backend
- **Depende de**: TASK-011, TASK-012, TASK-023
- **Arquivos de produção**:
  - `app/api/routers/analytics.py`
  - `app/api/schemas/analytics.py`
- **Arquivos de teste**:
  - `tests/integration/api/test_analytics_api.py`
- **Wiring permitido**:
  - `app/main.py` (apenas importar o router e `app.include_router`)
- **Reusa**:
  - `app/api/params.py` → `period_params`
  - `app/api/schemas/common.py` → `Money`
  - `app/api/deps.py` → `get_uow`
  - fixture `client` de `tests/integration/conftest.py`
- **Contrato**: CT-22, CT-26, CT-21 — (consome)
- **Testes**: integration
- **Descrição**: `GET /analytics/summary` (período, `category_id`, `merchant`), `GET /analytics/categories` (período) e `GET /analytics/monthly` (período), com os schemas de 8.1. Todos os valores monetários e percentuais usam `Money`.
- **Done when**:
  - [ ] `pytest -q tests/integration/api/test_analytics_api.py` verde com ≥ 7 testes
  - [ ] Teste: após importar despesas -10.00, -20.00 e -60.00 → `summary.currencies[0]` com `total="90.00"`, `mean="30.00"`, `median="20.00"` e 4 faixas no `histogram`
  - [ ] Teste: `categories` → soma dos `percentage` de BRL == `"100.00"`
  - [ ] Teste: `monthly?start_date=2026-01-01&end_date=2026-03-31` com despesas só em jan e mar → 3 meses, fevereiro com `total="0.00"`
  - [ ] Teste: banco sem despesas → `summary` e `categories` retornam `{"currencies": []}` (SEA-95); período invertido → 422 `INVALID_PERIOD`
- **Não fazer**:
  - Não calcular nada no router

---

### TASK-029 — Endpoint GET /anomalies
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-27`, `SEA-31`, `SEA-35`, `SEA-96`
- **Tipo**: crud-padrão
- **Risco**: alto
- **Âncora de risco**: AS-6 (endpoint aberto sem autenticação — `app/api/routers/anomalies.py`)
- **Perfil**: backend
- **Depende de**: TASK-011, TASK-012, TASK-018
- **Arquivos de produção**:
  - `app/api/routers/anomalies.py`
  - `app/api/schemas/anomalies.py`
- **Arquivos de teste**:
  - `tests/integration/api/test_anomalies_api.py`
- **Wiring permitido**:
  - `app/main.py` (apenas importar o router e `app.include_router`)
- **Reusa**:
  - `app/api/params.py` → `period_params`
  - `app/api/schemas/common.py` → `TransactionOut`, `Money`
  - `app/api/deps.py` → `get_uow`, `get_settings`
  - fixture `client` de `tests/integration/conftest.py`
- **Contrato**: CT-22, CT-26, CT-16 — (consome)
- **Testes**: integration
- **Descrição**: `GET /anomalies` com filtro de período → `{"items": [AnomalyOut]}`, sendo `AnomalyOut {id, method, value, reason, transaction: TransactionOut}` (8.1).
- **Done when**:
  - [ ] `pytest -q tests/integration/api/test_anomalies_api.py` verde com ≥ 4 testes
  - [ ] Teste: importar o conjunto de SEA-28 → `items` com 1 elemento, `method="IQR"`, `transaction.amount="-5000.00"` e `reason` não vazio
  - [ ] Teste: banco vazio → 200 `{"items": []}` (SEA-96)
  - [ ] Teste: período que exclui a data da anomalia → `items == []` (SEA-31)
- **Não fazer**:
  - Não recalcular anomalias no GET (LAC-13)

---

### TASK-030 — Dockerfile e Docker Compose
- **Status**: ✅ APROVADA em 2026-09-26

- **Requisito**: `SEA-01`
- **Tipo**: infra
- **Risco**: médio
- **Perfil**: infra
- **Depende de**: TASK-005, TASK-012
- **Arquivos de produção**:
  - `Dockerfile`
  - `docker-compose.yml`
- **Arquivos de teste**:
  - `tests/unit/infra/test_docker_files.py`
- **Wiring permitido**:
  - `.env.example` (apenas as variáveis da seção 11 do plan, com valores de desenvolvimento, sem segredo real)
  - `.dockerignore` (apenas `.venv`, `.git`, `reports`, `__pycache__`, `.env`, `.specs`)
- **Reusa**: —
- **Contrato**: CT-5, CT-26 — (consome)
- **Testes**: unit
- **Gate**: `docker compose build api` (executar em `.`)
- **Descrição**: `Dockerfile` em `python:3.12-slim`: instala o pacote (sem extras de dev), copia `app/`, `alembic/` e `alembic.ini`, e usa o `CMD` de DA-13. `docker-compose.yml` com o serviço `db` (`postgres:16-alpine`, env `POSTGRES_*`, healthcheck `pg_isready`, volume `pgdata`, sem `ports`) e o serviço `api` (`build: .`, `env_file: .env`, `depends_on: db: condition: service_healthy`, `ports: ["127.0.0.1:8000:8000"]`, DA-12). `.env.example` com `DATABASE_URL=postgresql+psycopg://sea:sea_dev_password@db:5432/sea`.
- **Done when**:
  - [ ] `pytest -q tests/unit/infra/test_docker_files.py` verde com ≥ 4 testes (checagem textual: `127.0.0.1:8000:8000`, `service_healthy`, `alembic upgrade head` no Dockerfile, serviço `db` sem `ports`)
  - [ ] `docker compose build api` sai com código 0
  - [ ] `cp .env.example .env && docker compose up -d --build` seguido de `curl -fsS http://localhost:8000/health` retorna `{"status":"ok"}` e `curl -fsS http://localhost:8000/openapi.json` retorna 200
  - [ ] Com `DATABASE_URL` removida do `.env`, o contêiner `api` termina com código diferente de 0 e `docker compose logs api` contém `DATABASE_URL`
- **Não fazer**:
  - Não publicar a porta do PostgreSQL
  - Não versionar `.env`

---

### TASK-031 — Pipeline de CI no GitHub Actions e README

- **Requisito**: `SEA-01`, `SEA-04`
- **Tipo**: infra
- **Risco**: baixo
- **Perfil**: infra
- **Depende de**: TASK-030
- **Arquivos de produção**:
  - `.github/workflows/ci.yml`
  - `README.md`
- **Arquivos de teste**:
  - `tests/unit/infra/test_ci_workflow.py`
- **Wiring permitido**: —
- **Reusa**: —
- **Contrato**: —
- **Testes**: unit
- **Descrição**: Workflow disparado em `push` e `pull_request`. Job `test` (`ubuntu-latest`): serviço `postgres:16-alpine` (user/senha/db `sea`/`sea`/`sea_test`, porta 5432, health-cmd `pg_isready`), `actions/setup-python` 3.12, `pip install -e ".[dev]"`, `ruff check . --output-format=concise`, `mypy app` e `pytest -q` com `TEST_DATABASE_URL=postgresql+psycopg://sea:sea@localhost:5432/sea_test`. Upload de `reports/junit.xml` como artefato (`if: always()`). Job `docker`: `cp .env.example .env && docker compose build api`. O README traz o propósito, o aviso de mono-usuário sem autenticação e de que a API não deve ser exposta (LAC-01), a subida (`cp .env.example .env`, `docker compose up -d --build`, `http://localhost:8000/docs`), as variáveis de ambiente, o layout do CSV (LAC-02) e como rodar os testes localmente.
- **Done when**:
  - [ ] `pytest -q tests/unit/infra/test_ci_workflow.py` verde com ≥ 4 testes (checagem textual: gatilhos `push` e `pull_request`, `postgres:16-alpine`, `pytest -q`, `TEST_DATABASE_URL`)
  - [ ] `grep -c "docker compose up -d --build" README.md` ≥ 1 e `grep -ci "sem autenticação" README.md` ≥ 1
- **Não fazer**:
  - Não adicionar etapa de deploy (fora de escopo)

---

### TASK-032 — CSV de exemplo e teste de aceitação ponta a ponta

- **Requisito**: `SEA-02`, `SEA-35`
- **Tipo**: teste
- **Risco**: baixo
- **Perfil**: backend
- **Depende de**: TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029
- **Arquivos de produção**:
  - `samples/transacoes_exemplo.csv`
- **Arquivos de teste**:
  - `tests/integration/api/test_acceptance_sample_csv.py`
- **Wiring permitido**: —
- **Reusa**:
  - fixture `client` de `tests/integration/conftest.py`
- **Contrato**: CT-26 — (consome)
- **Testes**: integration
- **Descrição**: Criar um CSV de exemplo (UTF-8, cabeçalho `date,description,amount,merchant,currency`) com ≥ 30 linhas: despesas BRL em 3 categorias e 3 meses, 2 receitas, 1 linha vazia, 1 linha inválida, e um grupo "Alimentação" com ≥ 10 despesas entre 40.00 e 60.00 mais 1 de 5000.00 (anomalia plantada). O teste cria as categorias e as regras, importa o arquivo e confere contra valores calculados à mão, escritos como constantes no teste.
- **Done when**:
  - [ ] `pytest -q tests/integration/api/test_acceptance_sample_csv.py` verde com ≥ 5 testes
  - [ ] Teste: `/openapi.json` contém exatamente os caminhos `/imports`, `/transactions`, `/transactions/{transaction_id}`, `/transactions/recategorize`, `/categories`, `/categorization-rules`, `/categorization-rules/{rule_id}`, `/analytics/summary`, `/analytics/categories`, `/analytics/monthly`, `/anomalies` e `/health` (SEA-02)
  - [ ] Teste: todos esses endpoints, chamados sem cabeçalho `Authorization`, respondem com status diferente de 401 e de 403 (SEA-35)
  - [ ] Teste: importar o CSV → `rejected_count=1`, e `GET /transactions?limit=500` retorna todas as linhas válidas
  - [ ] Teste: `summary` e `categories` batem com as constantes calculadas à mão; `GET /anomalies` retorna só a despesa de 5000.00
- **Não fazer**:
  - Não alterar código de produção de outras tasks para fazer o teste passar

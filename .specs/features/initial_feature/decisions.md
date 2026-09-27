# Decisões — initial_feature (Smart Expense Analyzer)

Etapa: gate de clarificação do spec (spec-writer, 1ª passada) · Data: 2026-09-26

## Decisões do humano

### LAC-01 — A API exige autenticação e separa dados por usuário?
- **Data**: 2026-09-26
- **Opções apresentadas**: A) mono-usuário sem auth B) mono-usuário com chave de API por variável de ambiente C) multiusuário com JWT e isolamento
- **Recomendação do spec-writer**: B
- **Escolha**: A — mono-usuário, sem autenticação
- **Observações do humano**: escolha diverge da recomendação. A API não exige credenciais e não existe entidade User.

### LAC-02 — Layout do CSV
- **Data**: 2026-09-26
- **Opções apresentadas**: A) fixo date/description/amount/merchant opcional, data ISO, decimal ponto, separador vírgula, UTF-8 B) fixo brasileiro (dd/mm/aaaa, decimal vírgula, ";") C) A e B com detecção automática D) mapeamento a cada importação
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: junto com LAC-16/LAC-16b, entra também a coluna opcional `currency`.

### LAC-03 — Receitas/créditos e sinal do valor
- **Data**: 2026-09-26
- **Opções apresentadas**: A) importar só despesas e descartar créditos B) importar tudo com tipo; estatísticas só sobre despesas C) valor negativo é linha inválida
- **Recomendação do spec-writer**: B
- **Escolha**: B
- **Observações do humano**: —

### LAC-04 — Linhas inválidas no CSV
- **Data**: 2026-09-26
- **Opções apresentadas**: A) rejeitar o arquivo inteiro B) importar as válidas e registrar as inválidas por linha C) importar só se as inválidas ficarem abaixo de um percentual
- **Recomendação do spec-writer**: B
- **Escolha**: B
- **Observações do humano**: —

### LAC-05 — Duplicidade e reimportação
- **Data**: 2026-09-26
- **Opções apresentadas**: A) rejeitar arquivo idêntico (hash, 409) B) ignorar transações com chave data+valor+descrição já existente C) A e B D) sem deduplicação
- **Recomendação do spec-writer**: C
- **Escolha**: C
- **Observações do humano**: por LAC-16b, a moeda também entra na chave de deduplicação.

### LAC-06 — POST /imports síncrono ou assíncrono?
- **Data**: 2026-09-26
- **Opções apresentadas**: A) síncrono, 201 com contagens B) assíncrono, 202 com consulta de status
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-07 — Tamanho máximo do CSV
- **Data**: 2026-09-26
- **Opções apresentadas**: A) 10 MB configurável, 413 acima disso B) 50 MB configurável C) sem limite
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-08 — Casamento de CategorizationRule e conflitos
- **Data**: 2026-09-26
- **Opções apresentadas**: A) palavra-chave contida, sem distinguir caixa e acento, prioridade numérica B) regex com prioridade C) palavra-chave mais faixa de valor
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-09 — Escopo do CRUD além dos endpoints mínimos
- **Data**: 2026-09-26
- **Opções apresentadas**: A) mínimos + CRUD de regras + listagem de categorias B) A + editar/excluir categoria + mudar Category de transação + excluir Import C) só mínimos, regras por seed
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-10 — Category de transação sem regra correspondente
- **Data**: 2026-09-26
- **Opções apresentadas**: A) Category padrão "Não categorizada" B) nula
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-11 — Recategorização do histórico quando as regras mudam
- **Data**: 2026-09-26
- **Opções apresentadas**: A) não, a P3 sai do escopo B) sim, sob demanda C) sim, automaticamente
- **Recomendação do spec-writer**: B
- **Escolha**: B
- **Observações do humano**: —

### LAC-12 — Método, parâmetros e amostra mínima de anomalias
- **Data**: 2026-09-26
- **Opções apresentadas**: A) IQR por Category, Q3+1,5×IQR, mínimo 8 B) Z-Score por Category, |z|>3, mínimo 8 C) ambos, escolhidos por parâmetro
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: por LAC-16, o grupo estatístico é (Category, moeda).

### LAC-13 — Quando as anomalias são calculadas e persistidas
- **Data**: 2026-09-26
- **Opções apresentadas**: A) ao fim de cada importação, sobre todo o histórico, persistidas B) sob demanda, sem persistência C) ao fim da importação, só as novas
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-14 — O que é "distribuição de gastos"
- **Data**: 2026-09-26
- **Opções apresentadas**: A) percentual por categoria B) histograma por faixas de valor C) ambos
- **Recomendação do spec-writer**: C
- **Escolha**: C
- **Observações do humano**: —

### LAC-15 — Exposição dos dados mensais
- **Data**: 2026-09-26
- **Opções apresentadas**: A) endpoint dedicado de série mensal B) agrupamento por mês no /analytics/summary
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-16 — Há mais de uma moeda?
- **Data**: 2026-09-26
- **Opções apresentadas**: A) BRL única, sem campo de moeda B) coluna de moeda, agregações separadas por moeda
- **Recomendação do spec-writer**: A
- **Escolha**: B — Transaction tem moeda; agregações, estatísticas e anomalias são separadas por moeda, nunca somam moedas diferentes
- **Observações do humano**: escolha diverge da recomendação. Detalhada em LAC-16b.

### LAC-16b — Como a moeda entra no CSV (derivada de LAC-02 A + LAC-16 B, criada pelo orquestrador)
- **Data**: 2026-09-26
- **Opções apresentadas**: A) coluna `currency` opcional (ISO 4217); se ausente, usa `DEFAULT_CURRENCY` (env, padrão BRL) B) coluna obrigatória C) moeda informada por importação
- **Recomendação do orquestrador**: A
- **Escolha**: A
- **Observações do humano**: a moeda entra na chave de deduplicação (LAC-05) e no agrupamento de analytics e anomalias. Código fora de ISO 4217 torna a linha inválida (LAC-04).

### LAC-17 — Paginação e filtros de GET /transactions
- **Data**: 2026-09-26
- **Opções apresentadas**: A) limit/offset, padrão 50, máximo 500, filtros por período/categoria/estabelecimento/Import B) cursor C) sem paginação
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-18 — Período padrão de analytics e anomalias sem filtro
- **Data**: 2026-09-26
- **Opções apresentadas**: A) todo o histórico B) mês corrente C) últimos 12 meses
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-19 — Unicidade do nome de Category
- **Data**: 2026-09-26
- **Opções apresentadas**: A) único sem distinguir caixa, 409 na duplicata B) pode repetir
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-20 — Sinal de `amount`, zero e valor nas estatísticas (etapa: spec-writer, 2ª passada)
- **Data**: 2026-09-26
- **Opções apresentadas**: A) negativo = despesa, zero = linha inválida, estatísticas usam o módulo B) positivo = despesa (convenção de fatura), zero = linha inválida C) convenção configurável por variável de ambiente, padrão A
- **Recomendação do spec-writer**: A
- **Escolha**: A
- **Observações do humano**: —

### LAC-21 — Risco da TASK-014 (csv_reader + csv_rows) (etapa: plan-architect)
- **Data**: 2026-09-26
- **Opções apresentadas**: A) alto, com âncora AS-3 (onda só dela, QA semântico rigoroso) B) médio (onda 4 em paralelo, gate mecânico + 18 ou mais testes unitários)
- **Recomendação do plan-architect**: A (Jev a_regra_central p=0.47, em dúvida)
- **Escolha**: B — médio
- **Observações do humano**: escolha diverge da recomendação. A task continua coberta pelo gate mecânico e pelos testes unitários do Done when.

## Premissas assumidas (lacunas não bloqueantes)

### P-01 — Desdobramento por estabelecimento
- **Premissa**: o resumo por estabelecimento fica dentro de GET /analytics/summary (SEA-22), que é o único endpoint de analytics coerente com esse resumo.
- **Reversibilidade**: alta
- **Onde impacta**: spec.md SEA-22; contrato de /analytics/summary

### P-02 — Interpretações do spec-writer ao aplicar as decisões (para conferência humana)
- **Premissa**: (1) SEA-62: LAC-18 ("todo o histórico") vale também para GET /analytics/monthly; (2) SEA-65: a recategorização recalcula as anomalias; (3) SEA-56: faixas do histograma [0,50), [50,100), [100,500), [500,∞); (4) SEA-38: código de moeda gravado em maiúsculas; (5) SEA-43: o 409 por hash vale só contra Imports concluídos, e o reenvio depois de "Falhou" é aceito; (6) SEA-103: linha repetida no mesmo arquivo conta como duplicada.
- **Reversibilidade**: alta (cada item muda um critério isolado)
- **Onde impacta**: spec.md SEA-38, SEA-43, SEA-56, SEA-62, SEA-65, SEA-103

### ENV-01 — Ambiente de verificação do run.py (etapa: /implement, aceite da TASK-001)
- **Data**: 2026-09-26
- **Contexto**: o aceite da TASK-001 falhou com `ModuleNotFoundError: No module named 'app'`. O run.py chamava o pytest global (uv tool, Python 3.14, sem as dependências do projeto), e o `pytest.ini` da raiz tem precedência sobre `[tool.pytest.ini_options]` do pyproject.
- **Opções apresentadas**: A) `.venv` Python 3.12 compartilhado na raiz, só com as dependências, run.py rodando com ele no PATH, e `pytest.ini` com `pythonpath = .`, `testpaths = tests` e `--import-mode=importlib` B) remover o `pytest.ini` C) pausar
- **Recomendação do orquestrador**: A
- **Escolha**: A
- **Observações**: o `pytest.ini` passa a ser a fonte da config do pytest, e o `[tool.pytest.ini_options]` do pyproject (TASK-001) fica ignorado. Requer atualização de plan (seção de comandos/ambiente): a verificação roda com `.venv/bin` no PATH.

### LAC-22 — `amount` fora do limite de NUMERIC(14,2) (etapa: /implement, TASK-014, hm-engineer)
- **Data**: 2026-09-26
- **Opções apresentadas**: A) rejeitar a linha em `parse_row` com o motivo existente "valor não numérico" quando |amount| >= 10^12 B) criar o motivo novo "valor fora do limite" (muda o catálogo 8.3) C) não validar na TASK-014 (a importação falharia com 500, contrariando SEA-41)
- **Recomendação do hm-engineer**: A (Jev e4_contract p=0.85: é lacuna)
- **Escolha**: A
- **Observações**: o catálogo e os contratos não mudam. Nota para o plan (P-03): documentar que |amount| >= 10^12 vira "valor não numérico". Decisão incerta registrada pelo implementador, sem consulta ao humano: ".5" e "1." são rejeitados como "valor não numérico" (Jev e3_implied p=0.52, aplicado o lado estrito).

### ENV-01 (adendo) — Testcontainers com colima
- **Data**: 2026-09-26
- **Observação**: os testes de integração exigem `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock` nesta máquina (Docker via colima). O run.py roda com essa variável, além de `.venv/bin` no PATH e `PYTHONPATH=.`.

### FUP-01 — ANOMALY_IQR_K não finito aceito pela config (etapa: /implement, QA da onda 5)
- **Data**: 2026-09-26
- **Contexto**: `Field(default=1.5, gt=0)` em app/core/config.py (CT-1, TASK-002) aceita "inf" e "1e309". `detect_iqr_anomalies` (TASK-017) levanta ValueError nesses casos, e o recompute_all (TASK-018) derruba o import. Só pode ser causado por configuração do operador.
- **Opções apresentadas**: A) registrar como follow-up, sem mudar o escopo B) corrigir nesta feature com uma task nova
- **Recomendação do orquestrador**: A
- **Escolha**: A
- **Observações**: correção sugerida: `Field(gt=0, allow_inf_nan=False)` e um teste. Requer atualização de plan (CT-1) numa próxima iteração.

### SCOPE-01 — Ordem de imports no conftest quebra o lint quando app/main.py passa a existir (etapa: /implement, aceite da TASK-012)
- **Data**: 2026-09-26
- **Contexto**: `ruff check` aponta I001 em `tests/integration/conftest.py:113` (import tardio de `app.main` na fixture `client`, TASK-005). Com `app/main.py` presente, o ruff trata `app.main` como first-party e pede que ele venha depois de `fastapi.testclient`. O arquivo está fora do escopo da TASK-012 (Wiring: —).
- **Opções apresentadas**: A) o humano amplia o Wiring da TASK-012 em tasks.md para incluir `tests/integration/conftest.py` (só ordem de imports) e roda o check_plan B) bloquear a TASK-012 C) reprovar e tentar dentro do escopo
- **Recomendação do orquestrador**: A
- **Escolha**: A
- **Observações**: requer atualização de tasks.md (feita pelo humano, com check_plan). Depois disso, o implementador da TASK-012 é retomado para aplicar a correção de uma linha.

### FUP-02 — Anomalias desatualizadas quando duas importações rodam em paralelo (etapa: /implement, QA RIGOROSO da onda 7)
- **Data**: 2026-09-26
- **Contexto**: `AnomalyService.recompute_all` (TASK-018) lê as despesas antes do `pg_advisory_xact_lock`, que só é obtido em `replace_all` (TASK-009, DA-7). Com duas importações paralelas em READ COMMITTED, quem grava por último substitui o conjunto a partir de uma leitura que não inclui as linhas do outro. O QA reproduziu em 5 de 5 execuções, o que contraria o SEA-60 ("todo o histórico"). O próximo recálculo (import ou recategorização) corrige o conjunto.
- **Opções apresentadas**: A) registrar como follow-up B) corrigir nesta feature ampliando o escopo
- **Recomendação do orquestrador**: A
- **Escolha**: A
- **Observações**: correção sugerida: obter o advisory lock (815001) antes de `list_expenses` no recompute_all. Requer atualização de plan (DA-7) numa próxima iteração.

### FUP-03 — Corpo de upload sem limite antes do parse multipart (AS-6) (etapa: /implement, QA RIGOROSO da onda 8)
- **Data**: 2026-09-26
- **Contexto**: o POST /imports lê no máximo MAX_UPLOAD_MB + 1 byte, mas o Starlette grava o multipart inteiro num SpooledTemporaryFile antes do endpoint. O QA mediu 18,8 MB em disco temporário com 30 MB enviados. Pela LAC-01/DA-12, a gravidade é BAIXA. O SEA-104 é cumprido como está escrito. Há também um risco de CSRF de rede local: uma página maliciosa pode fazer POST para localhost, o que vale para todo o AS-6.
- **Opções apresentadas**: A) registrar como follow-up B) corrigir nesta feature com uma task nova ou ampliada
- **Recomendação do orquestrador**: A
- **Escolha**: A
- **Observações**: correção sugerida: middleware ASGI que responde 413 FILE_TOO_LARGE pelo Content-Length ou pela contagem do stream, acima de MAX_UPLOAD_MB + a folga do multipart, com teste por socket. Registrar o risco de CSRF de rede local no README (TASK-031). Requer atualização de plan (DA-12/DA-13) numa próxima iteração.

### SCOPE-02 — Corrida entre PUT e DELETE de regra devolve 500 (etapa: /implement, QA RIGOROSO da onda 10, TASK-027)
- **Data**: 2026-09-26
- **Contexto**: em PUT e DELETE simultâneos na mesma regra, a API devolve 500 (StaleDataError) em 41 de 100 corridas. O contrato 8.3 manda 404 RULE_NOT_FOUND. Em DELETE contra DELETE, os dois respondem 204. A causa é o update/delete não atômico em `app/infrastructure/db/repositories/categorization_rules.py` (TASK-007), arquivo fora do escopo da TASK-027.
- **Opções apresentadas**: A) o humano amplia o Wiring da TASK-027 para incluir o repositório e o teste de concorrência B) registrar como follow-up e aceitar o risco C) bloquear a TASK-027
- **Recomendação do orquestrador**: A
- **Escolha**: A
- **Observações**: requer atualização de tasks.md (Wiring da TASK-027), feita pelo humano com check_plan. O contrato do repositório (CT-7/CT-8) não muda: update devolve entidade ou None, delete devolve bool.

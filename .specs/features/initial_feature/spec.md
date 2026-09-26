# Especificação — Smart Expense Analyzer (feature inicial)

## 1. Problema

Quem registra despesas pessoais normalmente só tem o extrato bancário ou da
fatura do cartão em CSV. Esse arquivo é uma lista crua: não separa gastos por
categoria, não mostra quanto se gasta por mês ou por estabelecimento e não
destaca gastos fora do padrão. Hoje a análise é manual, feita em planilha, e
por isso é lenta, sujeita a erro e raramente repetida.

O Smart Expense Analyzer é um backend que recebe esses arquivos, valida e
normaliza os dados, categoriza as despesas por regras configuráveis, persiste
tudo e expõe via API REST resumos, estatísticas (total, média, mediana,
distribuição), séries mensais para gráficos e uma lista de transações
potencialmente anormais, detectadas por métodos estatísticos simples.

O projeto também é uma vitrine de engenharia: tem de ser reproduzível com
Docker, coberto por testes automatizados executados em CI e organizado em
camadas com responsabilidades separadas. Esta é a primeira feature do
projeto (greenfield). Não existe código nem feature anterior.

## 2. Objetivos

- [ ] Um usuário sobe todo o ambiente (API + PostgreSQL) com um único comando do Docker Compose e o esquema do banco fica aplicado sem passo manual.
- [ ] Um usuário importa um CSV de transações e recebe o resultado da importação com as contagens de linhas processadas.
- [ ] Um usuário consulta pela API as transações importadas, já normalizadas e categorizadas.
- [ ] Um usuário obtém total, média, mediana e distribuição de gastos por categoria, período e estabelecimento.
- [ ] Um usuário obtém a lista de transações potencialmente anormais, com o motivo estatístico de cada uma.
- [ ] Um usuário obtém os dados agregados por mês, prontos para alimentar gráficos.
- [ ] Todo push ou pull request executa no GitHub Actions os testes unitários e de integração. O pipeline falha se algum teste falhar.
- [ ] O código segue os requisitos de engenharia pedidos: type hints, validação com Pydantic, tratamento centralizado de exceções, logging, configuração por variáveis de ambiente, Clean Architecture, SOLID, Repository Pattern, injeção de dependência e migrações Alembic. A forma de aplicar cada um é decisão do `plan.md`.

## 3. Fora de Escopo

| Item | Motivo da exclusão |
|---|---|
| Interface gráfica (frontend, dashboard, renderização de gráficos) | A descrição pede backend. A API entrega os dados e quem consome desenha os gráficos. |
| Formatos de importação além de CSV (OFX, XLSX, PDF, QIF) | A descrição cita só CSV. |
| Integração direta com bancos ou Open Finance | Não foi pedida. A entrada é sempre um arquivo enviado pelo usuário. |
| Categorização ou detecção de anomalias com machine learning | A descrição pede regras configuráveis e métodos estatísticos simples (Z-Score/IQR). |
| Notificações e alertas (e-mail, push, webhook) de anomalias | A descrição pede apenas a lista de possíveis anomalias via API. |
| Orçamentos, metas de gasto e previsões | Não citados na descrição. |
| Conversão cambial entre moedas | Decisão LAC-16 (B): multimoeda sem conversão. Cada moeda é agregada separadamente (`SEA-54`). |
| Exportação de relatórios em arquivo (PDF, Excel, CSV de saída) | A descrição pede "dados para relatórios/gráficos" em JSON. |
| Deploy em nuvem ou em ambiente de produção | O critério de conclusão é o ambiente local com Docker e o CI. |
| Testes de carga e metas de desempenho sob estresse | Não há meta de desempenho na descrição (ver seção 10). |
| Marcar ou desmarcar manualmente uma transação como anomalia, ou registrar feedback sobre ela | Não citado. A lista de anomalias é somente leitura. |
| Hierarquia de categorias (subcategorias) | Não citada. Category é uma lista plana. |
| Autenticação, autorização e múltiplos usuários | Decisão LAC-01 (A): API mono-usuário de acesso aberto, sem entidade User. O risco está registrado na seção 10. |
| Edição e exclusão de Category, alteração manual da Category de uma transação, exclusão de Import | Decisão LAC-09 (A): o CRUD completo cobre só CategorizationRule; de Category, apenas criação e listagem. |

## 4. Glossário de Domínio

Projeto greenfield: não existe código, e os termos vêm da descrição da
feature. Os nomes das entidades seguem exatamente os da descrição
(`Transaction`, `Category`, `Import`, `CategorizationRule`, `Anomaly`) e
devem ser mantidos no código.

| Termo | Significado | Onde aparece no código |
|---|---|---|
| Transaction / Transação (novo) | Um lançamento financeiro lido de uma linha válida do CSV, com data, descrição, estabelecimento, valor, moeda, tipo, Category atribuída e o Import de origem. | Não existe (greenfield). Entidade citada na descrição. |
| Despesa (novo) | Transaction que representa saída de dinheiro. Estatísticas, resumos e anomalias consideram apenas despesas. Receitas são importadas e listadas, mas não entram em cálculos (decisão LAC-03, `SEA-39`). | Não existe (greenfield). |
| Category / Categoria (novo) | Classificação de uma despesa (ex.: "Alimentação", "Transporte"). | Não existe (greenfield). Entidade citada na descrição. |
| CategorizationRule / Regra de categorização (novo) | Regra configurável que associa transações a uma Category. Casa por palavra-chave contida, com prioridade numérica (decisão LAC-08, `SEA-46` e `SEA-47`). | Não existe (greenfield). Entidade citada na descrição. |
| Import / Importação (novo) | Registro de um envio de arquivo CSV: nome do arquivo, momento, status e contagens do processamento. | Não existe (greenfield). Entidade citada na descrição. |
| Anomaly / Anomalia (novo) | Registro de que uma despesa foi considerada potencialmente anormal por um método estatístico, com o método, o valor de referência e o motivo. | Não existe (greenfield). Entidade citada na descrição. |
| Estabelecimento (novo) | Nome do comerciante ou recebedor da despesa, usado para agrupar gastos. Vem da coluna `merchant` do CSV ou, se ela estiver ausente ou vazia, da descrição normalizada (`SEA-37`). | Não existe (greenfield). |
| Tipo (novo) | Classificação de uma Transaction como `despesa` ou `receita`, derivada do sinal de `amount` (decisões LAC-03 e LAC-20: negativo = despesa, positivo = receita). | Não existe (greenfield). |
| Moeda (novo) | Código ISO 4217 da Transaction, vindo da coluna opcional `currency` ou, na ausência dela, da variável de ambiente `DEFAULT_CURRENCY` (padrão BRL). Decisões LAC-16 e LAC-16b. | Não existe (greenfield). |
| Não categorizada (novo) | Category padrão, existente desde a migração inicial, atribuída a transações que nenhuma regra casa (decisão LAC-10). | Não existe (greenfield). |
| Chave de deduplicação (novo) | Combinação (data, valor, descrição normalizada, moeda) que identifica uma transação já existente (decisões LAC-05 e LAC-16b). | Não existe (greenfield). |
| Recategorização (novo) | Ação explícita que reaplica as regras atuais a todas as transações persistidas (decisão LAC-11). | Não existe (greenfield). |
| Período (novo) | Intervalo fechado de datas `[data inicial, data final]` usado como filtro em consultas e analytics. | Não existe (greenfield). |
| Z-Score (novo) | Distância de um valor à média em desvios-padrão: `(valor − média) / desvio-padrão`. | Não existe (greenfield). |
| IQR (novo) | Intervalo interquartil `Q3 − Q1`. É anomalia o valor acima de `Q3 + k·IQR`. | Não existe (greenfield). |
| Série mensal (novo) | Agregação das despesas por mês-calendário (AAAA-MM), para gráficos. | Não existe (greenfield). |

## 5. Atores e Permissões

| Ator | Ação | Condição / restrição |
|---|---|---|
| Usuário da API | Importar CSV, consultar transações, criar e listar categorias, manter regras (CRUD), recategorizar, consultar analytics, série mensal e anomalias | Acesso aberto, sem credenciais e sem separação de dados por usuário (decisão LAC-01, `SEA-35`). Qualquer cliente com acesso de rede à API tem todas as permissões. O risco está na seção 10. |
| Desenvolvedor / avaliador | Subir o ambiente com Docker Compose e executar os testes localmente | Precisa de Docker instalado. As variáveis de ambiente vêm de um arquivo de exemplo versionado, sem segredos reais. |
| Pipeline de CI (GitHub Actions) | Executar lint (se o plano definir), testes unitários e de integração a cada push ou pull request | Nenhuma credencial de produção. O banco de teste é efêmero. |

Não existe controle de permissão prévio (greenfield). Pela decisão LAC-01 (A),
a matriz é de acesso aberto, mono-usuário: não há papel nem ação restrita na
API.

## 6. Histórias de Usuário

### P1: Ambiente reproduzível e pipeline de CI ⭐ MVP

**História**: Como desenvolvedor ou avaliador, quero subir todo o ambiente com um comando e ver os testes rodando no CI para confirmar que o projeto funciona sem configuração manual.

**Por que P1**: O critério de conclusão exige subir tudo com Docker e ter os testes executados pelo pipeline de CI. Sem isso nenhuma outra história pode ser demonstrada.

**Critérios de aceite**:

| ID | Critério |
|---|---|
| `SEA-01` | WHEN o desenvolvedor executa o comando de subida do Docker Compose documentado no README, a partir de um clone limpo e de um arquivo de variáveis criado a partir do exemplo versionado, THEN o sistema SHALL disponibilizar a API e o PostgreSQL, com todas as migrações Alembic aplicadas, sem nenhum passo manual adicional. |
| `SEA-02` | WHEN a API está no ar THEN o sistema SHALL expor a documentação OpenAPI gerada pelo FastAPI com todos os endpoints desta especificação. |
| `SEA-03` | WHEN falta ou é inválida uma variável de ambiente obrigatória na inicialização (ex.: conexão com o banco) THEN o sistema SHALL encerrar a inicialização com mensagem de log que nomeia a variável, sem iniciar a API em estado parcial. |
| `SEA-04` | WHEN ocorre push ou pull request no repositório THEN o pipeline do GitHub Actions SHALL executar os testes unitários e os de integração, estes contra um PostgreSQL real, e SHALL terminar com falha se qualquer teste falhar. |
| `SEA-05` | WHEN qualquer requisição da API gera um erro (validação, recurso inexistente, conflito ou erro inesperado) THEN o sistema SHALL responder com um corpo JSON de erro de formato único (código do erro e mensagem legível), sem expor stack trace, SQL ou detalhes internos. |
| `SEA-06` | WHEN ocorre um erro inesperado (não tratado pelo domínio) THEN o sistema SHALL responder HTTP 500 com o corpo padrão de `SEA-05` e SHALL registrar em log o erro completo com um identificador que também volta na resposta. |
| `SEA-35` | WHEN qualquer endpoint desta especificação recebe uma requisição sem credencial ou cabeçalho de autenticação THEN o sistema SHALL processá-la normalmente, sem responder HTTP 401 nem 403 (acesso aberto, mono-usuário; decisão LAC-01). |

**Teste independente**: Em uma máquina com Docker, clonar, copiar o arquivo de variáveis de exemplo, executar o comando documentado e abrir a documentação OpenAPI. No GitHub, abrir um pull request com um teste propositalmente quebrado e ver o pipeline falhar.

### P1: Importar CSV e consultar transações ⭐ MVP

**História**: Como usuário da API, quero enviar o CSV do meu extrato e consultar as transações resultantes, já limpas e normalizadas, para trabalhar com meus gastos sem planilha.

**Por que P1**: É o fluxo central do critério de conclusão ("importar um CSV, consultar as transações pela API") e a fonte de dados de todas as outras histórias.

**Critérios de aceite**:

| ID | Critério |
|---|---|
| `SEA-07` | WHEN o usuário envia um arquivo CSV válido em `POST /imports` THEN o sistema SHALL criar um registro Import e persistir no PostgreSQL uma Transaction por linha válida, vinculada a esse Import. |
| `SEA-08` | WHEN uma importação termina THEN a resposta de `POST /imports` SHALL conter o identificador do Import, o status e as contagens de linhas lidas e de transações importadas. As contagens adicionais estão em `SEA-42`. |
| `SEA-09` | WHEN uma linha é importada THEN o sistema SHALL normalizar descrição e estabelecimento, removendo espaços nas extremidades e colapsando espaços internos repetidos, e SHALL gravar a data como data-calendário e o valor como decimal exato com 2 casas, sem erro de ponto flutuante. |
| `SEA-10` | WHEN o CSV contém linhas totalmente vazias THEN o sistema SHALL ignorá-las, sem contá-las como transações nem como linhas inválidas. |
| `SEA-11` | WHEN o usuário chama `GET /transactions` THEN o sistema SHALL retornar as transações persistidas, cada uma com id, data, descrição, estabelecimento, valor, Category ("Não categorizada" quando nenhuma regra casou, `SEA-52`) e id do Import de origem. Paginação e filtros: `SEA-67` e `SEA-68`. |
| `SEA-12` | WHEN o usuário chama `GET /transactions/{id}` com um id existente THEN o sistema SHALL retornar essa transação com os mesmos campos de `SEA-11`. |
| `SEA-13` | WHEN o usuário chama `GET /transactions` com um filtro de período THEN o sistema SHALL retornar apenas as transações com data dentro do intervalo fechado `[data inicial, data final]`. |
| `SEA-14` | WHEN uma importação é processada THEN o sistema SHALL registrar em log o início e o fim, com id do Import, nome do arquivo, contagens e duração. |
| `SEA-36` | WHEN o usuário envia um CSV em UTF-8, com separador vírgula e cabeçalho contendo as colunas obrigatórias `date`, `description` e `amount` (e, opcionalmente, `merchant` e `currency`) THEN o sistema SHALL aceitá-lo, interpretando `date` no formato AAAA-MM-DD e `amount` com ponto como separador decimal (decisão LAC-02). |
| `SEA-37` | WHEN a coluna `merchant` não existe no arquivo ou está vazia na linha THEN o sistema SHALL usar como estabelecimento a descrição normalizada da linha (decisão LAC-02). |
| `SEA-38` | WHEN a coluna `currency` não existe no arquivo ou está vazia na linha THEN o sistema SHALL atribuir à transação a moeda da variável de ambiente `DEFAULT_CURRENCY` (padrão BRL). WHEN `currency` traz um código ISO 4217 válido THEN o sistema SHALL gravá-lo em letras maiúsculas (decisões LAC-16 e LAC-16b). |
| `SEA-39` | WHEN uma linha válida é importada THEN o sistema SHALL persistir a transação com tipo `despesa` ou `receita`, derivado do sinal de `amount`: negativo = `despesa`, positivo = `receita`. Receitas são persistidas e listadas, mas excluídas de estatísticas, séries e anomalias. Nos cálculos (totais, médias, medianas, percentuais, faixas do histograma, séries mensais e IQR), o valor de cada despesa é o módulo de `amount`, ou seja, um número positivo (decisões LAC-03 e LAC-20). |
| `SEA-40` | WHEN o usuário chama `GET /transactions` ou `GET /transactions/{id}` THEN cada transação retornada SHALL incluir também o tipo e a moeda, além dos campos de `SEA-11`. |
| `SEA-41` | WHEN o CSV tem linhas inválidas (`date` ausente, fora do formato AAAA-MM-DD ou data inexistente; `amount` ausente ou não numérico; `description` vazia; `currency` preenchida com código fora da ISO 4217) THEN o sistema SHALL importar as linhas válidas, registrar no Import cada linha inválida com seu número no arquivo e o motivo, e SHALL concluir o Import com status "Concluída com rejeições" (decisões LAC-04 e LAC-16b). |
| `SEA-42` | WHEN `POST /imports` responde THEN o corpo SHALL conter, além dos campos de `SEA-08`, as contagens de linhas rejeitadas e de transações duplicadas e a lista de rejeições (número da linha e motivo). |
| `SEA-43` | WHEN o conteúdo do arquivo enviado é idêntico, byte a byte, ao de um Import anterior com status "Concluída" ou "Concluída com rejeições" THEN o sistema SHALL responder HTTP 409, sem criar Import nem Transaction (decisão LAC-05). |
| `SEA-44` | WHEN uma linha válida tem chave de deduplicação (data, valor, descrição normalizada, moeda) igual à de uma Transaction já persistida THEN o sistema SHALL NOT criar nova Transaction para ela e SHALL contá-la como duplicada no resultado do Import (decisões LAC-05 e LAC-16b). |
| `SEA-45` | WHEN o usuário envia um CSV em `POST /imports` THEN o sistema SHALL processar o arquivo inteiro dentro da requisição e responder HTTP 201 com o Import já em estado terminal e com as contagens finais (processamento síncrono; decisão LAC-06). |
| `SEA-67` | WHEN o usuário chama `GET /transactions` THEN o sistema SHALL paginar por `limit`/`offset`, com `limit` padrão 50 e máximo 500, e SHALL informar na resposta o total de itens que atendem aos filtros (decisão LAC-17). |
| `SEA-68` | WHEN o usuário chama `GET /transactions` com filtros de período, Category, estabelecimento e/ou Import THEN o sistema SHALL retornar apenas as transações que atendem a todos os filtros informados (decisão LAC-17). |

Decisões aplicadas nesta história: LAC-02, LAC-03, LAC-04, LAC-05, LAC-06,
LAC-07, LAC-16, LAC-16b e LAC-20.

**Teste independente**: Com o ambiente no ar, enviar um CSV de exemplo com 10 linhas válidas e 1 linha vazia em `POST /imports`. Conferir a resposta (10 importadas) e depois `GET /transactions` (10 itens normalizados) e `GET /transactions/{id}` de um deles.

### P1: Categorização automática por regras configuráveis ⭐ MVP

**História**: Como usuário da API, quero criar categorias e regras para que as despesas importadas já cheguem categorizadas, sem trabalho manual linha a linha.

**Por que P1**: A categorização é requisito principal da descrição e dá base para `GET /analytics/categories`, que faz parte do critério de conclusão ("visualizar estatísticas de gastos").

**Critérios de aceite**:

| ID | Critério |
|---|---|
| `SEA-15` | WHEN o usuário envia em `POST /categories` um nome não vazio THEN o sistema SHALL criar a Category e responder HTTP 201 com seu id e nome. |
| `SEA-16` | WHEN o usuário envia em `POST /categories` um nome vazio, composto só de espaços ou ausente THEN o sistema SHALL responder HTTP 422 sem criar a Category. |
| `SEA-17` | WHEN uma transação é importada e pelo menos uma CategorizationRule casa com ela THEN o sistema SHALL atribuir à transação a Category da regra vencedora, pelos critérios de casamento e prioridade de `SEA-46` e `SEA-47`. |
| `SEA-18` | WHEN o usuário tenta criar uma CategorizationRule que aponta para uma Category inexistente THEN o sistema SHALL responder HTTP 422 sem criar a regra. |
| `SEA-19` | WHEN o mesmo CSV é importado duas vezes com o mesmo conjunto de regras (desconsiderando deduplicação) THEN o sistema SHALL atribuir as mesmas categorias às mesmas linhas, ou seja, a categorização é determinística. |
| `SEA-46` | WHEN a palavra-chave de uma CategorizationRule está contida na descrição ou no estabelecimento de uma transação, sem distinguir maiúsculas de minúsculas nem letras acentuadas de não acentuadas THEN o sistema SHALL considerar que a regra casa com a transação (decisão LAC-08). |
| `SEA-47` | WHEN mais de uma CategorizationRule casa com a mesma transação THEN o sistema SHALL aplicar a de menor número de prioridade e, no empate, a criada primeiro (decisão LAC-08). |
| `SEA-48` | WHEN o usuário usa o recurso `/categorization-rules` THEN o sistema SHALL permitir criar (HTTP 201), listar, consultar por id, atualizar e excluir (HTTP 204) regras, cada uma com palavra-chave, Category e prioridade inteira (decisão LAC-09). |
| `SEA-49` | WHEN o usuário consulta, atualiza ou exclui uma CategorizationRule com id inexistente THEN o sistema SHALL responder HTTP 404 com o corpo de erro padrão. |
| `SEA-50` | WHEN o usuário cria ou atualiza uma CategorizationRule com palavra-chave vazia ou só de espaços, ou com prioridade ausente ou não inteira THEN o sistema SHALL responder HTTP 422 sem gravar a alteração. |
| `SEA-51` | WHEN o usuário chama `GET /categories` THEN o sistema SHALL listar todas as Category, incluindo "Não categorizada", com id e nome (decisão LAC-09). |
| `SEA-52` | WHEN nenhuma CategorizationRule casa com uma transação importada THEN o sistema SHALL atribuir a ela a Category "Não categorizada", que já existe desde a migração inicial do banco (decisão LAC-10). |
| `SEA-53` | WHEN o usuário envia em `POST /categories` um nome igual ao de uma Category existente, desconsiderando maiúsculas/minúsculas e espaços nas extremidades (inclusive "Não categorizada") THEN o sistema SHALL responder HTTP 409 sem criar a Category (decisão LAC-19). |

Decisões aplicadas nesta história: LAC-08, LAC-09, LAC-10 e LAC-19.

**Teste independente**: Criar a Category "Transporte" e uma regra que case com a descrição "UBER". Importar um CSV com uma linha "UBER TRIP" e outra "PADARIA". Conferir em `GET /transactions` que a primeira tem Category "Transporte" e a segunda tem Category "Não categorizada" (`SEA-52`).

### P1: Estatísticas e resumos de gastos ⭐ MVP

**História**: Como usuário da API, quero ver total, média, mediana e distribuição dos meus gastos por categoria, período e estabelecimento para entender para onde vai meu dinheiro.

**Por que P1**: O critério de conclusão exige "visualizar estatísticas de gastos", e `GET /analytics/summary` e `GET /analytics/categories` são endpoints mínimos.

**Critérios de aceite**:

| ID | Critério |
|---|---|
| `SEA-20` | WHEN o usuário chama `GET /analytics/summary` THEN o sistema SHALL retornar, para as despesas do escopo consultado, o total, a quantidade, a média aritmética e a mediana dos valores, arredondados a 2 casas decimais. |
| `SEA-21` | WHEN o usuário chama `GET /analytics/summary` com filtro de período, de Category ou de estabelecimento, sozinhos ou combinados THEN o sistema SHALL calcular as estatísticas de `SEA-20` apenas sobre as despesas que atendem a todos os filtros informados. |
| `SEA-22` | WHEN o usuário chama `GET /analytics/summary` THEN o sistema SHALL incluir o desdobramento por estabelecimento, com total e quantidade de despesas de cada um, dentro do escopo consultado (premissa P-01). |
| `SEA-23` | WHEN o usuário chama `GET /analytics/categories` THEN o sistema SHALL retornar, para cada Category com pelo menos uma despesa no escopo consultado, o total, a quantidade, a média e a mediana. As despesas sem regra correspondente aparecem na Category "Não categorizada" (`SEA-52`). |
| `SEA-24` | WHEN o usuário chama `GET /analytics/categories` com filtro de período THEN o sistema SHALL considerar apenas as despesas com data no intervalo fechado informado. |
| `SEA-25` | WHEN existem receitas persistidas (decisão LAC-03) THEN o sistema SHALL excluí-los de todos os cálculos de `SEA-20` a `SEA-24`. |
| `SEA-26` | WHEN o conjunto de despesas é conhecido (ex.: valores 10,00, 20,00 e 60,00) THEN o sistema SHALL retornar total 90,00, média 30,00 e mediana 20,00. Com quantidade par, a mediana SHALL ser a média dos dois valores centrais. |
| `SEA-54` | WHEN o escopo consultado tem despesas em mais de uma moeda THEN `GET /analytics/summary`, `GET /analytics/categories`, `GET /analytics/monthly` e o cálculo de anomalias SHALL produzir resultados separados por moeda, cada grupo identificado pelo código da moeda, e SHALL NOT somar nem comparar valores de moedas diferentes (decisões LAC-16 e LAC-16b). |
| `SEA-55` | WHEN o usuário chama `GET /analytics/categories` THEN o sistema SHALL incluir, para cada Category de cada moeda, o percentual que ela representa do total de despesas daquela moeda no escopo, com 2 casas decimais. A soma dos percentuais de uma moeda SHALL ficar em 100,00 ± 0,01 (decisão LAC-14). |
| `SEA-56` | WHEN o usuário chama `GET /analytics/summary` THEN o sistema SHALL incluir, por moeda, o histograma de despesas nas faixas de valor [0, 50), [50, 100), [100, 500) e [500, ∞), com a quantidade e o total de cada faixa, incluindo as faixas vazias com quantidade 0 (decisão LAC-14). |
| `SEA-57` | WHEN `GET /analytics/summary`, `GET /analytics/categories` ou `GET /anomalies` é chamado sem filtro de período THEN o sistema SHALL considerar todo o histórico de transações (decisão LAC-18). |

Decisões aplicadas nesta história: LAC-14, LAC-16, LAC-16b e LAC-18.
Premissa P-01 em `SEA-22`.

**Teste independente**: Carregar um conjunto fixo de despesas com valores conhecidos (por importação ou dados de teste) e comparar a resposta dos dois endpoints com os valores calculados à mão.

### P1: Lista de possíveis anomalias ⭐ MVP

**História**: Como usuário da API, quero receber a lista de despesas potencialmente anormais, com o motivo, para revisar gastos fora do meu padrão.

**Por que P1**: O critério de conclusão exige "receber uma lista de possíveis anomalias", e `GET /anomalies` é endpoint mínimo.

**Critérios de aceite**:

| ID | Critério |
|---|---|
| `SEA-27` | WHEN o usuário chama `GET /anomalies` THEN o sistema SHALL retornar a lista de Anomaly, cada uma com a transação associada (id, data, descrição, estabelecimento, valor, Category), o método estatístico usado, o valor calculado (Z-Score ou limite IQR) e um motivo legível. |
| `SEA-28` | WHEN a detecção roda sobre um conjunto conhecido de despesas com um valor claramente discrepante (ex.: 20 despesas entre 40,00 e 60,00 e uma de 5.000,00 na mesma Category) THEN o sistema SHALL marcar a de 5.000,00 como anomalia e nenhuma das outras 20. |
| `SEA-29` | WHEN a detecção roda THEN o sistema SHALL avaliar somente despesas. Receitas (decisão LAC-03) nunca SHALL gerar Anomaly. |
| `SEA-30` | WHEN o mesmo conjunto de dados é avaliado mais de uma vez com os mesmos parâmetros THEN o sistema SHALL produzir o mesmo conjunto de anomalias, sem duplicar registros de Anomaly para a mesma transação e o mesmo método. |
| `SEA-31` | WHEN o usuário chama `GET /anomalies` com filtro de período THEN o sistema SHALL retornar apenas as anomalias cujas transações têm data no intervalo fechado informado. |
| `SEA-58` | WHEN a detecção roda THEN o sistema SHALL agrupar as despesas por (Category, moeda) e SHALL marcar como anomalia a despesa cujo valor for maior que Q3 + k × IQR do seu grupo, com k = 1,5 por padrão e configurável por variável de ambiente (decisões LAC-12 e LAC-16). |
| `SEA-59` | WHEN um grupo (Category, moeda) tem menos despesas que a amostra mínima (padrão 8, configurável por variável de ambiente) THEN o sistema SHALL NOT avaliar nem marcar nenhuma despesa desse grupo (decisão LAC-12). |
| `SEA-60` | WHEN uma importação termina com status "Concluída" ou "Concluída com rejeições" THEN o sistema SHALL recalcular as anomalias sobre todo o histórico de despesas e substituir o conjunto persistido de Anomaly pelo resultado do novo cálculo (decisão LAC-13). |

Decisões aplicadas nesta história: LAC-12, LAC-13 e LAC-16.

**Teste independente**: Importar o CSV do exemplo de `SEA-28` e conferir que `GET /anomalies` retorna exatamente a transação de 5.000,00 com método e motivo.

### P2: Dados mensais para relatórios e gráficos

**História**: Como usuário da API, quero obter meus gastos agregados mês a mês, no total e por categoria, para montar gráficos de evolução.

**Por que P2**: Faz parte dos requisitos principais, mas não está nos endpoints mínimos nem no critério de conclusão. As histórias P1 funcionam sem ela.

**Critérios de aceite**:

| ID | Critério |
|---|---|
| `SEA-32` | WHEN o usuário solicita a série mensal para um período THEN o sistema SHALL retornar um item por mês-calendário (AAAA-MM) do período, com o total e a quantidade de despesas do mês. |
| `SEA-33` | WHEN um mês do período solicitado não tem despesas THEN o sistema SHALL incluir esse mês na série com total 0,00 e quantidade 0, sem lacunas na sequência de meses. |
| `SEA-34` | WHEN o usuário solicita a série mensal THEN o sistema SHALL incluir, para cada mês, o total por Category. |
| `SEA-61` | WHEN o usuário chama o endpoint dedicado `GET /analytics/monthly` com filtro de período THEN o sistema SHALL retornar a série mensal de `SEA-32` a `SEA-34`, separada por moeda conforme `SEA-54` (decisão LAC-15). |
| `SEA-62` | WHEN `GET /analytics/monthly` é chamado sem filtro de período THEN o sistema SHALL considerar todo o histórico, do mês da despesa mais antiga ao da mais recente (extensão da decisão LAC-18 ao endpoint criado por LAC-15). |

Decisão aplicada nesta história: LAC-15.

**Teste independente**: Importar despesas de janeiro e março de um mesmo ano, pedir a série de janeiro a março e conferir 3 itens, com fevereiro zerado.

### P3: Recategorização de transações já importadas

**História**: Como usuário da API, quero que as transações antigas reflitam as regras de categorização atuais para que as estatísticas por categoria continuem coerentes.

**Por que P3**: Útil quando as regras evoluem, mas o MVP funciona categorizando apenas no momento da importação.

**Critérios de aceite** (decisão LAC-11: recategorização sob demanda):

| ID | Critério |
|---|---|
| `SEA-63` | WHEN o usuário chama `POST /transactions/recategorize` THEN o sistema SHALL reaplicar as CategorizationRule atuais a todas as transações persistidas, com as mesmas regras de `SEA-17`, `SEA-46`, `SEA-47` e `SEA-52`, e SHALL responder HTTP 200 com a quantidade de transações avaliadas e a de transações cuja Category mudou. |
| `SEA-64` | WHEN uma CategorizationRule é criada, atualizada ou excluída THEN o sistema SHALL NOT alterar a Category de nenhuma transação já persistida até a recategorização de `SEA-63` ser chamada. |
| `SEA-65` | WHEN a recategorização termina THEN o sistema SHALL recalcular as anomalias como em `SEA-60`, porque os grupos (Category, moeda) podem ter mudado. |
| `SEA-66` | WHEN `POST /transactions/recategorize` é chamado duas vezes seguidas sem mudança de regras THEN a segunda resposta SHALL informar 0 transações alteradas. |

**Teste independente**: Importar um CSV com uma transação "UBER TRIP" que fica em "Não categorizada". Criar uma regra "UBER" para "Transporte", conferir que a transação continua em "Não categorizada", chamar `POST /transactions/recategorize` e conferir "Transporte" em `GET /transactions/{id}`.

## 7. Estados e Transições

Entidade com ciclo de vida: **Import**. O processamento é síncrono (decisão
LAC-06), então "Processando" é um estado interno que nunca aparece numa
resposta: `POST /imports` sempre devolve o Import em estado terminal
(`SEA-45`). O estado "Concluída com rejeições" vem da decisão LAC-04.

| De | Evento | Para | Quem pode disparar | Efeito colateral |
|---|---|---|---|---|
| (inexistente) | Arquivo recebido em `POST /imports` e aceito na validação estrutural | Processando | Usuário da API | Registro Import criado com nome do arquivo e momento do envio. |
| (inexistente) | Arquivo recusado na validação estrutural (vazio, ilegível, sem coluna obrigatória ou acima do limite) | Nenhum Import persistido | Usuário da API | Nenhuma Transaction criada. Resposta de erro (`SEA-90` a `SEA-92`, `SEA-104`). |
| (inexistente) | Arquivo idêntico a um Import anterior "Concluída" ou "Concluída com rejeições" | Nenhum Import persistido | Usuário da API | HTTP 409, nenhuma Transaction criada (`SEA-43`). |
| Processando | Processamento terminou sem nenhuma linha inválida | Concluída | Sistema | Transactions persistidas (exceto duplicadas), contagens gravadas no Import e anomalias recalculadas (`SEA-60`). |
| Processando | Processamento terminou com pelo menos uma linha inválida | Concluída com rejeições | Sistema | Linhas válidas persistidas (exceto duplicadas), rejeições registradas por linha (`SEA-41`) e anomalias recalculadas (`SEA-60`). |
| Processando | Falha durante o processamento ou a persistência (ex.: banco indisponível) | Falhou | Sistema | Nenhuma Transaction daquele Import permanece persistida (`SEA-97`). Motivo registrado no Import e no log. |

- **Estados terminais**: Concluída, Concluída com rejeições e Falhou.
- **Transições proibidas**: qualquer saída de Concluída, Concluída com rejeições ou Falhou. Um Import terminal nunca é reprocessado. Uma nova tentativa é sempre um novo Import.

## 8. Casos de Borda e Erros

| ID | Situação | Comportamento esperado |
|---|---|---|
| `SEA-90` | Vazio: arquivo sem bytes ou só com cabeçalho | WHEN o CSV enviado está vazio ou contém apenas o cabeçalho THEN o sistema SHALL responder HTTP 422 com erro indicando arquivo sem transações e SHALL NOT criar nenhuma Transaction nem Import. |
| `SEA-91` | Entrada inválida: arquivo não é CSV legível (binário ou encoding diferente de UTF-8; decisão LAC-02) | WHEN o arquivo não pode ser lido como CSV THEN o sistema SHALL responder HTTP 422 com erro de formato e SHALL NOT criar nenhuma Transaction. |
| `SEA-92` | Entrada inválida: cabeçalho sem coluna obrigatória | WHEN falta ao CSV uma ou mais das colunas obrigatórias `date`, `description` e `amount` (decisão LAC-02) THEN o sistema SHALL responder HTTP 422 listando os nomes das colunas ausentes e SHALL NOT criar nenhuma Transaction. |
| `SEA-93` | Recurso inexistente | WHEN o usuário chama `GET /transactions/{id}` com id que não existe THEN o sistema SHALL responder HTTP 404 com o corpo de erro padrão (`SEA-05`). |
| `SEA-94` | Entrada inválida: id malformado | WHEN o usuário chama `GET /transactions/{id}` com id em formato inválido THEN o sistema SHALL responder HTTP 422 com o corpo de erro padrão. |
| `SEA-95` | Vazio: analytics sem dados | WHEN não há despesas no escopo consultado de `GET /analytics/summary` ou `GET /analytics/categories` THEN o sistema SHALL responder HTTP 200 sem nenhum grupo de moeda, ou seja, com lista de moedas vazia (ajustado pela decisão LAC-16: os resultados são sempre agrupados por moeda, `SEA-54`). |
| `SEA-96` | Vazio: anomalias sem dados suficientes | WHEN não há despesas, ou nenhum grupo (Category, moeda) atinge a amostra mínima de `SEA-59`, THEN `GET /anomalies` SHALL responder HTTP 200 com lista vazia. |
| `SEA-97` | Falha de dependência externa: PostgreSQL indisponível | WHEN o banco fica indisponível durante uma requisição THEN o sistema SHALL responder HTTP 503 com o corpo de erro padrão, SHALL registrar o erro em log e, se for uma importação, SHALL NOT deixar transações parciais daquele Import persistidas. |
| `SEA-98` | Concorrência: duas importações simultâneas | WHEN dois `POST /imports` com arquivos diferentes são processados ao mesmo tempo THEN o sistema SHALL persistir as transações de cada um vinculadas ao seu próprio Import, com contagens corretas e independentes. Arquivos iguais em paralelo: `SEA-106`. |
| `SEA-99` | Entrada inválida: período invertido | WHEN qualquer endpoint recebe filtro de período com data inicial posterior à data final THEN o sistema SHALL responder HTTP 422 com o corpo de erro padrão. |
| `SEA-100` | Entrada inválida: data em formato inválido no filtro | WHEN um filtro de data não está no formato ISO 8601 (AAAA-MM-DD) THEN o sistema SHALL responder HTTP 422 com o corpo de erro padrão. |
| `SEA-101` | Limite: Category inexistente no filtro | WHEN `GET /transactions` ou `GET /analytics/summary` recebe filtro por uma Category que não existe THEN o sistema SHALL responder HTTP 200 com resultado vazio ou zerado, sem erro. |
| `SEA-102` | Limite: todas as linhas de dados são inválidas | WHEN nenhuma linha de dados do CSV é válida THEN o sistema SHALL responder HTTP 201 com o Import em "Concluída com rejeições", 0 transações importadas e todas as linhas listadas nas rejeições (decisão LAC-04). |
| `SEA-103` | Duplicata dentro do mesmo arquivo | WHEN duas linhas do mesmo CSV têm a mesma chave de deduplicação THEN o sistema SHALL importar a primeira e contar a segunda como duplicada (decisão LAC-05). |
| `SEA-104` | Limite superior: arquivo muito grande | WHEN o arquivo enviado passa do tamanho máximo (padrão 10 MB, configurável por variável de ambiente) THEN o sistema SHALL responder HTTP 413 com o corpo de erro padrão, sem criar Import nem Transaction (decisão LAC-07). |
| `SEA-105` | Entrada inválida: paginação | WHEN `GET /transactions` recebe `limit` menor que 1 ou maior que 500, ou `offset` negativo THEN o sistema SHALL responder HTTP 422 com o corpo de erro padrão (decisão LAC-17). |
| `SEA-106` | Concorrência: o mesmo arquivo enviado duas vezes em paralelo | WHEN dois `POST /imports` com conteúdo idêntico são processados ao mesmo tempo THEN o sistema SHALL NOT persistir duas Transactions com a mesma chave de deduplicação. Ao final, cada linha única do arquivo existe exatamente uma vez (decisão LAC-05). |
| `SEA-107` | Reenvio após falha | WHEN o usuário reenvia um arquivo idêntico ao de um Import com status "Falhou" THEN o sistema SHALL aceitá-lo e processá-lo como novo Import, sem responder HTTP 409. |
| `SEA-108` | Entrada inválida: moeda padrão mal configurada | WHEN a variável `DEFAULT_CURRENCY` contém código fora da ISO 4217 THEN o sistema SHALL encerrar a inicialização como em `SEA-03` (decisão LAC-16b). |
| `SEA-109` | Vazio: recategorização sem transações | WHEN `POST /transactions/recategorize` é chamado sem nenhuma transação persistida THEN o sistema SHALL responder HTTP 200 com 0 transações avaliadas e 0 alteradas. |
| — | Permissão ausente | Não se aplica: acesso aberto por decisão LAC-01, coberto por `SEA-35`. O risco está na seção 10. |
| `SEA-110` | Entrada inválida: `amount` igual a zero | WHEN uma linha do CSV tem `amount` igual a zero THEN o sistema SHALL tratá-la como linha inválida, registrá-la nas rejeições do Import com o número da linha e o motivo, e SHALL NOT criar Transaction para ela (decisões LAC-20 e LAC-04). |

## 9. Mensagens ao Usuário

Canal: corpo JSON de erro padrão da API (`SEA-05`), em português do Brasil
(idioma do projeto). Os textos abaixo são de referência. A redação exata
pode ser ajustada no plano sem mudar o significado.

| Situação | Mensagem | Tom / canal |
|---|---|---|
| Arquivo vazio (`SEA-90`) | "O arquivo enviado não contém transações." | Objetivo, corpo de erro JSON |
| Arquivo ilegível (`SEA-91`) | "Não foi possível ler o arquivo como CSV." | Objetivo, corpo de erro JSON |
| Colunas ausentes (`SEA-92`) | "Colunas obrigatórias ausentes: {lista}." | Objetivo, corpo de erro JSON |
| Transação inexistente (`SEA-93`) | "Transação não encontrada." | Objetivo, corpo de erro JSON |
| Nome de Category inválido (`SEA-16`) | "O nome da categoria é obrigatório." | Objetivo, corpo de erro JSON |
| Regra com Category inexistente (`SEA-18`) | "Categoria informada na regra não existe." | Objetivo, corpo de erro JSON |
| Período invertido (`SEA-99`) | "A data inicial deve ser anterior ou igual à data final." | Objetivo, corpo de erro JSON |
| Banco indisponível (`SEA-97`) | "Serviço temporariamente indisponível. Tente novamente." | Neutro, corpo de erro JSON |
| Erro inesperado (`SEA-06`) | "Erro interno. Identificador: {id}." | Neutro, corpo de erro JSON |
| Arquivo acima do limite (`SEA-104`) | "O arquivo excede o tamanho máximo de {limite} MB." | Objetivo, corpo de erro JSON |
| Arquivo já importado (`SEA-43`) | "Este arquivo já foi importado (importação {id})." | Objetivo, corpo de erro JSON |
| Category duplicada (`SEA-53`) | "Já existe uma categoria com este nome." | Objetivo, corpo de erro JSON |
| Regra inexistente (`SEA-49`) | "Regra de categorização não encontrada." | Objetivo, corpo de erro JSON |
| Paginação inválida (`SEA-105`) | "Parâmetros de paginação inválidos: limit deve estar entre 1 e 500 e offset não pode ser negativo." | Objetivo, corpo de erro JSON |
| Motivo de rejeição de linha (`SEA-41`) | "Linha {n}: {motivo}" (ex.: "Linha 12: data inválida", "Linha 15: moeda fora da ISO 4217") | Objetivo, item da lista de rejeições do Import |

## 10. Requisitos Não-Funcionais

| Eixo | Requisito |
|---|---|
| Performance | A descrição não define meta numérica. Esta feature não tem critério de aceite de desempenho (testes de carga estão na seção 3). O processamento é síncrono (`SEA-45`), então importações até o tamanho máximo de 10 MB (`SEA-104`) não podem estourar o tempo limite de requisição configurado no ambiente Docker. |
| Volume | Projeto de demonstração, com uma instância da API e um banco. Tamanho máximo de 10 MB por arquivo, configurável (`SEA-104`). Listagem de transações paginada com no máximo 500 itens por página (`SEA-67`). |
| Concorrência | Importações simultâneas são independentes (`SEA-98`) e não geram transações duplicadas entre si (`SEA-106`). A persistência de um Import é atômica frente a falhas (`SEA-97`). |
| Segurança | **Risco explícito aceito (decisão LAC-01 = A):** a API não tem autenticação nem autorização. Qualquer cliente com acesso de rede lê, cria e altera dados financeiros e dispara importações e recategorizações (`SEA-35`). Mitigação exigida: o Docker Compose publica a API só em interface local (localhost), e o README declara que o projeto é mono-usuário, de demonstração, e não deve ser exposto à internet. Adicionar autenticação depois exige feature própria. Credenciais e segredos só por variáveis de ambiente, nunca versionados. Respostas de erro sem stack trace nem detalhes internos (`SEA-05`). O conteúdo do CSV é tratado como entrada não confiável e validado antes de persistir. |
| Privacidade / LGPD | Há dados financeiros pessoais (descrições, estabelecimentos, valores). Os logs não registram linhas do CSV nem descrições de transações, apenas ids, contagens e metadados do Import. Não há exclusão de dados importados pela API (decisão LAC-09 = A; ver seção 3). A remoção só é possível apagando o volume do banco no ambiente local. **Risco aceito**: a API não atende pedidos de exclusão de dado pessoal, o que é aceitável para uso local mono-usuário e precisa ser revisto antes de qualquer uso por terceiros. Não há outro requisito de retenção na descrição. |
| Acessibilidade | Não se aplica (API sem interface gráfica). |
| i18n / formato | Datas na API em ISO 8601 (AAAA-MM-DD). Valores monetários como decimal com 2 casas. Mensagens de erro em português do Brasil. Multimoeda sem conversão: código ISO 4217 por transação, padrão `DEFAULT_CURRENCY` = BRL, agregações separadas por moeda (`SEA-38`, `SEA-54`). CSV de entrada em UTF-8, separador vírgula, data AAAA-MM-DD e ponto decimal (`SEA-36`). Fuso horário: não se aplica, porque as transações são datas-calendário sem hora. |
| Observabilidade | Logs de início e fim de cada importação (`SEA-14`). Erros inesperados em log com identificador de correlação (`SEA-06`). Nível de log configurável por variável de ambiente. |
| Compatibilidade | Não se aplica a dados ou integrações existentes (greenfield). O esquema do banco nasce e evolui só por migrações Alembic versionadas (`SEA-01`). |

## 11. Rastreabilidade

| ID | História | Prioridade | Status |
|---|---|---|---|
| `SEA-01` | P1: Ambiente reproduzível e pipeline de CI | P1 | Pendente |
| `SEA-02` | P1: Ambiente reproduzível e pipeline de CI | P1 | Pendente |
| `SEA-03` | P1: Ambiente reproduzível e pipeline de CI | P1 | Pendente |
| `SEA-04` | P1: Ambiente reproduzível e pipeline de CI | P1 | Pendente |
| `SEA-05` | P1: Ambiente reproduzível e pipeline de CI | P1 | Pendente |
| `SEA-06` | P1: Ambiente reproduzível e pipeline de CI | P1 | Pendente |
| `SEA-07` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-08` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-09` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-10` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-11` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-12` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-13` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-14` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-15` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-16` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-17` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-18` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-19` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-20` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-21` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-22` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-23` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-24` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-25` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-26` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-27` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-28` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-29` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-30` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-31` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-32` | P2: Dados mensais para relatórios e gráficos | P2 | Pendente |
| `SEA-33` | P2: Dados mensais para relatórios e gráficos | P2 | Pendente |
| `SEA-34` | P2: Dados mensais para relatórios e gráficos | P2 | Pendente |
| `SEA-90` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-91` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-92` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-93` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-94` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-95` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-96` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-97` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-98` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-99` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-100` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-101` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-35` | P1: Ambiente reproduzível e pipeline de CI | P1 | Pendente |
| `SEA-36` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-37` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-38` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-39` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-40` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-41` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-42` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-43` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-44` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-45` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-46` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-47` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-48` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-49` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-50` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-51` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-52` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-53` | P1: Categorização automática por regras configuráveis | P1 | Pendente |
| `SEA-54` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-55` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-56` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-57` | P1: Estatísticas e resumos de gastos | P1 | Pendente |
| `SEA-58` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-59` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-60` | P1: Lista de possíveis anomalias | P1 | Pendente |
| `SEA-61` | P2: Dados mensais para relatórios e gráficos | P2 | Pendente |
| `SEA-62` | P2: Dados mensais para relatórios e gráficos | P2 | Pendente |
| `SEA-63` | P3: Recategorização de transações já importadas | P3 | Pendente |
| `SEA-64` | P3: Recategorização de transações já importadas | P3 | Pendente |
| `SEA-65` | P3: Recategorização de transações já importadas | P3 | Pendente |
| `SEA-66` | P3: Recategorização de transações já importadas | P3 | Pendente |
| `SEA-67` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-68` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-102` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-103` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-104` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-105` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-106` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-107` | P1: Importar CSV e consultar transações | P1 | Pendente |
| `SEA-108` | P1: Ambiente reproduzível e pipeline de CI | P1 | Pendente |
| `SEA-109` | P3: Recategorização de transações já importadas | P3 | Pendente |
| `SEA-110` | P1: Importar CSV e consultar transações | P1 | Pendente |

**Cobertura**: 89 requisitos no total (68 critérios de história, `SEA-01` a
`SEA-68`, e 21 casos de borda, `SEA-90` a `SEA-110`). Por prioridade: P1 = 79,
P2 = 5, P3 = 5.

## 12. Lacunas

### Lacunas resolvidas (decisions.md, 2026-09-26)

| Lacuna | Escolha | Critérios gerados ou ajustados |
|---|---|---|
| LAC-01 | A: mono-usuário, sem autenticação (diverge da recomendação) | `SEA-35`; seção 5; risco na seção 10 (Segurança) |
| LAC-02 | A: layout fixo `date`/`description`/`amount`/`merchant`/`currency`, UTF-8, vírgula | `SEA-36`, `SEA-37`; `SEA-91` e `SEA-92` ajustados |
| LAC-03 | B: importar tudo com tipo; estatísticas só sobre despesas | `SEA-39`, `SEA-40`; `SEA-25` e `SEA-29` ajustados |
| LAC-04 | B: importar válidas e registrar inválidas por linha | `SEA-41`, `SEA-42`, `SEA-102`; seção 7 |
| LAC-05 | C: hash do arquivo + chave por transação | `SEA-43`, `SEA-44`, `SEA-103`, `SEA-106`, `SEA-107` |
| LAC-06 | A: síncrono, HTTP 201 | `SEA-45`; seção 7 |
| LAC-07 | A: 10 MB configurável, HTTP 413 | `SEA-104` |
| LAC-08 | A: palavra-chave contida, prioridade numérica | `SEA-46`, `SEA-47` |
| LAC-09 | A: mínimos + CRUD de regras + listagem de categorias | `SEA-48` a `SEA-51`; seção 3 |
| LAC-10 | A: Category padrão "Não categorizada" | `SEA-52`; `SEA-11` e `SEA-23` ajustados |
| LAC-11 | B: recategorização sob demanda | `SEA-63` a `SEA-66`, `SEA-109` |
| LAC-12 | A: IQR por (Category, moeda), k = 1,5, amostra mínima 8 | `SEA-58`, `SEA-59`; `SEA-96` ajustado |
| LAC-13 | A: recalcular sobre todo o histórico ao fim de cada importação | `SEA-60` |
| LAC-14 | C: percentual por categoria + histograma por faixas | `SEA-55`, `SEA-56` |
| LAC-15 | A: endpoint dedicado de série mensal | `SEA-61`, `SEA-62` |
| LAC-16 | B: multimoeda sem conversão (diverge da recomendação) | `SEA-54`; `SEA-95` ajustado |
| LAC-16b | A: coluna `currency` opcional ISO 4217, padrão `DEFAULT_CURRENCY` = BRL | `SEA-38`, `SEA-108`; `SEA-41` e `SEA-44` |
| LAC-17 | A: limit/offset, padrão 50, máximo 500, filtros | `SEA-67`, `SEA-68`, `SEA-105` |
| LAC-18 | A: todo o histórico | `SEA-57`, `SEA-62` |
| LAC-19 | A: nome único sem distinguir caixa, HTTP 409 | `SEA-53` |
| LAC-20 | A: negativo = despesa, zero = linha inválida, estatísticas usam o módulo | `SEA-39` ajustado; `SEA-110` |

Premissa assumida: P-01 (desdobramento por estabelecimento em
`GET /analytics/summary`), marcada em `SEA-22`.

### Lacunas abertas

Nenhuma lacuna aberta.

## 13. Critérios de Sucesso da Feature

- [ ] A partir de um clone limpo, o ambiente sobe com um comando do Docker Compose e a documentação OpenAPI responde, sem passo manual além de copiar o arquivo de variáveis de exemplo.
- [ ] Um CSV de exemplo versionado no repositório é importado com sucesso, e todas as suas linhas válidas aparecem em `GET /transactions`.
- [ ] `GET /analytics/summary` e `GET /analytics/categories` retornam, para o CSV de exemplo, valores iguais aos calculados à mão (total, média, mediana).
- [ ] `GET /anomalies` retorna, para o CSV de exemplo, exatamente as transações discrepantes plantadas nele.
- [ ] O pipeline do GitHub Actions passa no branch principal, executando testes unitários e de integração, e falha quando um teste é quebrado.
- [ ] Todos os 89 IDs desta especificação têm pelo menos um teste automatizado associado.

## Autoverificação do spec

Revisado após aplicar as decisões (2026-09-26).

- [x] Todo critério de aceite tem ID único e formato WHEN/THEN/SHALL. São 89 IDs (`SEA-01` a `SEA-68` e `SEA-90` a `SEA-110`), sem duplicatas (conferido por script), e nenhum ID anterior foi renumerado.
- [x] Toda história P1 é demonstrável isoladamente. A P3 ganhou critérios e teste independente.
- [x] A seção "Fora de Escopo" tem 14 itens (2 vieram das decisões LAC-01 e LAC-09).
- [x] O glossário usa termos do codebase. Projeto greenfield: os termos seguem a descrição e as decisões; os novos (Tipo, Moeda, Não categorizada, Chave de deduplicação, Recategorização) estão marcados como `(novo)`.
- [x] Os casos de borda cobrem vazio (`SEA-90`, `SEA-95`, `SEA-96`, `SEA-109`), limite (`SEA-101`, `SEA-102`, `SEA-104`), inválido (`SEA-91`, `SEA-92`, `SEA-94`, `SEA-99`, `SEA-100`, `SEA-105`, `SEA-108`), concorrência (`SEA-98`, `SEA-106`), falha de dependência (`SEA-97`, `SEA-107`) e permissão (não se aplica, por decisão; `SEA-35` e o risco na seção 10).
- [x] Todos os eixos de NFR estão preenchidos ou marcados "não se aplica". Os riscos aceitos de LAC-01 e LAC-09 estão explícitos.
- [x] Toda lacuna tem severidade, opções e recomendação. Nenhuma lacuna aberta. LAC-20 foi resolvida (A).
- [x] Nenhuma decisão técnica de implementação vazou para o spec. Os caminhos citados são contrato de API (`/categorization-rules`, `GET /categories`, `GET /analytics/monthly`, `POST /transactions/recategorize`), não arquivos nem classes.

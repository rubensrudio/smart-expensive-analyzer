"""Teste de aceitação ponta a ponta com o CSV de exemplo (TASK-032; SEA-02, SEA-35).

Só HTTP, pelo `client` e sem cabeçalho `Authorization`. O teste cria as categorias e
as regras, importa `samples/transacoes_exemplo.csv` e confere as respostas contra
constantes calculadas à mão a partir do arquivo.

Conteúdo do CSV (dados fictícios, BRL, jan–mar/2026):
- Alimentação (mercado/padaria/restaurante): 12 despesas entre 40.00 e 60.00 mais
  1 de 5000.00 (anomalia plantada; grupo de 13 >= amostra mínima 8, SEA-28/SEA-59);
- Transporte (uber/posto): 7 despesas (grupo < 8, não avaliado);
- Moradia (aluguel/energia): 6 despesas (grupo < 8, não avaliado);
- 2 receitas (sem regra, ficam em "Não categorizada" e fora dos cálculos, SEA-25);
- 1 linha vazia (ignorada) e 1 linha com data inválida (linha física 22, rejeitada).

Cálculos à mão (valores em módulo, 26 despesas):
- total = 5596.30 + 423.40 + 5065.73 = 11085.43; média = 11085.43 / 26 = 426.362 → 426.36;
  mediana = (53.10 + 55.00) / 2 = 54.05 (13º e 14º valores ordenados).
- Alimentação: 13 despesas, total 5596.30, média 430.485 → 430.48 (430.4846...), mediana 50.00.
  IQR (percentil linear, n=13): Q1 = 46.60 (posição 3), Q3 = 55.00 (posição 9),
  IQR = 8.40, limite = 55.00 + 1.5 × 8.40 = 67.60 → só 5000.00 passa do limite.
- Moradia: 6, total 5065.73, média 844.288 → 844.29, mediana (201.48 + 1500.00) / 2 = 850.74.
- Transporte: 7, total 423.40, média 60.4857 → 60.49, mediana 42.30.
- Percentuais (maior resto em centésimos): 50.483 / 45.697 / 3.819 → pisos 5048 + 4569 + 381
  = 9998; os 2 centésimos faltantes vão para os maiores restos (Transporte .943, Moradia
  .719) → 50.48 / 45.70 / 3.82 (soma 100.00).
"""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

SAMPLE_CSV = Path(__file__).resolve().parents[3] / "samples" / "transacoes_exemplo.csv"
PERIOD = {"start_date": "2026-01-01", "end_date": "2026-03-31"}
DEFAULT_CATEGORY = "Não categorizada"

CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "Alimentação": ("mercado", "padaria", "restaurante"),
    "Transporte": ("uber", "posto"),
    "Moradia": ("aluguel", "energia"),
}

EXPECTED_PATHS = {
    "/imports",
    "/transactions",
    "/transactions/{transaction_id}",
    "/transactions/recategorize",
    "/categories",
    "/categorization-rules",
    "/categorization-rules/{rule_id}",
    "/analytics/summary",
    "/analytics/categories",
    "/analytics/monthly",
    "/anomalies",
    "/health",
}

# (date, description, amount, merchant, category) de cada linha válida do CSV.
EXPECTED_TRANSACTIONS: set[tuple[str, str, str, str, str]] = {
    ("2026-01-03", "MERCADO COMPRA SEMANAL", "-42.50", "Mercado Bom Preço", "Alimentação"),
    ("2026-01-05", "UBER VIAGEM CENTRO", "-25.40", "Uber", "Transporte"),
    ("2026-01-05", "SALARIO MENSAL", "7000.00", "Empresa Exemplo", DEFAULT_CATEGORY),
    ("2026-01-08", "ALUGUEL JANEIRO", "-1500.00", "Imobiliária Lar", "Moradia"),
    ("2026-01-10", "PADARIA CAFE DA MANHA", "-55.00", "Padaria Pão Quente", "Alimentação"),
    ("2026-01-12", "POSTO COMBUSTIVEL", "-89.90", "Posto Estrada", "Transporte"),
    ("2026-01-15", "ENERGIA CONTA JANEIRO", "-187.35", "Companhia Energia", "Moradia"),
    ("2026-01-18", "RESTAURANTE ALMOCO", "-48.90", "Restaurante Sabor", "Alimentação"),
    ("2026-01-25", "MERCADO REPOSICAO", "-51.20", "Mercado Bom Preço", "Alimentação"),
    ("2026-02-02", "MERCADO COMPRA SEMANAL", "-44.00", "Mercado Bom Preço", "Alimentação"),
    ("2026-02-04", "UBER VIAGEM AEROPORTO", "-31.70", "Uber", "Transporte"),
    ("2026-02-06", "ALUGUEL FEVEREIRO", "-1500.00", "Imobiliária Lar", "Moradia"),
    ("2026-02-09", "RESTAURANTE JANTAR", "-59.90", "Restaurante Sabor", "Alimentação"),
    ("2026-02-11", "POSTO COMBUSTIVEL", "-120.00", "Posto Estrada", "Transporte"),
    ("2026-02-14", "MERCADO COMPRA FESTA ANUAL", "-5000.00", "Mercado Bom Preço", "Alimentação"),
    ("2026-02-15", "ENERGIA CONTA FEVEREIRO", "-201.48", "Companhia Energia", "Moradia"),
    ("2026-02-17", "PADARIA LANCHE", "-47.30", "Padaria Pão Quente", "Alimentação"),
    ("2026-02-20", "FREELANCE PROJETO", "1200.00", "Cliente Exemplo", DEFAULT_CATEGORY),
    ("2026-02-24", "MERCADO REPOSICAO", "-53.10", "Mercado Bom Preço", "Alimentação"),
    ("2026-03-01", "MERCADO COMPRA SEMANAL", "-40.00", "Mercado Bom Preço", "Alimentação"),
    ("2026-03-03", "UBER VIAGEM BAIRRO", "-18.60", "Uber", "Transporte"),
    ("2026-03-06", "ALUGUEL MARCO", "-1500.00", "Imobiliária Lar", "Moradia"),
    ("2026-03-09", "RESTAURANTE ALMOCO", "-57.80", "Restaurante Sabor", "Alimentação"),
    ("2026-03-12", "POSTO COMBUSTIVEL", "-95.50", "Posto Estrada", "Transporte"),
    ("2026-03-15", "ENERGIA CONTA MARCO", "-176.90", "Companhia Energia", "Moradia"),
    ("2026-03-18", "PADARIA CAFE DA MANHA", "-46.60", "Padaria Pão Quente", "Alimentação"),
    ("2026-03-22", "UBER VIAGEM CENTRO", "-42.30", "Uber", "Transporte"),
    ("2026-03-27", "MERCADO REPOSICAO", "-50.00", "Mercado Bom Preço", "Alimentação"),
}
VALID_ROWS = 28
DATA_ROWS_READ = 29  # linhas não vazias depois do cabeçalho (28 válidas + 1 inválida)
INVALID_LINE = 22
INVALID_REASON = "Linha 22: data inválida"

EXPECTED_SUMMARY = {
    "currency": "BRL",
    "total": "11085.43",
    "count": 26,
    "mean": "426.36",
    "median": "54.05",
    "by_merchant": [
        {"merchant": "Mercado Bom Preço", "total": "5280.80", "count": 7},
        {"merchant": "Imobiliária Lar", "total": "4500.00", "count": 3},
        {"merchant": "Companhia Energia", "total": "565.73", "count": 3},
        {"merchant": "Posto Estrada", "total": "305.40", "count": 3},
        {"merchant": "Restaurante Sabor", "total": "166.60", "count": 3},
        {"merchant": "Padaria Pão Quente", "total": "148.90", "count": 3},
        {"merchant": "Uber", "total": "118.00", "count": 4},
    ],
    "histogram": [
        {"range_start": "0.00", "range_end": "50.00", "count": 10, "total": "387.30"},
        {"range_start": "50.00", "range_end": "100.00", "count": 8, "total": "512.40"},
        {"range_start": "100.00", "range_end": "500.00", "count": 4, "total": "685.73"},
        {"range_start": "500.00", "range_end": None, "count": 4, "total": "9500.00"},
    ],
}

# (category_name, total, count, mean, median, percentage), ordem: total desc.
EXPECTED_CATEGORIES = [
    ("Alimentação", "5596.30", 13, "430.48", "50.00", "50.48"),
    ("Moradia", "5065.73", 6, "844.29", "850.74", "45.70"),
    ("Transporte", "423.40", 7, "60.49", "42.30", "3.82"),
]
EXPECTED_CATEGORIES_TOTAL = "11085.43"

# month → (total, count, [(category_name, total, count)] na ordem total desc).
EXPECTED_MONTHS = {
    "2026-01": (
        "2000.25",
        8,
        [("Moradia", "1687.35", 2), ("Alimentação", "197.60", 4), ("Transporte", "115.30", 2)],
    ),
    "2026-02": (
        "7057.48",
        9,
        [("Alimentação", "5204.30", 5), ("Moradia", "1701.48", 2), ("Transporte", "151.70", 2)],
    ),
    "2026-03": (
        "2027.70",
        9,
        [("Moradia", "1676.90", 2), ("Alimentação", "194.40", 4), ("Transporte", "156.40", 3)],
    ),
}

ANOMALY_TRANSACTION = ("2026-02-14", "MERCADO COMPRA FESTA ANUAL", "-5000.00")
ANOMALY_LIMIT = "67.60"


def _no_auth_header(response: Any) -> bool:
    return "authorization" not in {name.lower() for name in response.request.headers}


def _setup_categories_and_rules(client: TestClient) -> dict[str, int]:
    category_ids: dict[str, int] = {}
    for priority, (name, keywords) in enumerate(CATEGORY_RULES.items(), start=1):
        created = client.post("/categories", json={"name": name})
        assert created.status_code == 201, created.text
        category_ids[name] = int(created.json()["id"])
        for keyword in keywords:
            rule = client.post(
                "/categorization-rules",
                json={"keyword": keyword, "category_id": category_ids[name], "priority": priority},
            )
            assert rule.status_code == 201, rule.text
    return category_ids


def _import_sample(client: TestClient) -> Any:
    with SAMPLE_CSV.open("rb") as handle:
        return client.post(
            "/imports", files={"file": ("transacoes_exemplo.csv", handle, "text/csv")}
        )


@pytest.fixture
def imported(client: TestClient) -> dict[str, Any]:
    category_ids = _setup_categories_and_rules(client)
    response = _import_sample(client)
    assert response.status_code == 201, response.text
    return {"import": response.json(), "category_ids": category_ids}


def test_sample_csv_is_utf8_with_expected_header_and_size() -> None:
    lines = SAMPLE_CSV.read_bytes().decode("utf-8").splitlines()

    assert lines[0] == "date,description,amount,merchant,currency"
    assert len(lines) - 1 >= 30
    assert sum(1 for line in lines[1:] if not line.strip()) == 1


def test_openapi_exposes_exactly_the_spec_paths(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert set(response.json()["paths"]) == EXPECTED_PATHS


def test_every_endpoint_answers_without_authorization_header(client: TestClient) -> None:
    category = client.post("/categories", json={"name": "Alimentação"})
    imported = _import_sample(client)
    rules = client.get("/categorization-rules")
    rule = client.post(
        "/categorization-rules",
        json={"keyword": "mercado", "category_id": category.json()["id"], "priority": 1},
    )
    rule_id = rule.json()["id"]
    listed = client.get("/transactions")
    transaction_id = listed.json()["items"][0]["id"]
    responses = [
        category,
        imported,
        rules,
        rule,
        listed,
        client.get("/health"),
        client.get("/categories"),
        client.get(f"/transactions/{transaction_id}"),
        client.post("/transactions/recategorize"),
        client.get(f"/categorization-rules/{rule_id}"),
        client.put(
            f"/categorization-rules/{rule_id}",
            json={"keyword": "padaria", "category_id": category.json()["id"], "priority": 2},
        ),
        client.get("/analytics/summary", params=PERIOD),
        client.get("/analytics/categories", params=PERIOD),
        client.get("/analytics/monthly", params=PERIOD),
        client.get("/anomalies", params=PERIOD),
        client.delete(f"/categorization-rules/{rule_id}"),
    ]

    for response in responses:
        target = f"{response.request.method} {response.request.url.path}"
        assert _no_auth_header(response), target
        assert response.status_code not in (401, 403), target
        assert response.status_code in (200, 201, 204), f"{target}: {response.text}"


def test_import_sample_rejects_only_the_invalid_line(imported: dict[str, Any]) -> None:
    body = imported["import"]

    assert body["status"] == "concluida_com_rejeicoes"
    assert body["rows_read"] == DATA_ROWS_READ
    assert body["imported_count"] == VALID_ROWS
    assert body["rejected_count"] == 1
    assert body["duplicate_count"] == 0
    assert body["rejections"] == [{"line": INVALID_LINE, "reason": INVALID_REASON}]


def test_transactions_list_returns_every_valid_line_categorized_by_rules(
    client: TestClient, imported: dict[str, Any]
) -> None:
    response = client.get("/transactions", params={"limit": 500})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == VALID_ROWS
    assert len(body["items"]) == VALID_ROWS
    got = {
        (t["date"], t["description"], t["amount"], t["merchant"], t["category"]["name"])
        for t in body["items"]
    }
    assert got == EXPECTED_TRANSACTIONS
    assert {t["currency"] for t in body["items"]} == {"BRL"}
    assert {t["import_id"] for t in body["items"]} == {imported["import"]["id"]}
    incomes = [t for t in body["items"] if t["type"] == "receita"]
    assert sorted(t["amount"] for t in incomes) == ["1200.00", "7000.00"]


def test_summary_matches_hand_computed_constants(
    client: TestClient, imported: dict[str, Any]
) -> None:
    response = client.get("/analytics/summary")

    assert response.status_code == 200
    assert response.json() == {"currencies": [EXPECTED_SUMMARY]}


def test_categories_breakdown_matches_hand_computed_constants(
    client: TestClient, imported: dict[str, Any]
) -> None:
    ids = imported["category_ids"]

    response = client.get("/analytics/categories")

    assert response.status_code == 200
    expected = [
        {
            "category_id": ids[name],
            "category_name": name,
            "total": total,
            "count": count,
            "mean": mean,
            "median": median,
            "percentage": percentage,
        }
        for name, total, count, mean, median, percentage in EXPECTED_CATEGORIES
    ]
    assert response.json() == {
        "currencies": [
            {"currency": "BRL", "total": EXPECTED_CATEGORIES_TOTAL, "categories": expected}
        ]
    }


def test_monthly_series_matches_hand_computed_constants(
    client: TestClient, imported: dict[str, Any]
) -> None:
    ids = imported["category_ids"]

    response = client.get("/analytics/monthly", params=PERIOD)

    assert response.status_code == 200
    expected_months = [
        {
            "month": month,
            "total": total,
            "count": count,
            "by_category": [
                {"category_id": ids[name], "category_name": name, "total": t, "count": c}
                for name, t, c in by_category
            ],
        }
        for month, (total, count, by_category) in EXPECTED_MONTHS.items()
    ]
    assert response.json() == {"currencies": [{"currency": "BRL", "months": expected_months}]}


def test_anomalies_return_only_the_planted_outlier(
    client: TestClient, imported: dict[str, Any]
) -> None:
    response = client.get("/anomalies")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    anomaly = items[0]
    transaction = anomaly["transaction"]
    assert (transaction["date"], transaction["description"], transaction["amount"]) == (
        ANOMALY_TRANSACTION
    )
    assert transaction["category"]["name"] == "Alimentação"
    assert anomaly["method"] == "IQR"
    assert anomaly["value"] == ANOMALY_LIMIT
    assert anomaly["reason"]

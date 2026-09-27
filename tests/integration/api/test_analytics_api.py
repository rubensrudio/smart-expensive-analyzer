"""Testes de integração de `/analytics` (TASK-028; contrato 8.1; AS-6).

Requisitos: SEA-20..SEA-24, SEA-35, SEA-54..SEA-57, SEA-61, SEA-95.
Entrada adversarial (lições das ondas anteriores): nenhum parâmetro gera 500, o filtro
`merchant` se comporta igual ao de `/transactions` e todo dinheiro sai com 2 casas HALF_UP.
"""

import logging
from collections.abc import Iterator
from decimal import Decimal
from typing import Any, NoReturn

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.routers.analytics import get_analytics_service
from app.application.services.analytics_service import CurrencyCategories, CurrencySummary
from app.core.config import Settings
from app.domain.entities import ExpenseFilters, Period
from app.domain.monthly_series import CurrencySeries
from app.main import create_app

SUMMARY = "/analytics/summary"
CATEGORIES = "/analytics/categories"
MONTHLY = "/analytics/monthly"
ALL_ROUTES = (SUMMARY, CATEGORIES, MONTHLY)
HEADER = "date,description,amount,merchant,currency"
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1  # `category_id` é BIGINT
MERCHANT_FILTER_MAX_LENGTH = 1000
MISSING_ID = 999_999
DEFAULT_CATEGORY = "Não categorizada"
SECRET = "LOJA SIGILOSA 4242"
ERROR_KEYS = {"code", "message", "details", "error_id"}
SUMMARY_KEYS = {"currency", "total", "count", "mean", "median", "by_merchant", "histogram"}
EMPTY_BUCKETS = [
    {"range_start": "0.00", "range_end": "50.00", "count": 0, "total": "0.00"},
    {"range_start": "50.00", "range_end": "100.00", "count": 0, "total": "0.00"},
    {"range_start": "100.00", "range_end": "500.00", "count": 0, "total": "0.00"},
    {"range_start": "500.00", "range_end": None, "count": 0, "total": "0.00"},
]
THREE_EXPENSES = (
    "2026-01-05,MERCADO A,-10.00,Mercado,BRL",
    "2026-01-06,PADARIA B,-20.00,Padaria,BRL",
    "2026-01-07,LOJA C,-60.00,Loja,BRL",
    "2026-01-08,SALARIO,3000.00,Empresa,BRL",  # receita: fora de todo cálculo (SEA-25)
)


def _csv(*lines: str) -> bytes:
    return ("\n".join([HEADER, *lines]) + "\n").encode("utf-8")


def _import(client: TestClient, *lines: str, filename: str = "extrato.csv") -> None:
    response = client.post("/imports", files={"file": (filename, _csv(*lines), "text/csv")})
    assert response.status_code == 201, response.text


def _category(client: TestClient, name: str) -> int:
    response = client.post("/categories", json={"name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _rule(client: TestClient, keyword: str, category_id: int, priority: int = 1) -> None:
    response = client.post(
        "/categorization-rules",
        json={"keyword": keyword, "category_id": category_id, "priority": priority},
    )
    assert response.status_code == 201, response.text


def _no_auth_header(response: Any) -> bool:
    return "authorization" not in {name.lower() for name in response.request.headers}


def _assert_validation_error(response: Any, field: str) -> None:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert field in [detail["field"] for detail in body["details"]]


def _only_currency(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    currencies = response.json()["currencies"]
    assert len(currencies) == 1, currencies
    return dict(currencies[0])


@pytest.fixture
def isolated_app(settings: Settings) -> Iterator[FastAPI]:
    app = create_app(settings)
    yield app
    app.dependency_overrides.clear()


# --- GET /analytics/summary ----------------------------------------------------------


def test_summary_returns_stats_merchants_and_four_buckets(client: TestClient) -> None:
    """SEA-20, SEA-22, SEA-25, SEA-56: -10, -20, -60 → 90 / 30 / 20; receita ignorada."""
    _import(client, *THREE_EXPENSES)

    response = client.get(SUMMARY)

    assert _no_auth_header(response)  # SEA-35
    assert set(response.json()) == {"currencies"}
    group = _only_currency(response)
    assert set(group) == SUMMARY_KEYS
    assert group["currency"] == "BRL"
    assert (group["total"], group["count"], group["mean"], group["median"]) == (
        "90.00",
        3,
        "30.00",
        "20.00",
    )
    assert group["by_merchant"] == [
        {"merchant": "Loja", "total": "60.00", "count": 1},
        {"merchant": "Padaria", "total": "20.00", "count": 1},
        {"merchant": "Mercado", "total": "10.00", "count": 1},
    ]
    assert len(group["histogram"]) == 4
    assert group["histogram"] == [
        {"range_start": "0.00", "range_end": "50.00", "count": 2, "total": "30.00"},
        {"range_start": "50.00", "range_end": "100.00", "count": 1, "total": "60.00"},
        {"range_start": "100.00", "range_end": "500.00", "count": 0, "total": "0.00"},
        {"range_start": "500.00", "range_end": None, "count": 0, "total": "0.00"},
    ]


def test_summary_histogram_bounds_are_half_open(client: TestClient) -> None:
    """SEA-56: 50.00 cai em [50, 100); 500.00 em [500, ∞); faixas vazias com count 0."""
    _import(
        client,
        "2026-01-05,A,-49.99,M1,BRL",
        "2026-01-06,B,-50.00,M2,BRL",
        "2026-01-07,C,-500.00,M3,BRL",
    )

    buckets = _only_currency(client.get(SUMMARY))["histogram"]

    assert [(b["count"], b["total"]) for b in buckets] == [
        (1, "49.99"),
        (1, "50.00"),
        (0, "0.00"),
        (1, "500.00"),
    ]


def test_summary_rounds_mean_and_median_half_up(client: TestClient) -> None:
    """P-15: média e mediana 0.025 → "0.03" (HALF_UP), nunca "0.02" (HALF_EVEN)."""
    _import(client, "2026-01-05,A,-0.01,M1,BRL", "2026-01-06,B,-0.04,M2,BRL")

    group = _only_currency(client.get(SUMMARY))

    assert (group["total"], group["mean"], group["median"]) == ("0.05", "0.03", "0.03")


def test_summary_by_merchant_ties_ordered_by_merchant_asc(client: TestClient) -> None:
    """8.1: `by_merchant` por total desc e merchant asc; mesmo merchant soma e conta."""
    _import(
        client,
        "2026-01-05,A,-15.00,Beta,BRL",
        "2026-01-06,B,-15.00,Alfa,BRL",
        "2026-01-07,C,-5.00,Gama,BRL",
        "2026-01-08,D,-5.00,Gama,BRL",
    )

    by_merchant = _only_currency(client.get(SUMMARY))["by_merchant"]

    assert by_merchant == [
        {"merchant": "Alfa", "total": "15.00", "count": 1},
        {"merchant": "Beta", "total": "15.00", "count": 1},
        {"merchant": "Gama", "total": "10.00", "count": 2},
    ]


def test_summary_filters_combined_apply_all(client: TestClient) -> None:
    """SEA-21: período + categoria + merchant (sem caixa, espaços normalizados)."""
    food = _category(client, "Alimentação")
    _rule(client, "FEIRA", food)  # casa só pela descrição, não pelo merchant
    _import(
        client,
        "2026-01-05,FEIRA X,-10.00,Mercado Bom,BRL",
        "2026-02-05,FEIRA Y,-30.00,Mercado Bom,BRL",
        "2026-02-06,FEIRA Z,-50.00,Outro,BRL",
        "2026-02-07,UBER,-70.00,Mercado Bom,BRL",
    )

    response = client.get(
        SUMMARY,
        params={"start_date": "2026-02-01", "category_id": food, "merchant": "  mercado   BOM "},
    )

    group = _only_currency(response)
    assert (group["total"], group["count"]) == ("30.00", 1)
    assert group["by_merchant"] == [{"merchant": "Mercado Bom", "total": "30.00", "count": 1}]


def test_summary_separates_currencies_alphabetically(client: TestClient) -> None:
    """SEA-54: cada moeda é um grupo; valores de moedas diferentes nunca são somados."""
    _import(
        client,
        "2026-01-05,A,-10.00,M,USD",
        "2026-01-06,B,-20.00,M,BRL",
        "2026-01-07,C,-40.00,M,USD",
        "2026-01-08,D,-5.00,M,EUR",
    )

    response = client.get(SUMMARY)

    assert response.status_code == 200
    groups = response.json()["currencies"]
    assert [(g["currency"], g["total"], g["count"]) for g in groups] == [
        ("BRL", "20.00", 1),
        ("EUR", "5.00", 1),
        ("USD", "50.00", 2),
    ]
    assert [g["by_merchant"][0]["total"] for g in groups] == ["20.00", "5.00", "50.00"]


@pytest.mark.parametrize("value", [MISSING_ID, INT64_MAX, INT64_MIN, 0, -1])
def test_summary_category_without_expenses_returns_empty(client: TestClient, value: int) -> None:
    """SEA-101 / SEA-95: categoria inexistente → 200 com lista de moedas vazia."""
    _import(client, *THREE_EXPENSES)

    response = client.get(SUMMARY, params={"category_id": value})

    assert response.status_code == 200, response.text
    assert response.json() == {"currencies": []}


@pytest.mark.parametrize(
    "value", [str(INT64_MAX + 1), str(INT64_MIN - 1), "9" * 5000, "abc", "1.5", "", "1e3"]
)
def test_summary_invalid_category_id_returns_422(client: TestClient, value: str) -> None:
    _assert_validation_error(
        client.get(SUMMARY, params={"category_id": value}), "query.category_id"
    )


def test_summary_merchant_without_match_returns_empty(client: TestClient) -> None:
    _import(client, *THREE_EXPENSES)

    response = client.get(SUMMARY, params={"merchant": "%' OR '1'='1"})

    assert response.status_code == 200
    assert response.json() == {"currencies": []}


@pytest.mark.parametrize(
    "value",
    ["Loja\x00", "\x00", "Lo\x07ja", "Loja\x7f", "Loja\x80", "Loja\x9f", "Loja\x1b[31m"],
)
def test_summary_merchant_with_control_char_returns_422(
    client: TestClient, value: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Mesmo `MerchantFilter` de `/transactions`: NUL daria DataError (500) no PostgreSQL."""
    caplog.set_level(logging.DEBUG)

    response = client.get(SUMMARY, params={"merchant": value})

    _assert_validation_error(response, "query.merchant")
    app_logs = [r.getMessage() for r in caplog.records if not r.name.startswith("httpx")]
    assert not any(value in message for message in app_logs)


@pytest.mark.parametrize("raw", ["Loja%00", "%00", "Loja%ED%A0%80", "%FF%FE", "Loja%C0%80"])
def test_summary_merchant_raw_bytes_never_return_500(client: TestClient, raw: str) -> None:
    response = client.get(f"{SUMMARY}?merchant={raw}")

    assert response.status_code in (200, 422), response.text
    if "%00" in raw:
        _assert_validation_error(response, "query.merchant")


@pytest.mark.parametrize("value", ["", " ", "   ", "\t\n", "\x1c\x1d\x1e\x1f", "  "])
def test_summary_blank_merchant_returns_422(client: TestClient, value: str) -> None:
    """Mesma decisão de `/transactions`: merchant vazio após normalizar é inválido."""
    _assert_validation_error(client.get(SUMMARY, params={"merchant": value}), "query.merchant")


def test_summary_merchant_length_limit_measured_after_normalization(client: TestClient) -> None:
    long_merchant = "M" * MERCHANT_FILTER_MAX_LENGTH
    _import(client, f"2026-01-05,LONGA,-1.00,{long_merchant},BRL")

    at_limit = client.get(SUMMARY, params={"merchant": f"   {long_merchant}   "})
    assert _only_currency(at_limit)["total"] == "1.00"

    over = client.get(SUMMARY, params={"merchant": long_merchant + "M"})
    _assert_validation_error(over, "query.merchant")


# --- GET /analytics/categories -------------------------------------------------------


def test_categories_percentages_sum_100_and_order(client: TestClient) -> None:
    """SEA-23, SEA-55: 3 categorias iguais → 33.34 + 33.33 + 33.33 = 100.00."""
    food = _category(client, "Alimentação")
    transport = _category(client, "Transporte")
    _rule(client, "MERCADO", food)
    _rule(client, "UBER", transport)
    _import(
        client,
        "2026-01-05,MERCADO,-10.00,M,BRL",
        "2026-01-06,UBER,-10.00,U,BRL",
        "2026-01-07,OUTRA,-10.00,O,BRL",
        "2026-01-08,SALARIO,500.00,E,BRL",
    )

    group = _only_currency(client.get(CATEGORIES))

    assert set(group) == {"currency", "total", "categories"}
    assert (group["currency"], group["total"]) == ("BRL", "30.00")
    categories = group["categories"]
    assert [c["category_name"] for c in categories] == [
        "Alimentação",
        DEFAULT_CATEGORY,
        "Transporte",
    ]
    assert sum(Decimal(c["percentage"]) for c in categories) == Decimal("100.00")
    assert [c["percentage"] for c in categories] == ["33.34", "33.33", "33.33"]
    first = categories[0]
    assert set(first) == {
        "category_id",
        "category_name",
        "total",
        "count",
        "mean",
        "median",
        "percentage",
    }
    assert first == {
        "category_id": food,
        "category_name": "Alimentação",
        "total": "10.00",
        "count": 1,
        "mean": "10.00",
        "median": "10.00",
        "percentage": "33.34",
    }


def test_categories_per_currency_and_period(client: TestClient) -> None:
    """SEA-24, SEA-54: período fechado e percentuais somando 100.00 por moeda."""
    _import(
        client,
        "2025-12-31,FORA,-99.00,M,BRL",
        "2026-01-01,A,-10.00,M,BRL",
        "2026-01-31,B,-20.00,M,USD",
        "2026-02-01,FORA2,-99.00,M,USD",
    )

    response = client.get(CATEGORIES, params={"start_date": "2026-01-01", "end_date": "2026-01-31"})

    assert response.status_code == 200
    groups = response.json()["currencies"]
    assert [(g["currency"], g["total"]) for g in groups] == [("BRL", "10.00"), ("USD", "20.00")]
    for group in groups:
        assert sum(Decimal(c["percentage"]) for c in group["categories"]) == Decimal("100.00")


def test_categories_mean_uses_half_up(client: TestClient) -> None:
    _import(client, "2026-01-05,A,-0.01,M,BRL", "2026-01-06,B,-0.04,M,BRL")

    category = _only_currency(client.get(CATEGORIES))["categories"][0]

    assert (category["total"], category["mean"], category["median"]) == ("0.05", "0.03", "0.03")
    assert category["percentage"] == "100.00"


# --- GET /analytics/monthly ----------------------------------------------------------


def test_monthly_fills_missing_month_with_zero(client: TestClient) -> None:
    """SEA-61, P-11: despesas em jan e mar → 3 meses, fevereiro com total 0.00."""
    food = _category(client, "Alimentação")
    _rule(client, "MERCADO", food)
    _import(
        client,
        "2026-01-10,MERCADO,-10.00,M,BRL",
        "2026-01-11,OUTRA,-5.50,O,BRL",
        "2026-03-15,MERCADO,-20.00,M,BRL",
    )

    response = client.get(MONTHLY, params={"start_date": "2026-01-01", "end_date": "2026-03-31"})

    group = _only_currency(response)
    assert set(group) == {"currency", "months"}
    months = group["months"]
    assert [m["month"] for m in months] == ["2026-01", "2026-02", "2026-03"]
    assert [(m["total"], m["count"]) for m in months] == [("15.50", 2), ("0.00", 0), ("20.00", 1)]
    assert months[1]["by_category"] == []
    assert months[0]["by_category"] == [
        {"category_id": food, "category_name": "Alimentação", "total": "10.00", "count": 1},
        {
            "category_id": months[0]["by_category"][1]["category_id"],
            "category_name": DEFAULT_CATEGORY,
            "total": "5.50",
            "count": 1,
        },
    ]


def test_monthly_separates_currencies(client: TestClient) -> None:
    """SEA-54: mesmo intervalo de meses para todas as moedas, sem somar entre elas."""
    _import(client, "2026-01-10,A,-10.00,M,USD", "2026-02-10,B,-20.00,M,BRL")

    response = client.get(MONTHLY)

    assert response.status_code == 200
    groups = response.json()["currencies"]
    assert [g["currency"] for g in groups] == ["BRL", "USD"]
    assert [[m["total"] for m in g["months"]] for g in groups] == [
        ["0.00", "20.00"],
        ["10.00", "0.00"],
    ]


# --- Vazio, período e entrada inválida (todas as rotas) -------------------------------


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_empty_database_returns_no_currencies(client: TestClient, route: str) -> None:
    """SEA-95: sem despesas → 200 `{"currencies": []}`; receita não conta como despesa."""
    assert client.get(route).json() == {"currencies": []}

    _import(client, "2026-01-08,SALARIO,3000.00,Empresa,BRL")
    response = client.get(route)

    assert response.status_code == 200
    assert response.json() == {"currencies": []}


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_inverted_period_returns_invalid_period(client: TestClient, route: str) -> None:
    response = client.get(route, params={"start_date": "2026-03-01", "end_date": "2026-01-01"})

    assert response.status_code == 422, response.text
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == "INVALID_PERIOD"


@pytest.mark.parametrize("route", ALL_ROUTES)
@pytest.mark.parametrize("value", ["2026-13-01", "abc", "2026-02-30", "", "9" * 5000])
def test_invalid_date_returns_validation_error(client: TestClient, route: str, value: str) -> None:
    _assert_validation_error(client.get(route, params={"start_date": value}), "query.start_date")


@pytest.mark.parametrize("route", ALL_ROUTES)
def test_extreme_dates_never_return_500(client: TestClient, route: str) -> None:
    """Período de 0001-01-01 a 9999-12-31 é válido e não pode quebrar a série mensal."""
    _import(client, *THREE_EXPENSES)

    response = client.get(route, params={"start_date": "2026-01-01", "end_date": "9999-12-31"})

    assert response.status_code == 200, response.text
    ancient = client.get(route, params={"start_date": "0001-01-01", "end_date": "0001-01-01"})
    assert ancient.status_code == 200, ancient.text
    assert ancient.json() == {"currencies": []}


def test_same_day_period_is_inclusive(client: TestClient) -> None:
    """SEA-24: intervalo fechado nos dois lados."""
    _import(client, *THREE_EXPENSES)

    response = client.get(SUMMARY, params={"start_date": "2026-01-06", "end_date": "2026-01-06"})

    assert _only_currency(response)["total"] == "20.00"


# --- AS-3 / AS-6 ----------------------------------------------------------------------


def test_database_unavailable_returns_503_without_internals(
    isolated_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    """AS-3: SQL, parâmetros e merchant não vazam no corpo nem no log."""
    leaked = f"SELECT * FROM transactions WHERE merchant = '{SECRET}'"

    def fail() -> NoReturn:
        raise OperationalError(leaked, {"merchant": SECRET}, Exception())

    class FailingAnalyticsService:
        def summary(self, filters: ExpenseFilters) -> list[CurrencySummary]:
            fail()

        def categories(self, period: Period) -> list[CurrencyCategories]:
            fail()

        def monthly(self, period: Period) -> list[CurrencySeries]:
            fail()

    isolated_app.dependency_overrides[get_analytics_service] = FailingAnalyticsService
    caplog.set_level(logging.DEBUG)

    with TestClient(isolated_app, raise_server_exceptions=False) as test_client:
        responses = [
            test_client.get(SUMMARY, params={"merchant": SECRET}),
            test_client.get(CATEGORIES),
            test_client.get(MONTHLY),
        ]

    for response in responses:
        assert response.status_code == 503
        body = response.json()
        assert set(body) == ERROR_KEYS
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert SECRET not in response.text
        assert "SELECT" not in response.text
    assert SECRET not in caplog.text
    assert "SELECT" not in caplog.text


def test_openapi_documents_routes_error_responses_and_no_security(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    expected_params = {
        SUMMARY: {"start_date", "end_date", "category_id", "merchant"},
        CATEGORIES: {"start_date", "end_date"},
        MONTHLY: {"start_date", "end_date"},
    }

    for route, params in expected_params.items():
        assert set(paths[route]) == {"get"}
        operation = paths[route]["get"]
        assert {p["name"] for p in operation["parameters"]} == params
        assert "200" in operation["responses"]
        for status in ("422", "503"):
            ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ErrorResponse")
        assert "security" not in operation
    assert "securitySchemes" not in schema.get("components", {})

"""Testes de integração de `/transactions` (TASK-025; contrato 8.1; AS-6).

Requisitos: SEA-11, SEA-12, SEA-13, SEA-35, SEA-40, SEA-63, SEA-67, SEA-68, SEA-93, SEA-94.
Entrada adversarial (lições das ondas 8 a 11): nenhum parâmetro gera 500.
"""

import logging
import threading
from collections.abc import Iterator
from typing import Any, NoReturn

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from starlette.types import ASGIApp

from app.api.routers.transactions import get_recategorization_service, get_transaction_service
from app.application.services.recategorization_service import RecategorizationResult
from app.core.config import Settings
from app.domain.entities import Page, PageResult, Transaction, TransactionFilters
from app.main import create_app

BASE = "/transactions"
HEADER = "date,description,amount,merchant,currency"
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1  # `id`, `category_id`, `import_id` BIGINT
MERCHANT_FILTER_MAX_LENGTH = 1000
MISSING_ID = 999_999
DEFAULT_CATEGORY = "Não categorizada"
SECRET = "LOJA SIGILOSA 4242"
TRANSACTION_KEYS = {
    "id",
    "date",
    "description",
    "merchant",
    "amount",
    "currency",
    "type",
    "category",
    "import_id",
}
ERROR_KEYS = {"code", "message", "details", "error_id"}
NOT_FOUND_BODY = {
    "code": "TRANSACTION_NOT_FOUND",
    "message": "Transação não encontrada.",
    "details": None,
    "error_id": None,
}
THREE_LINES = (
    "2024-01-05,UBER TRIP,-25.50,Uber,BRL",
    "2024-01-06,PADARIA CENTRAL,-12.00,Padaria,BRL",
    "2024-01-07,SALARIO,3000.00,Empresa,BRL",
)


def _csv(*lines: str) -> bytes:
    return ("\n".join([HEADER, *lines]) + "\n").encode("utf-8")


def _import(client: TestClient, *lines: str, filename: str = "extrato.csv") -> int:
    response = client.post("/imports", files={"file": (filename, _csv(*lines), "text/csv")})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _category(client: TestClient, name: str) -> int:
    response = client.post("/categories", json={"name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _rule(client: TestClient, keyword: str, category_id: int, priority: int = 1) -> int:
    response = client.post(
        "/categorization-rules",
        json={"keyword": keyword, "category_id": category_id, "priority": priority},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _no_auth_header(response: Any) -> bool:
    return "authorization" not in {name.lower() for name in response.request.headers}


def _assert_validation_error(response: Any, field: str) -> None:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert field in [detail["field"] for detail in body["details"]]


def _assert_invalid_pagination(response: Any) -> None:
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "INVALID_PAGINATION"


def _descriptions(response: Any) -> list[str]:
    return [item["description"] for item in response.json()["items"]]


def _categories_by_description(engine: Engine) -> dict[str, str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.description, c.name FROM transactions t "
                "JOIN categories c ON c.id = t.category_id"
            )
        ).all()
    return {description: name for description, name in rows}


@pytest.fixture
def isolated_app(settings: Settings) -> Iterator[FastAPI]:
    app = create_app(settings)
    yield app
    app.dependency_overrides.clear()


# --- GET /transactions: caminho feliz ------------------------------------------------


def test_list_after_import_returns_three_items_with_all_fields(client: TestClient) -> None:
    """SEA-11, SEA-40: tipo, moeda, categoria e import de cada item."""
    import_id = _import(client, *THREE_LINES)

    response = client.get(BASE)

    assert response.status_code == 200
    assert _no_auth_header(response)  # SEA-35
    body = response.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert (body["total"], body["limit"], body["offset"]) == (3, 50, 0)
    assert len(body["items"]) == 3
    for item in body["items"]:
        assert set(item) == TRANSACTION_KEYS
        assert item["currency"] == "BRL"
        assert item["category"]["name"] == DEFAULT_CATEGORY
        assert isinstance(item["category"]["id"], int)
        assert item["import_id"] == import_id
    salary = next(i for i in body["items"] if i["description"] == "SALARIO")
    assert salary["type"] == "receita"
    assert salary["amount"] == "3000.00"
    uber = next(i for i in body["items"] if i["description"] == "UBER TRIP")
    assert uber["type"] == "despesa"
    assert uber["amount"] == "-25.50"
    assert uber["merchant"] == "Uber"
    assert uber["date"] == "2024-01-05"


def test_list_is_ordered_by_date_desc_then_id_desc(client: TestClient) -> None:
    _import(
        client,
        "2024-01-05,A,-1.00,M,BRL",
        "2024-01-07,B,-1.00,M,BRL",
        "2024-01-05,C,-1.00,M,BRL",
    )

    assert _descriptions(client.get(BASE)) == ["B", "C", "A"]


def test_empty_database_returns_empty_page(client: TestClient) -> None:
    response = client.get(BASE)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_pagination_slices_items_and_keeps_total(client: TestClient) -> None:
    _import(client, *(f"2024-02-{d:02d},D{d},-1.00,M,BRL" for d in range(1, 6)))

    response = client.get(BASE, params={"limit": 2, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["limit"], body["offset"]) == (5, 2, 1)
    assert _descriptions(response) == ["D4", "D3"]


def test_limit_500_and_offset_beyond_total_are_accepted(client: TestClient) -> None:
    _import(client, *THREE_LINES)

    assert client.get(BASE, params={"limit": 500}).json()["total"] == 3
    beyond = client.get(BASE, params={"offset": 10})
    assert beyond.status_code == 200
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == 3


# --- GET /transactions: filtros ------------------------------------------------------


def test_start_date_and_merchant_combined_return_only_matching(client: TestClient) -> None:
    """SEA-68: filtros combinados com E lógico."""
    _import(
        client,
        "2024-01-05,UBER ANTIGO,-10.00,Uber,BRL",
        "2024-03-05,UBER NOVO,-20.00,Uber,BRL",
        "2024-03-06,PADARIA NOVA,-5.00,Padaria,BRL",
    )

    response = client.get(BASE, params={"start_date": "2024-02-01", "merchant": "Uber"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert _descriptions(response) == ["UBER NOVO"]


def test_merchant_filter_ignores_case_and_extra_spaces(client: TestClient) -> None:
    """P-09: igualdade sem caixa, após normalizar espaços (inclusive tab interno)."""
    _import(
        client,
        "2024-01-05,A,-1.00,Uber Eats,BRL",
        "2024-01-06,B,-1.00,Uber,BRL",
    )

    for value in ("  uBER   eats ", "uber\teats"):
        response = client.get(BASE, params={"merchant": value})
        assert response.status_code == 200, value
        assert _descriptions(response) == ["A"]


def test_period_filters_are_inclusive_and_open_ended(client: TestClient) -> None:
    """SEA-13, P-10."""
    _import(
        client,
        "2024-01-01,JAN,-1.00,M,BRL",
        "2024-02-01,FEV,-1.00,M,BRL",
        "2024-03-01,MAR,-1.00,M,BRL",
    )

    assert _descriptions(client.get(BASE, params={"end_date": "2024-02-01"})) == ["FEV", "JAN"]
    both = client.get(BASE, params={"start_date": "2024-02-01", "end_date": "2024-02-01"})
    assert _descriptions(both) == ["FEV"]


def test_category_and_import_filters(client: TestClient) -> None:
    """SEA-67, SEA-94."""
    transport = _category(client, "Transporte")
    _rule(client, "uber", transport)
    first = _import(client, "2024-01-05,UBER TRIP,-25.50,Uber,BRL", filename="a.csv")
    second = _import(client, "2024-01-06,PADARIA,-12.00,Padaria,BRL", filename="b.csv")

    by_category = client.get(BASE, params={"category_id": transport})
    assert _descriptions(by_category) == ["UBER TRIP"]
    assert by_category.json()["items"][0]["category"] == {"id": transport, "name": "Transporte"}
    assert _descriptions(client.get(BASE, params={"import_id": first})) == ["UBER TRIP"]
    assert _descriptions(client.get(BASE, params={"import_id": second})) == ["PADARIA"]
    combined = client.get(BASE, params={"import_id": second, "category_id": transport})
    assert combined.json()["total"] == 0


@pytest.mark.parametrize("param", ["category_id", "import_id"])
@pytest.mark.parametrize("value", [MISSING_ID, INT64_MAX, INT64_MIN, 0, -1])
def test_unknown_ids_in_filters_return_empty_page(
    client: TestClient, param: str, value: int
) -> None:
    """SEA-101: id inexistente (dentro do BIGINT) no filtro → 200 vazio."""
    _import(client, *THREE_LINES)

    response = client.get(BASE, params={param: value})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


@pytest.mark.parametrize("param", ["category_id", "import_id"])
@pytest.mark.parametrize(
    "value", [str(INT64_MAX + 1), str(INT64_MIN - 1), "9" * 5000, "abc", "1.5", "", "1e3"]
)
def test_invalid_or_out_of_range_ids_in_filters_return_422(
    client: TestClient, param: str, value: str
) -> None:
    _assert_validation_error(client.get(BASE, params={param: value}), f"query.{param}")


def test_inverted_period_returns_invalid_period(client: TestClient) -> None:
    response = client.get(BASE, params={"start_date": "2024-02-01", "end_date": "2024-01-01"})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PERIOD"


@pytest.mark.parametrize("param", ["start_date", "end_date"])
@pytest.mark.parametrize("value", ["2024-13-01", "abc", "2024-02-30", "", "9" * 5000])
def test_invalid_dates_return_422_validation_error(
    client: TestClient, param: str, value: str
) -> None:
    _assert_validation_error(client.get(BASE, params={param: value}), f"query.{param}")


# --- GET /transactions: merchant adversarial -----------------------------------------


@pytest.mark.parametrize(
    "value",
    ["Uber\x00", "\x00", "Ub\x07er", "Uber\x7f", "Uber\x80", "Uber\x9f", "Uber\x1b[31m"],
)
def test_merchant_with_control_char_or_surrogate_returns_422(
    client: TestClient, value: str, caplog: pytest.LogCaptureFixture
) -> None:
    """NUL faria o PostgreSQL recusar com DataError (500)."""
    _import(client, *THREE_LINES)
    caplog.set_level(logging.DEBUG)

    response = client.get(BASE, params={"merchant": value})

    _assert_validation_error(response, "query.merchant")
    assert "Uber" not in response.text
    # O httpx do TestClient loga a URL do lado do cliente; só os logs da app importam.
    app_logs = [r.getMessage() for r in caplog.records if not r.name.startswith("httpx")]
    assert not any("Uber" in message for message in app_logs)


def test_merchant_with_whitespace_control_chars_is_normalized(client: TestClient) -> None:
    """Cc de espaço (tab, NEL U+0085...) colapsam na normalização, como na keyword."""
    _import(client, *THREE_LINES)

    for value in ("Uber\x85", "\tUber\r\n", "\x1cUber\x1f"):
        response = client.get(BASE, params={"merchant": value})
        assert response.status_code == 200, repr(value)
        assert _descriptions(response) == ["UBER TRIP"]


@pytest.mark.parametrize("raw", ["Uber%00", "%00", "Uber%ED%A0%80", "%FF%FE", "Uber%C0%80"])
def test_merchant_with_raw_percent_encoded_bytes_never_returns_500(
    client: TestClient, raw: str
) -> None:
    """NUL cru é recusado; bytes que não são UTF-8 válido nunca chegam ao banco como erro."""
    response = client.get(f"{BASE}?merchant={raw}")

    assert response.status_code in (200, 422), response.text
    if "%00" in raw:
        _assert_validation_error(response, "query.merchant")


@pytest.mark.parametrize("value", ["", " ", "   ", "\t\n", "\x1c\x1d\x1e\x1f", "  "])
def test_blank_merchant_returns_422(client: TestClient, value: str) -> None:
    """Decisão: merchant vazio após normalizar é filtro inválido (422), não "ausente"."""
    _import(client, *THREE_LINES)

    _assert_validation_error(client.get(BASE, params={"merchant": value}), "query.merchant")


def test_merchant_length_limit_measured_after_normalization(client: TestClient) -> None:
    long_merchant = "M" * MERCHANT_FILTER_MAX_LENGTH
    _import(client, f"2024-01-05,LONGA,-1.00,{long_merchant},BRL")

    at_limit = client.get(BASE, params={"merchant": f"   {long_merchant}   "})
    assert at_limit.status_code == 200
    assert _descriptions(at_limit) == ["LONGA"]

    over = client.get(BASE, params={"merchant": long_merchant + "M"})
    _assert_validation_error(over, "query.merchant")


def test_merchant_without_match_returns_empty_page(client: TestClient) -> None:
    _import(client, *THREE_LINES)

    response = client.get(BASE, params={"merchant": "%' OR '1'='1"})

    assert response.status_code == 200
    assert response.json()["total"] == 0


# --- GET /transactions: paginação adversarial ----------------------------------------


@pytest.mark.parametrize(
    "params",
    [{"limit": 501}, {"limit": 0}, {"limit": -1}, {"offset": -1}, {"limit": INT64_MAX + 1}],
)
def test_out_of_range_pagination_returns_invalid_pagination(
    client: TestClient, params: dict[str, Any]
) -> None:
    """SEA-105."""
    _assert_invalid_pagination(client.get(BASE, params=params))


@pytest.mark.parametrize("value", [str(INT64_MAX + 1), "9" * 5000])
def test_offset_beyond_bigint_returns_422_validation_error(client: TestClient, value: str) -> None:
    """OFFSET é BIGINT no PostgreSQL: acima disso o banco quebraria (500)."""
    _assert_validation_error(client.get(BASE, params={"offset": value}), "query.offset")


def test_offset_at_bigint_max_is_accepted(client: TestClient) -> None:
    _import(client, *THREE_LINES)

    response = client.get(BASE, params={"offset": INT64_MAX})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 3


@pytest.mark.parametrize("param", ["limit", "offset"])
@pytest.mark.parametrize("value", ["abc", "1.5", "", "1e2", "9" * 5000])
def test_non_integer_pagination_returns_422_validation_error(
    client: TestClient, param: str, value: str
) -> None:
    _assert_validation_error(client.get(BASE, params={param: value}), f"query.{param}")


# --- GET /transactions/{transaction_id} ----------------------------------------------


def test_get_by_id_returns_transaction_out(client: TestClient) -> None:
    """SEA-12."""
    _import(client, *THREE_LINES)
    listed = client.get(BASE).json()["items"][0]

    response = client.get(f"{BASE}/{listed['id']}")

    assert response.status_code == 200
    assert _no_auth_header(response)
    assert response.json() == listed


@pytest.mark.parametrize("transaction_id", [MISSING_ID, INT64_MAX, INT64_MIN, 0, -1])
def test_get_unknown_id_returns_404(client: TestClient, transaction_id: int) -> None:
    """SEA-93: id dentro do BIGINT e inexistente."""
    response = client.get(f"{BASE}/{transaction_id}")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


@pytest.mark.parametrize(
    "raw_id",
    [
        "abc",
        "1.5",
        "1e3",
        str(INT64_MAX + 1),
        str(INT64_MIN - 1),
        "9" * 5000,
        "%00",
        "recategorize",
    ],
)
def test_get_invalid_path_id_returns_422_validation_error(client: TestClient, raw_id: str) -> None:
    _assert_validation_error(client.get(f"{BASE}/{raw_id}"), "path.transaction_id")


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_no_manual_update_or_delete_endpoint(client: TestClient, method: str) -> None:
    """Fora de escopo: alteração manual de categoria."""
    _import(client, *THREE_LINES)
    transaction_id = client.get(BASE).json()["items"][0]["id"]

    for url in (BASE, f"{BASE}/{transaction_id}"):
        response = client.request(method, url, json={"category_id": 1})
        assert response.status_code == 405, (method, url)
        assert response.json()["code"] == "METHOD_NOT_ALLOWED"


def test_post_to_collection_is_not_allowed(client: TestClient) -> None:
    response = client.post(BASE, json={})

    assert response.status_code == 405


# --- POST /transactions/recategorize -------------------------------------------------


def test_recategorize_empty_database_returns_zero_counts(client: TestClient) -> None:
    """SEA-109, SEA-35."""
    response = client.post(f"{BASE}/recategorize")

    assert response.status_code == 200
    assert _no_auth_header(response)
    assert response.json() == {"evaluated": 0, "changed": 0}


def test_recategorize_applies_new_rules_and_is_idempotent(
    client: TestClient, engine: Engine
) -> None:
    """SEA-63, SEA-66."""
    _import(client, *THREE_LINES)
    transport = _category(client, "Transporte")
    _rule(client, "uber", transport)

    first = client.post(f"{BASE}/recategorize")

    assert first.status_code == 200
    assert first.json() == {"evaluated": 3, "changed": 1}
    categories = _categories_by_description(engine)
    assert categories["UBER TRIP"] == "Transporte"
    assert categories["PADARIA CENTRAL"] == DEFAULT_CATEGORY
    listed = client.get(BASE, params={"category_id": transport})
    assert _descriptions(listed) == ["UBER TRIP"]

    second = client.post(f"{BASE}/recategorize")
    assert second.json() == {"evaluated": 3, "changed": 0}


def test_recategorize_ignores_body_and_query(client: TestClient) -> None:
    _import(client, *THREE_LINES)

    response = client.post(f"{BASE}/recategorize?x=1", json={"evaluated": 99})

    assert response.status_code == 200
    assert response.json() == {"evaluated": 3, "changed": 0}


def test_get_on_recategorize_path_is_not_the_action(client: TestClient) -> None:
    """GET não dispara a recategorização: cai na rota por id e falha na validação."""
    _assert_validation_error(client.get(f"{BASE}/recategorize"), "path.transaction_id")


# --- concorrência ---------------------------------------------------------------------

RACE_ROUNDS = 10


def _race(app: ASGIApp, requests: list[tuple[str, str]]) -> list[Any]:
    """Dispara as requisições ao mesmo tempo, cada uma na sua thread e no seu client."""
    barrier = threading.Barrier(len(requests))
    results: list[Any] = [None] * len(requests)

    def go(index: int, method: str, url: str) -> None:
        worker = TestClient(app, raise_server_exceptions=False)
        barrier.wait()
        results[index] = worker.request(method, url)

    threads = [
        threading.Thread(target=go, args=(index, *request))
        for index, request in enumerate(requests)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_concurrent_recategorizations_never_return_500(client: TestClient, engine: Engine) -> None:
    lines = [f"2024-01-{d:02d},UBER {d},-{10 + d}.00,Uber,BRL" for d in range(1, 21)]
    lines += [f"2024-02-{d:02d},PADARIA {d},-{5 + d}.00,Padaria,BRL" for d in range(1, 21)]
    _import(client, *lines)
    transport = _category(client, "Transporte")
    food = _category(client, "Alimentação")
    rule_id = _rule(client, "uber", transport)
    _rule(client, "padaria", food)
    url = f"{BASE}/recategorize"

    for round_number in range(RACE_ROUNDS):
        # Alterna a categoria da regra "uber" para sempre haver o que mudar.
        target = food if round_number % 2 else transport
        updated = client.put(
            f"/categorization-rules/{rule_id}",
            json={"keyword": "uber", "category_id": target, "priority": 1},
        )
        assert updated.status_code == 200

        responses = _race(client.app, [("POST", url), ("POST", url), ("GET", BASE)])

        for response in responses:
            assert response.status_code == 200, response.text
        for response in responses[:2]:
            assert response.json()["evaluated"] == 40
        expected = "Alimentação" if target == food else "Transporte"
        categories = _categories_by_description(engine)
        assert {categories[f"UBER {d}"] for d in range(1, 21)} == {expected}
        assert {categories[f"PADARIA {d}"] for d in range(1, 21)} == {"Alimentação"}

    assert client.post(url).json() == {"evaluated": 40, "changed": 0}


# --- AS-3 / AS-6 ----------------------------------------------------------------------


def test_database_unavailable_returns_503_without_internals(
    isolated_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    """AS-3: SQL, parâmetros e merchant não vazam no corpo nem no log."""
    leaked = f"SELECT * FROM transactions WHERE merchant = '{SECRET}'"

    def fail() -> NoReturn:
        raise OperationalError(leaked, {"merchant": SECRET}, Exception())

    class FailingTransactionService:
        def get(self, transaction_id: int) -> Transaction:
            fail()

        def list(self, filters: TransactionFilters, page: Page) -> PageResult[Transaction]:
            fail()

    class FailingRecategorizationService:
        def recategorize(self) -> RecategorizationResult:
            fail()

    isolated_app.dependency_overrides[get_transaction_service] = FailingTransactionService
    isolated_app.dependency_overrides[get_recategorization_service] = FailingRecategorizationService
    caplog.set_level(logging.DEBUG)

    with TestClient(isolated_app, raise_server_exceptions=False) as test_client:
        responses = [
            test_client.get(BASE, params={"merchant": SECRET}),
            test_client.get(f"{BASE}/1"),
            test_client.post(f"{BASE}/recategorize"),
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
    collection = paths[BASE]
    item = paths[f"{BASE}/{{transaction_id}}"]
    action = paths[f"{BASE}/recategorize"]

    assert set(collection) == {"get"}
    assert set(item) == {"get"}
    assert set(action) == {"post"}
    params = {p["name"] for p in collection["get"]["parameters"]}
    assert params == {
        "start_date",
        "end_date",
        "category_id",
        "merchant",
        "import_id",
        "limit",
        "offset",
    }
    expected = [
        (collection["get"], ["422", "503"]),
        (item["get"], ["404", "422", "503"]),
        (action["post"], ["503"]),
    ]
    for operation, errors in expected:
        assert "200" in operation["responses"]
        for status in errors:
            ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ErrorResponse")
        assert "security" not in operation
    assert "securitySchemes" not in schema.get("components", {})

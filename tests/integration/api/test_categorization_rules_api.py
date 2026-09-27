"""Testes de integração de `/categorization-rules` (TASK-027; contrato 8.1; AS-6).

Requisitos: SEA-18, SEA-35, SEA-48, SEA-49, SEA-50, SEA-64.
"""

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Any, NoReturn

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from app.api.routers.categorization_rules import get_categorization_rule_service
from app.core.config import Settings
from app.domain.entities import CategorizationRule
from app.main import create_app

BASE = "/categorization-rules"
KEYWORD_MAX_LENGTH = 200  # `categorization_rules.keyword VARCHAR(200)`
INT32_MIN, INT32_MAX = -(2**31), 2**31 - 1  # `priority INTEGER`
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1  # `id` e `category_id` BIGINT
MISSING_ID = 999_999
SECRET = "PALAVRA SIGILOSA 4242"
RULE_KEYS = {"id", "keyword", "category_id", "priority", "created_at"}
RULE_NOT_FOUND_BODY = {
    "code": "RULE_NOT_FOUND",
    "message": "Regra de categorização não encontrada.",
    "details": None,
    "error_id": None,
}
RULE_CATEGORY_NOT_FOUND_BODY = {
    "code": "RULE_CATEGORY_NOT_FOUND",
    "message": "Categoria informada na regra não existe.",
    "details": None,
    "error_id": None,
}
CSV = (
    b"date,description,amount,merchant,currency\n"
    b"2024-01-05,UBER TRIP,-25.50,Uber,BRL\n"
    b"2024-01-06,PADARIA CENTRAL,-12.00,Padaria,BRL\n"
)


def _count_rules(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM categorization_rules")).scalar_one())


def _stored_rule(engine: Engine, rule_id: int) -> tuple[str, int, int]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT keyword, category_id, priority FROM categorization_rules WHERE id = :id"),
            {"id": rule_id},
        ).one()
    return (row.keyword, row.category_id, row.priority)


def _no_auth_header(response: Any) -> bool:
    return "authorization" not in {name.lower() for name in response.request.headers}


def _category(client: TestClient, name: str = "Transporte") -> int:
    response = client.post("/categories", json={"name": name})
    assert response.status_code == 201
    return int(response.json()["id"])


def _rule(client: TestClient, category_id: int, keyword: str = "uber", priority: int = 10) -> int:
    response = client.post(
        BASE, json={"keyword": keyword, "category_id": category_id, "priority": priority}
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def _assert_validation_error(response: Any, field: str) -> None:
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert field in [detail["field"] for detail in body["details"]]


@pytest.fixture
def isolated_app(settings: Settings) -> Iterator[FastAPI]:
    app = create_app(settings)
    yield app
    app.dependency_overrides.clear()


# --- ciclo completo e leitura -------------------------------------------------------


def test_full_cycle_post_get_put_delete_then_404(client: TestClient, engine: Engine) -> None:
    category_id = _category(client)

    created = client.post(
        BASE, json={"keyword": "  uber   trip ", "category_id": category_id, "priority": 10}
    )
    assert created.status_code == 201
    assert _no_auth_header(created)  # SEA-35
    body = created.json()
    assert set(body) == RULE_KEYS
    assert body["keyword"] == "uber trip"
    assert body["category_id"] == category_id
    assert body["priority"] == 10
    datetime.fromisoformat(body["created_at"])
    rule_id = body["id"]

    fetched = client.get(f"{BASE}/{rule_id}")
    assert fetched.status_code == 200
    assert fetched.json() == body

    updated = client.put(
        f"{BASE}/{rule_id}",
        json={"keyword": "uber trip", "category_id": category_id, "priority": -5},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == -5
    assert updated.json()["id"] == rule_id
    assert _stored_rule(engine, rule_id) == ("uber trip", category_id, -5)

    deleted = client.delete(f"{BASE}/{rule_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    gone = client.get(f"{BASE}/{rule_id}")
    assert gone.status_code == 404
    assert gone.json() == RULE_NOT_FOUND_BODY
    assert _count_rules(engine) == 0


def test_put_changes_keyword_and_category(client: TestClient, engine: Engine) -> None:
    first = _category(client, "Transporte")
    second = _category(client, "Alimentação")
    rule_id = _rule(client, first)

    response = client.put(
        f"{BASE}/{rule_id}", json={"keyword": "ifood", "category_id": second, "priority": 3}
    )

    assert response.status_code == 200
    assert _stored_rule(engine, rule_id) == ("ifood", second, 3)


def test_get_list_empty_then_ordered_by_priority_created_at_id(client: TestClient) -> None:
    empty = client.get(BASE)
    assert empty.status_code == 200
    assert empty.json() == []
    assert _no_auth_header(empty)

    category_id = _category(client)
    low = _rule(client, category_id, "a", priority=5)
    high = _rule(client, category_id, "b", priority=1)
    tie = _rule(client, category_id, "c", priority=5)

    response = client.get(BASE)

    assert response.status_code == 200
    items = response.json()
    assert all(set(item) == RULE_KEYS for item in items)
    assert [item["id"] for item in items] == [high, low, tie]


def test_priority_accepts_integer_column_limits(client: TestClient) -> None:
    category_id = _category(client)

    for priority in (INT32_MIN, INT32_MAX, 0):
        response = client.post(
            BASE, json={"keyword": "x", "category_id": category_id, "priority": priority}
        )
        assert response.status_code == 201
        assert response.json()["priority"] == priority


# --- keyword (SEA-50) ---------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword",
    ["  ", "", "\t\n ", "  "],
    ids=["only-spaces", "empty", "whitespace-mix", "unicode-spaces"],
)
def test_post_blank_keyword_returns_422_validation_error(
    client: TestClient, engine: Engine, keyword: str
) -> None:
    category_id = _category(client)

    response = client.post(
        BASE, json={"keyword": keyword, "category_id": category_id, "priority": 1}
    )

    _assert_validation_error(response, "body.keyword")
    assert _count_rules(engine) == 0


@pytest.mark.parametrize(
    "keyword", [None, 123, ["uber"], True], ids=["null", "int", "list", "bool"]
)
def test_post_non_string_keyword_returns_422(
    client: TestClient, engine: Engine, keyword: Any
) -> None:
    category_id = _category(client)

    response = client.post(
        BASE, json={"keyword": keyword, "category_id": category_id, "priority": 1}
    )

    _assert_validation_error(response, "body.keyword")
    assert _count_rules(engine) == 0


def test_post_missing_keyword_returns_422(client: TestClient, engine: Engine) -> None:
    category_id = _category(client)

    response = client.post(BASE, json={"category_id": category_id, "priority": 1})

    _assert_validation_error(response, "body.keyword")
    assert _count_rules(engine) == 0


@pytest.mark.parametrize(
    "keyword",
    ["ub\u0000er", "\u0000", "ub\u0007er", "uber\u007f", "ub\u009ber"],
    ids=["nul-inside", "nul-only", "bell", "del", "c1-csi"],
)
def test_post_keyword_with_control_char_returns_422(
    client: TestClient, engine: Engine, keyword: str
) -> None:
    # Lição TASK-026-1: o PostgreSQL recusa NUL em texto (DataError -> 500).
    category_id = _category(client)

    response = client.post(
        BASE, json={"keyword": keyword, "category_id": category_id, "priority": 1}
    )

    _assert_validation_error(response, "body.keyword")
    assert "\u0000" not in response.text
    assert _count_rules(engine) == 0


def test_post_keyword_with_lone_surrogate_returns_422(client: TestClient, engine: Engine) -> None:
    # JSON aceita `\ud800` sozinho, mas não há UTF-8 para ele: o driver quebraria (500).
    category_id = _category(client)
    raw = f'{{"keyword": "ub\\ud800er", "category_id": {category_id}, "priority": 1}}'

    response = client.post(BASE, content=raw.encode(), headers={"Content-Type": "application/json"})

    _assert_validation_error(response, "body.keyword")
    assert _count_rules(engine) == 0


# Achado TASK-027-1: U+001C..U+001F não são White_Space para o `strip_whitespace` do
# pydantic-core, mas `str.split()` os descarta. Só deles, a keyword normalizada fica vazia
# e o serviço levantaria `ValueError` (500).
SEPARATOR_ONLY_KEYWORDS = ["\x1c", "\x1f", "\x1d \x1e", "\x1c\x1d\x1e\x1f", " \x1f\t"]
SEPARATOR_ONLY_IDS = ["fs", "us", "gs-space-rs", "all-four", "mixed-spaces"]


@pytest.mark.parametrize("keyword", SEPARATOR_ONLY_KEYWORDS, ids=SEPARATOR_ONLY_IDS)
def test_post_separator_only_keyword_returns_422(
    client: TestClient, engine: Engine, keyword: str
) -> None:
    category_id = _category(client)

    response = client.post(
        BASE, json={"keyword": keyword, "category_id": category_id, "priority": 1}
    )

    _assert_validation_error(response, "body.keyword")
    assert _count_rules(engine) == 0


@pytest.mark.parametrize("keyword", SEPARATOR_ONLY_KEYWORDS, ids=SEPARATOR_ONLY_IDS)
def test_put_separator_only_keyword_returns_422_and_keeps_rule(
    client: TestClient, engine: Engine, keyword: str
) -> None:
    category_id = _category(client)
    rule_id = _rule(client, category_id, "uber", priority=10)

    response = client.put(
        f"{BASE}/{rule_id}", json={"keyword": keyword, "category_id": category_id, "priority": 2}
    )

    _assert_validation_error(response, "body.keyword")
    assert _stored_rule(engine, rule_id) == ("uber", category_id, 10)


def test_keyword_with_inner_separator_is_normalized(client: TestClient) -> None:
    category_id = _category(client)

    response = client.post(
        BASE, json={"keyword": "\x1ca\x1cb\x1f", "category_id": category_id, "priority": 1}
    )

    assert response.status_code == 201
    assert response.json()["keyword"] == "a b"


def test_keyword_length_is_measured_after_normalization(client: TestClient) -> None:
    category_id = _category(client)
    padded = "a" + " " * 300 + "b"  # 302 brutos, 3 normalizados

    accepted = client.post(
        BASE, json={"keyword": padded, "category_id": category_id, "priority": 1}
    )

    assert accepted.status_code == 201
    assert accepted.json()["keyword"] == "a b"


def test_keyword_inner_tab_and_newline_are_normalized(client: TestClient) -> None:
    category_id = _category(client)

    response = client.post(
        BASE, json={"keyword": "padaria\t\ncentral\r\n", "category_id": category_id, "priority": 1}
    )

    assert response.status_code == 201
    assert response.json()["keyword"] == "padaria central"


def test_keyword_at_max_length_with_edge_spaces_is_accepted(client: TestClient) -> None:
    category_id = _category(client)
    keyword = "k" * KEYWORD_MAX_LENGTH

    response = client.post(
        BASE, json={"keyword": f"  {keyword}  ", "category_id": category_id, "priority": 1}
    )

    assert response.status_code == 201
    assert response.json()["keyword"] == keyword


def test_keyword_over_max_length_returns_422(client: TestClient, engine: Engine) -> None:
    category_id = _category(client)

    response = client.post(
        BASE,
        json={
            "keyword": "k" * (KEYWORD_MAX_LENGTH + 1),
            "category_id": category_id,
            "priority": 1,
        },
    )

    _assert_validation_error(response, "body.keyword")
    assert _count_rules(engine) == 0


def test_put_blank_keyword_returns_422_and_keeps_rule(client: TestClient, engine: Engine) -> None:
    category_id = _category(client)
    rule_id = _rule(client, category_id, "uber", priority=10)

    response = client.put(
        f"{BASE}/{rule_id}", json={"keyword": "  ", "category_id": category_id, "priority": 2}
    )

    _assert_validation_error(response, "body.keyword")
    assert _stored_rule(engine, rule_id) == ("uber", category_id, 10)


def test_put_control_char_keyword_returns_422_and_keeps_rule(
    client: TestClient, engine: Engine
) -> None:
    category_id = _category(client)
    rule_id = _rule(client, category_id, "uber", priority=10)

    response = client.put(
        f"{BASE}/{rule_id}",
        json={"keyword": "ub\u0000er", "category_id": category_id, "priority": 2},
    )

    _assert_validation_error(response, "body.keyword")
    assert _stored_rule(engine, rule_id) == ("uber", category_id, 10)


# --- priority (SEA-50, P-12) --------------------------------------------------------


@pytest.mark.parametrize(
    "priority",
    [1.5, "1", True, None, 1.0, INT32_MAX + 1, INT32_MIN - 1, 2**64, -(2**70)],
    ids=[
        "float",
        "string",
        "bool",
        "null",
        "integral-float",
        "int32-overflow",
        "int32-underflow",
        "huge",
        "huge-negative",
    ],
)
def test_post_invalid_priority_returns_422(
    client: TestClient, engine: Engine, priority: Any
) -> None:
    category_id = _category(client)

    response = client.post(
        BASE, json={"keyword": "uber", "category_id": category_id, "priority": priority}
    )

    _assert_validation_error(response, "body.priority")
    assert _count_rules(engine) == 0


def test_post_missing_priority_returns_422(client: TestClient, engine: Engine) -> None:
    category_id = _category(client)

    response = client.post(BASE, json={"keyword": "uber", "category_id": category_id})

    _assert_validation_error(response, "body.priority")
    assert _count_rules(engine) == 0


@pytest.mark.parametrize("priority", [1.5, "1", INT32_MAX + 1], ids=["float", "string", "overflow"])
def test_put_invalid_priority_returns_422_and_keeps_rule(
    client: TestClient, engine: Engine, priority: Any
) -> None:
    category_id = _category(client)
    rule_id = _rule(client, category_id, "uber", priority=10)

    response = client.put(
        f"{BASE}/{rule_id}",
        json={"keyword": "uber", "category_id": category_id, "priority": priority},
    )

    _assert_validation_error(response, "body.priority")
    assert _stored_rule(engine, rule_id) == ("uber", category_id, 10)


# --- category_id (SEA-18) -----------------------------------------------------------


@pytest.mark.parametrize("category_id", [MISSING_ID, 0, -1, INT64_MAX, INT64_MIN])
def test_post_unknown_category_returns_422_rule_category_not_found(
    client: TestClient, engine: Engine, category_id: int
) -> None:
    response = client.post(
        BASE, json={"keyword": "uber", "category_id": category_id, "priority": 1}
    )

    assert response.status_code == 422
    assert response.json() == RULE_CATEGORY_NOT_FOUND_BODY
    assert _count_rules(engine) == 0


@pytest.mark.parametrize(
    "category_id",
    [INT64_MAX + 1, INT64_MIN - 1, 10**30, None, "abc", 1.5],
    ids=["int64-overflow", "int64-underflow", "huge", "null", "string", "float"],
)
def test_post_invalid_category_id_returns_422_validation_error(
    client: TestClient, engine: Engine, category_id: Any
) -> None:
    response = client.post(
        BASE, json={"keyword": "uber", "category_id": category_id, "priority": 1}
    )

    _assert_validation_error(response, "body.category_id")
    assert _count_rules(engine) == 0


def test_post_missing_category_id_returns_422(client: TestClient, engine: Engine) -> None:
    response = client.post(BASE, json={"keyword": "uber", "priority": 1})

    _assert_validation_error(response, "body.category_id")
    assert _count_rules(engine) == 0


def test_put_unknown_category_returns_422_and_keeps_rule(
    client: TestClient, engine: Engine
) -> None:
    category_id = _category(client)
    rule_id = _rule(client, category_id, "uber", priority=10)

    response = client.put(
        f"{BASE}/{rule_id}", json={"keyword": "ifood", "category_id": MISSING_ID, "priority": 2}
    )

    assert response.status_code == 422
    assert response.json() == RULE_CATEGORY_NOT_FOUND_BODY
    assert _stored_rule(engine, rule_id) == ("uber", category_id, 10)


# --- id inexistente e id de path (SEA-49) ------------------------------------------


@pytest.mark.parametrize("rule_id", [MISSING_ID, 0, -1, INT64_MAX, INT64_MIN])
def test_get_put_delete_unknown_rule_returns_404(client: TestClient, rule_id: int) -> None:
    category_id = _category(client)
    payload = {"keyword": "uber", "category_id": category_id, "priority": 1}

    responses = [
        client.get(f"{BASE}/{rule_id}"),
        client.put(f"{BASE}/{rule_id}", json=payload),
        client.delete(f"{BASE}/{rule_id}"),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.json() == RULE_NOT_FOUND_BODY


def test_put_unknown_rule_and_unknown_category_returns_404(client: TestClient) -> None:
    # Ordem do serviço: keyword, depois regra (404), depois categoria (422).
    response = client.put(
        f"{BASE}/{MISSING_ID}",
        json={"keyword": "uber", "category_id": MISSING_ID, "priority": 1},
    )

    assert response.status_code == 404
    assert response.json() == RULE_NOT_FOUND_BODY


@pytest.mark.parametrize(
    "rule_id",
    [str(INT64_MAX + 1), str(INT64_MIN - 1), "9" * 40, "abc", "1.5"],
    ids=["int64-overflow", "int64-underflow", "huge", "text", "float"],
)
def test_invalid_path_id_returns_422_validation_error(
    client: TestClient, engine: Engine, rule_id: str
) -> None:
    category_id = _category(client)
    existing = _rule(client, category_id)
    payload = {"keyword": "ifood", "category_id": category_id, "priority": 1}

    responses = [
        client.get(f"{BASE}/{rule_id}"),
        client.put(f"{BASE}/{rule_id}", json=payload),
        client.delete(f"{BASE}/{rule_id}"),
    ]

    for response in responses:
        _assert_validation_error(response, "path.rule_id")
    assert _stored_rule(engine, existing) == ("uber", category_id, 10)


# --- corpo inválido ----------------------------------------------------------------


def test_post_invalid_json_or_without_body_returns_422(client: TestClient, engine: Engine) -> None:
    invalid = client.post(BASE, content=b"{keyword: ", headers={"Content-Type": "application/json"})
    empty = client.post(BASE)
    not_object = client.post(BASE, json=["uber", 1, 1])

    for response in (invalid, empty, not_object):
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
    assert _count_rules(engine) == 0


# --- SEA-64: sem recategorização ----------------------------------------------------


def test_rule_changes_do_not_recategorize_existing_transactions(
    client: TestClient, engine: Engine
) -> None:
    imported = client.post("/imports", files={"file": ("extrato.csv", CSV, "text/csv")})
    assert imported.status_code == 201

    def categories() -> dict[str, int]:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT description, category_id FROM transactions"))
            return {row.description: row.category_id for row in rows}

    before = categories()
    assert len(before) == 2
    transport = _category(client, "Transporte")
    food = _category(client, "Alimentação")

    rule_id = _rule(client, transport, "uber", priority=1)
    assert categories() == before
    put = client.put(
        f"{BASE}/{rule_id}", json={"keyword": "padaria", "category_id": food, "priority": 1}
    )
    assert put.status_code == 200
    assert categories() == before
    assert client.delete(f"{BASE}/{rule_id}").status_code == 204
    assert categories() == before


# --- AS-3 / AS-6 --------------------------------------------------------------------


def test_database_unavailable_returns_503_without_internals(
    isolated_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    """AS-3: SQL, parâmetros e keyword não vazam no corpo nem no log."""
    leaked = f"INSERT INTO categorization_rules (keyword) VALUES ('{SECRET}')"

    def fail() -> NoReturn:
        raise OperationalError(leaked, {"keyword": SECRET}, Exception())

    class FailingService:
        def create(self, keyword: str, category_id: int, priority: int) -> CategorizationRule:
            fail()

        def get(self, rule_id: int) -> CategorizationRule:
            fail()

        def list(self) -> list[CategorizationRule]:
            fail()

        def update(
            self, rule_id: int, keyword: str, category_id: int, priority: int
        ) -> CategorizationRule:
            fail()

        def delete(self, rule_id: int) -> None:
            fail()

    isolated_app.dependency_overrides[get_categorization_rule_service] = FailingService
    caplog.set_level(logging.DEBUG)
    payload = {"keyword": SECRET, "category_id": 1, "priority": 1}

    with TestClient(isolated_app, raise_server_exceptions=False) as client:
        responses = [
            client.post(BASE, json=payload),
            client.get(BASE),
            client.get(f"{BASE}/1"),
            client.put(f"{BASE}/1", json=payload),
            client.delete(f"{BASE}/1"),
        ]

    for response in responses:
        assert response.status_code == 503
        assert response.json()["code"] == "SERVICE_UNAVAILABLE"
        assert SECRET not in response.text
        assert "INSERT INTO" not in response.text
    assert SECRET not in caplog.text
    assert "INSERT INTO" not in caplog.text


def test_openapi_documents_routes_error_responses_and_no_security(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    collection = schema["paths"][BASE]
    item = schema["paths"][f"{BASE}/{{rule_id}}"]

    assert set(collection) == {"get", "post"}
    assert set(item) == {"get", "put", "delete"}
    expected = [
        (collection["post"], "201", ["422", "503"]),
        (collection["get"], "200", ["503"]),
        (item["get"], "200", ["404", "422", "503"]),
        (item["put"], "200", ["404", "422", "503"]),
        (item["delete"], "204", ["404", "422", "503"]),
    ]
    for operation, success, errors in expected:
        assert success in operation["responses"]
        for status in errors:
            ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith("/ErrorResponse")
        assert "security" not in operation
    assert "securitySchemes" not in schema.get("components", {})

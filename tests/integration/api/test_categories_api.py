"""Testes de integração de `POST /categories` e `GET /categories` (TASK-026; 8.1; AS-6).

Requisitos: SEA-15, SEA-16, SEA-35, SEA-51, SEA-53.
"""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from app.api.routers.categories import get_category_service
from app.core.config import Settings
from app.domain.entities import Category
from app.main import create_app

DEFAULT_CATEGORY = "Não categorizada"
NAME_MAX_LENGTH = 100
SECRET = "CATEGORIA SIGILOSA 4242"
CATEGORY_KEYS = {"id", "name"}
NAME_REQUIRED_BODY = {
    "code": "CATEGORY_NAME_REQUIRED",
    "message": "O nome da categoria é obrigatório.",
    "details": None,
    "error_id": None,
}
ALREADY_EXISTS_BODY = {
    "code": "CATEGORY_ALREADY_EXISTS",
    "message": "Já existe uma categoria com este nome.",
    "details": None,
    "error_id": None,
}


def _count_categories(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM categories")).scalar_one())


def _no_auth_header(response: Any) -> bool:
    return "authorization" not in {name.lower() for name in response.request.headers}


@pytest.fixture
def isolated_app(settings: Settings) -> Iterator[FastAPI]:
    app = create_app(settings)
    yield app
    app.dependency_overrides.clear()


def test_post_valid_name_returns_201_with_id_and_name(client: TestClient, engine: Engine) -> None:
    response = client.post("/categories", json={"name": "Transporte"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == CATEGORY_KEYS
    assert isinstance(body["id"], int)
    assert body["name"] == "Transporte"
    assert _no_auth_header(response)  # SEA-35
    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT name FROM categories WHERE id = :id"), {"id": body["id"]}
        ).scalar_one()
    assert stored == "Transporte"


def test_post_normalizes_whitespace_of_name(client: TestClient) -> None:
    response = client.post("/categories", json={"name": "  Lazer   e  Cultura  "})

    assert response.status_code == 201
    assert response.json()["name"] == "Lazer e Cultura"


@pytest.mark.parametrize(
    "payload",
    [{"name": "   "}, {}, {"name": ""}, {"name": None}, {"name": "\t\n "}],
    ids=["only-spaces", "missing", "empty", "null", "whitespace-mix"],
)
def test_post_blank_or_missing_name_returns_422_name_required(
    client: TestClient, engine: Engine, payload: dict[str, Any]
) -> None:
    before = _count_categories(engine)

    response = client.post("/categories", json=payload)

    assert response.status_code == 422
    assert response.json() == NAME_REQUIRED_BODY
    assert _count_categories(engine) == before


@pytest.mark.parametrize("name", ["NÃO CATEGORIZADA", "  não categorizada  ", DEFAULT_CATEGORY])
def test_post_default_category_name_any_case_returns_409(
    client: TestClient, engine: Engine, name: str
) -> None:
    before = _count_categories(engine)

    response = client.post("/categories", json={"name": name})

    assert response.status_code == 409
    assert response.json() == ALREADY_EXISTS_BODY
    assert _count_categories(engine) == before


def test_post_existing_name_different_case_returns_409(client: TestClient, engine: Engine) -> None:
    assert client.post("/categories", json={"name": "Transporte"}).status_code == 201
    before = _count_categories(engine)

    response = client.post("/categories", json={"name": "  TRANSPORTE "})

    assert response.status_code == 409
    assert response.json()["code"] == "CATEGORY_ALREADY_EXISTS"
    assert _count_categories(engine) == before


def test_post_name_at_max_length_is_accepted(client: TestClient) -> None:
    name = "a" * NAME_MAX_LENGTH

    response = client.post("/categories", json={"name": name})

    assert response.status_code == 201
    assert response.json()["name"] == name


def test_post_name_at_max_length_with_edge_spaces_is_accepted(client: TestClient) -> None:
    name = "b" * NAME_MAX_LENGTH

    response = client.post("/categories", json={"name": f"  {name}  "})

    assert response.status_code == 201
    assert response.json()["name"] == name


def test_post_name_over_max_length_returns_422_validation_error(
    client: TestClient, engine: Engine
) -> None:
    before = _count_categories(engine)

    response = client.post("/categories", json={"name": "a" * (NAME_MAX_LENGTH + 1)})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "body.name"
    assert _count_categories(engine) == before


@pytest.mark.parametrize("name", [123, ["Transporte"], {"x": 1}, True])
def test_post_non_string_name_returns_422_validation_error(client: TestClient, name: Any) -> None:
    response = client.post("/categories", json={"name": name})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "body.name"


@pytest.mark.parametrize(
    "name",
    ["Tra\u0000nsporte", "\u0000", "Tra\u0007nsporte", "Transporte\u007f", "Tra\u009bnsporte"],
    ids=["nul-inside", "nul-only", "bell", "del", "c1-csi"],
)
def test_post_name_with_control_char_returns_422_validation_error(
    client: TestClient, engine: Engine, name: str
) -> None:
    # Achado TASK-026-1: o PostgreSQL recusa NUL em texto (DataError -> 500).
    before = _count_categories(engine)

    response = client.post("/categories", json={"name": name})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "body.name"
    assert "\u0000" not in response.text
    assert _count_categories(engine) == before


def test_post_name_with_inner_tab_and_newline_is_normalized(client: TestClient) -> None:
    # Cc de espaço (\t, \n, \r) seguem tratados como espaço pela normalização.
    response = client.post("/categories", json={"name": "Lazer\t\ne\r\nCultura"})

    assert response.status_code == 201
    assert response.json()["name"] == "Lazer e Cultura"


def test_post_invalid_json_returns_422_validation_error(client: TestClient) -> None:
    response = client.post(
        "/categories", content=b"{name: ", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_post_without_body_returns_422(client: TestClient, engine: Engine) -> None:
    before = _count_categories(engine)

    response = client.post("/categories")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert _count_categories(engine) == before


def test_get_lists_default_category_without_auth_header(client: TestClient) -> None:
    response = client.get("/categories")

    assert response.status_code == 200
    assert _no_auth_header(response)  # SEA-35
    body = response.json()
    assert isinstance(body, list)
    assert all(set(item) == CATEGORY_KEYS for item in body)
    assert DEFAULT_CATEGORY in [item["name"] for item in body]


def test_get_lists_created_categories_ordered_by_name(client: TestClient) -> None:
    for name in ("Transporte", "Alimentação", "Moradia"):
        assert client.post("/categories", json={"name": name}).status_code == 201

    response = client.get("/categories")

    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == sorted(names)
    assert set(names) == {"Transporte", "Alimentação", "Moradia", DEFAULT_CATEGORY}


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_update_and_delete_are_not_exposed(client: TestClient, method: str) -> None:
    # LAC-09: sem edição nem exclusão de Category.
    response = client.request(method.upper(), "/categories", json={"name": "X"})

    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


def test_database_unavailable_returns_503_without_internals(
    isolated_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    """AS-3: SQL e parâmetros da falha não vazam no corpo nem no log."""
    leaked = "INSERT INTO categories (name) VALUES ('CATEGORIA SIGILOSA 4242')"

    class FailingService:
        def create(self, name: str | None) -> Category:
            raise OperationalError(leaked, {"name": SECRET}, Exception())

        def list(self) -> list[Category]:
            raise OperationalError(leaked, {"name": SECRET}, Exception())

    isolated_app.dependency_overrides[get_category_service] = FailingService
    caplog.set_level(logging.DEBUG)

    with TestClient(isolated_app, raise_server_exceptions=False) as client:
        responses = [
            client.post("/categories", json={"name": SECRET}),
            client.get("/categories"),
        ]

    for response in responses:
        assert response.status_code == 503
        assert response.json()["code"] == "SERVICE_UNAVAILABLE"
        assert SECRET not in response.text
        assert "INSERT INTO" not in response.text
    assert SECRET not in caplog.text
    assert "INSERT INTO" not in caplog.text


def test_openapi_documents_error_responses_and_no_security(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    path = schema["paths"]["/categories"]

    assert set(path) == {"get", "post"}
    post = path["post"]
    assert "201" in post["responses"]
    for status in ("409", "422", "503"):
        ref = post["responses"][status]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ErrorResponse")
    assert "200" in path["get"]["responses"]
    assert "security" not in post
    assert "security" not in path["get"]
    assert "securitySchemes" not in schema.get("components", {})

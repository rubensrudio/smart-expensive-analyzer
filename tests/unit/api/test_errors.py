import logging
import re
from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import InterfaceError, OperationalError

from app.api.errors import ErrorResponse, register_exception_handlers
from app.core.errors import (
    AppError,
    CategoryAlreadyExistsError,
    CategoryNameRequiredError,
    DuplicateFileError,
    EmptyFileError,
    FileTooLargeError,
    InvalidCsvError,
    InvalidPaginationError,
    InvalidPeriodError,
    MissingColumnsError,
    RuleCategoryNotFoundError,
    RuleNotFoundError,
    ServiceUnavailableError,
    TransactionNotFoundError,
)

ERROR_KEYS = {"code", "message", "details", "error_id"}


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("SELECT secreto FROM transactions")

    @app.get("/db-down")
    def db_down() -> None:
        raise OperationalError("SELECT 1 FROM secret_table", {"pwd": "x"}, Exception("conn"))

    @app.get("/db-interface")
    def db_interface() -> None:
        raise InterfaceError("SELECT 2", None, Exception("iface"))

    @app.get("/missing-columns")
    def missing_columns() -> None:
        raise MissingColumnsError(["date", "amount"])

    @app.get("/transaction")
    def transaction() -> None:
        raise TransactionNotFoundError()

    @app.get("/service-unavailable")
    def service_unavailable() -> None:
        raise ServiceUnavailableError()

    @app.get("/by-date")
    def by_date(d: date) -> dict[str, str]:
        return {"d": d.isoformat()}

    @app.get("/by-id/{item_id}")
    def by_id(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def _assert_error_shape(body: dict[str, Any]) -> None:
    assert set(body) == ERROR_KEYS
    ErrorResponse.model_validate(body)


def test_unexpected_exception_returns_500_without_internals(client: TestClient) -> None:
    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    _assert_error_shape(body)
    assert body["code"] == "INTERNAL_ERROR"
    assert re.fullmatch(r"[0-9a-f]{32}", body["error_id"])
    assert body["message"] == f"Erro interno. Identificador: {body['error_id']}."
    assert body["details"] is None
    assert "SELECT" not in response.text
    assert "Traceback" not in response.text


def test_unexpected_exception_logs_same_error_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        response = client.get("/boom")

    error_id = response.json()["error_id"]
    records = [r for r in caplog.records if error_id in r.getMessage()]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
    assert "unexpected_error" in record.getMessage()
    assert "path=/boom" in record.getMessage()
    assert "method=GET" in record.getMessage()


def test_operational_error_returns_503(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.api.errors"):
        response = client.get("/db-down")

    assert response.status_code == 503
    body = response.json()
    _assert_error_shape(body)
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert body["message"] == "Serviço temporariamente indisponível. Tente novamente."
    assert "SELECT" not in response.text
    assert any("database_unavailable path=/db-down" in r.getMessage() for r in caplog.records)
    assert all("secret_table" not in r.getMessage() for r in caplog.records)


def test_interface_error_returns_503(client: TestClient) -> None:
    response = client.get("/db-interface")

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"


def test_service_unavailable_domain_error_returns_503(client: TestClient) -> None:
    response = client.get("/service-unavailable")

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"


def test_invalid_date_query_returns_422_validation_error(client: TestClient) -> None:
    response = client.get("/by-date", params={"d": "2026-13-01"})

    assert response.status_code == 422
    body = response.json()
    _assert_error_shape(body)
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Dados de entrada inválidos."
    assert body["details"]
    assert body["details"][0]["field"] == "query.d"
    assert isinstance(body["details"][0]["message"], str)
    assert set(body["details"][0]) == {"field", "message"}


def test_non_integer_path_id_returns_422_validation_error(client: TestClient) -> None:
    response = client.get("/by-id/abc")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_unknown_route_returns_404_standard_body(client: TestClient) -> None:
    response = client.get("/nao-existe")

    assert response.status_code == 404
    body = response.json()
    _assert_error_shape(body)
    assert body["code"] == "NOT_FOUND"
    assert body["message"] == "Recurso não encontrado."


def test_wrong_method_returns_405_standard_body(client: TestClient) -> None:
    response = client.post("/boom")

    assert response.status_code == 405
    body = response.json()
    _assert_error_shape(body)
    assert body["code"] == "METHOD_NOT_ALLOWED"
    assert body["message"] == "Método não permitido."
    assert "GET" in response.headers["allow"]


def test_app_error_uses_code_status_and_details(client: TestClient) -> None:
    response = client.get("/missing-columns")

    assert response.status_code == 422
    body = response.json()
    _assert_error_shape(body)
    assert body["code"] == "MISSING_COLUMNS"
    assert body["message"] == "Colunas obrigatórias ausentes: date, amount."
    assert body["details"] == ["date", "amount"]
    assert body["error_id"] is None


def test_domain_not_found_returns_404(client: TestClient) -> None:
    response = client.get("/transaction")

    assert response.status_code == 404
    assert response.json() == {
        "code": "TRANSACTION_NOT_FOUND",
        "message": "Transação não encontrada.",
        "details": None,
        "error_id": None,
    }


@pytest.mark.parametrize(
    ("error", "code", "message", "status"),
    [
        (EmptyFileError(), "EMPTY_FILE", "O arquivo enviado não contém transações.", 422),
        (InvalidCsvError(), "INVALID_CSV", "Não foi possível ler o arquivo como CSV.", 422),
        (
            FileTooLargeError(10),
            "FILE_TOO_LARGE",
            "O arquivo excede o tamanho máximo de 10 MB.",
            413,
        ),
        (
            DuplicateFileError(7),
            "DUPLICATE_FILE",
            "Este arquivo já foi importado (importação 7).",
            409,
        ),
        (TransactionNotFoundError(), "TRANSACTION_NOT_FOUND", "Transação não encontrada.", 404),
        (
            CategoryNameRequiredError(),
            "CATEGORY_NAME_REQUIRED",
            "O nome da categoria é obrigatório.",
            422,
        ),
        (
            CategoryAlreadyExistsError(),
            "CATEGORY_ALREADY_EXISTS",
            "Já existe uma categoria com este nome.",
            409,
        ),
        (
            RuleCategoryNotFoundError(),
            "RULE_CATEGORY_NOT_FOUND",
            "Categoria informada na regra não existe.",
            422,
        ),
        (
            RuleNotFoundError(),
            "RULE_NOT_FOUND",
            "Regra de categorização não encontrada.",
            404,
        ),
        (
            InvalidPeriodError(),
            "INVALID_PERIOD",
            "A data inicial deve ser anterior ou igual à data final.",
            422,
        ),
        (
            InvalidPaginationError(),
            "INVALID_PAGINATION",
            "Parâmetros de paginação inválidos: limit deve estar entre 1 e 500 e offset "
            "não pode ser negativo.",
            422,
        ),
        (
            ServiceUnavailableError(),
            "SERVICE_UNAVAILABLE",
            "Serviço temporariamente indisponível. Tente novamente.",
            503,
        ),
    ],
)
def test_catalog_codes_messages_and_status(
    error: AppError, code: str, message: str, status: int
) -> None:
    assert isinstance(error, AppError)
    assert error.code == code
    assert error.message == message
    assert error.http_status == status
    assert str(error) == message

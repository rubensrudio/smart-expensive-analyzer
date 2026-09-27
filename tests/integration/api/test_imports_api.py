"""Testes de integração de `POST /imports` (TASK-024; contrato 8.1; AS-6).

Requisitos: SEA-07, SEA-08, SEA-35, SEA-42, SEA-43, SEA-45, SEA-90, SEA-91, SEA-92, SEA-104.
"""

import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from app.api.routers.imports import get_import_service
from app.application.services.import_service import ImportService
from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.domain.entities import ImportRecord
from app.main import create_app

HEADER = "date,description,amount,merchant,currency"
MIB = 1024 * 1024
SECRET_DESCRIPTION = "FARMACIA SIGILOSA 7788"
ERROR_KEYS = {"code", "message", "details", "error_id"}
IMPORT_OUT_KEYS = {
    "id",
    "filename",
    "status",
    "received_at",
    "rows_read",
    "imported_count",
    "rejected_count",
    "duplicate_count",
    "rejections",
}


def _csv(*lines: str, header: str = HEADER) -> bytes:
    return ("\n".join([header, *lines]) + "\n").encode("utf-8")


VALID_3 = _csv(
    "2024-01-05,UBER TRIP,-25.50,Uber,BRL",
    "2024-01-06,PADARIA CENTRAL,-12.00,Padaria,BRL",
    "2024-01-07,SALARIO,5000.00,Empresa,BRL",
)


@pytest.fixture
def small_limit_app(settings: Settings) -> Iterator[FastAPI]:
    app = create_app(settings.model_copy(update={"max_upload_mb": 1}))
    yield app
    app.dependency_overrides.clear()


def test_valid_csv_returns_201_without_auth_header(client: TestClient, engine: Engine) -> None:
    response = client.post("/imports", files={"file": ("extrato.csv", VALID_3, "text/csv")})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == IMPORT_OUT_KEYS
    assert body["status"] == "concluida"
    assert body["filename"] == "extrato.csv"
    assert body["rows_read"] == 3
    assert body["imported_count"] == 3
    assert body["rejected_count"] == 0
    assert body["duplicate_count"] == 0
    assert body["rejections"] == []
    assert isinstance(body["id"], int)
    assert body["received_at"]
    # SEA-35: nenhum cabeçalho de autenticação é enviado nem exigido.
    assert "authorization" not in {name.lower() for name in response.request.headers}
    with engine.connect() as conn:
        linked = conn.execute(
            text("SELECT count(*) FROM transactions WHERE import_id = :id"), {"id": body["id"]}
        ).scalar_one()
    assert linked == 3


def test_same_file_again_returns_409_with_existing_id(client: TestClient) -> None:
    first = client.post("/imports", files={"file": ("a.csv", VALID_3, "text/csv")})
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = client.post("/imports", files={"file": ("outro-nome.csv", VALID_3, "text/csv")})

    assert second.status_code == 409
    body = second.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == "DUPLICATE_FILE"
    assert f"importação {first_id}" in body["message"]


def test_empty_file_returns_422_empty_file(client: TestClient, engine: Engine) -> None:
    response = client.post("/imports", files={"file": ("vazio.csv", b"", "text/csv")})

    assert response.status_code == 422
    assert response.json()["code"] == "EMPTY_FILE"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM imports")).scalar_one() == 0


def test_binary_file_returns_422_invalid_csv(client: TestClient) -> None:
    binary = bytes([0x89, 0x50, 0x4E, 0x47, 0x00, 0xFF, 0xFE, 0x00]) * 16

    response = client.post(
        "/imports", files={"file": ("foto.png", binary, "application/octet-stream")}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_CSV"


def test_missing_amount_column_returns_422_with_details(client: TestClient) -> None:
    content = _csv("2024-01-05,UBER TRIP", header="date,description")

    response = client.post("/imports", files={"file": ("sem-valor.csv", content, "text/csv")})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "MISSING_COLUMNS"
    assert body["details"] == ["amount"]


def test_file_one_byte_over_limit_returns_413(small_limit_app: FastAPI, engine: Engine) -> None:
    content = _csv("2024-01-05,UBER TRIP,-25.50,Uber,BRL")
    oversized = content + b"\n" * (MIB + 1 - len(content))
    assert len(oversized) == MIB + 1

    with TestClient(small_limit_app) as client:
        response = client.post("/imports", files={"file": ("grande.csv", oversized, "text/csv")})

    assert response.status_code == 413
    body = response.json()
    assert body["code"] == "FILE_TOO_LARGE"
    assert "1 MB" in body["message"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM imports")).scalar_one() == 0


def test_file_exactly_at_limit_is_accepted(small_limit_app: FastAPI) -> None:
    content = _csv("2024-01-05,UBER TRIP,-25.50,Uber,BRL")
    at_limit = content + b"\n" * (MIB - len(content))
    assert len(at_limit) == MIB

    with TestClient(small_limit_app) as client:
        response = client.post("/imports", files={"file": ("limite.csv", at_limit, "text/csv")})

    assert response.status_code == 201
    assert response.json()["imported_count"] == 1


def test_router_reads_at_most_limit_plus_one_byte(small_limit_app: FastAPI) -> None:
    """AS-6: um upload gigante não é carregado inteiro na memória nem repassado ao serviço."""
    received_sizes: list[int] = []
    settings = small_limit_app.state.settings

    class SpyImportService(ImportService):
        def import_csv(self, filename: str, content: bytes) -> ImportRecord:
            received_sizes.append(len(content))
            return super().import_csv(filename, content)

    def spy_provider() -> ImportService:
        from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

        factory = small_limit_app.state.session_factory
        return SpyImportService(lambda: SqlAlchemyUnitOfWork(factory), settings)

    small_limit_app.dependency_overrides[get_import_service] = spy_provider
    huge = b"a" * (3 * MIB)

    with TestClient(small_limit_app) as client:
        response = client.post("/imports", files={"file": ("enorme.csv", huge, "text/csv")})

    assert response.status_code == 413
    assert response.json()["code"] == "FILE_TOO_LARGE"
    assert received_sizes == [MIB + 1]


def test_invalid_date_row_returns_201_with_formatted_rejection(client: TestClient) -> None:
    content = _csv(
        "2024-01-05,UBER TRIP,-25.50,Uber,BRL",
        "2024-13-45,PADARIA CENTRAL,-12.00,Padaria,BRL",
    )

    response = client.post("/imports", files={"file": ("rej.csv", content, "text/csv")})

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "concluida_com_rejeicoes"
    assert body["imported_count"] == 1
    assert body["rejected_count"] == 1
    assert len(body["rejections"]) == 1
    rejection = body["rejections"][0]
    assert set(rejection) == {"line", "reason"}
    assert rejection["reason"].startswith("Linha ")
    assert rejection["reason"] == f"Linha {rejection['line']}: data inválida"


def test_missing_file_field_returns_422_validation_error(client: TestClient) -> None:
    response = client.post("/imports", data={"outro": "x"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert {"field": "body.file"}.items() <= body["details"][0].items()


def test_service_unavailable_returns_503_without_internals(
    small_limit_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    """AS-3: a causa encadeada (SQL + parâmetros) não vaza no corpo nem é logada pelo router."""
    leaked = "INSERT INTO transactions VALUES ('FARMACIA SIGILOSA 7788', -99.99)"

    class FailingService:
        def import_csv(self, filename: str, content: bytes) -> ImportRecord:
            cause = OperationalError(leaked, {"description": SECRET_DESCRIPTION}, Exception())
            raise ServiceUnavailableError() from cause

    small_limit_app.dependency_overrides[get_import_service] = FailingService
    caplog.set_level(logging.DEBUG)

    with TestClient(small_limit_app, raise_server_exceptions=False) as client:
        response = client.post("/imports", files={"file": ("x.csv", VALID_3, "text/csv")})

    assert response.status_code == 503
    body = response.json()
    assert body == {
        "code": "SERVICE_UNAVAILABLE",
        "message": "Serviço temporariamente indisponível. Tente novamente.",
        "details": None,
        "error_id": None,
    }
    assert SECRET_DESCRIPTION not in response.text
    assert SECRET_DESCRIPTION not in caplog.text
    assert "INSERT INTO" not in caplog.text


def test_successful_import_does_not_log_row_content(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    content = _csv(f"2024-01-05,{SECRET_DESCRIPTION},-99.99,Farmacia,BRL")

    response = client.post("/imports", files={"file": ("f.csv", content, "text/csv")})

    assert response.status_code == 201
    assert "import_finished" in caplog.text
    assert SECRET_DESCRIPTION not in caplog.text
    assert "99.99" not in caplog.text


def test_openapi_documents_error_responses_and_no_security(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/imports"]["post"]

    assert "201" in operation["responses"]
    for status in ("409", "413", "422", "503"):
        ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ErrorResponse")
    assert "security" not in operation
    assert "securitySchemes" not in schema.get("components", {})


def test_file_field_sent_as_plain_text_returns_422_validation_error(client: TestClient) -> None:
    # Sem nome de arquivo, a parte multipart é um campo de texto, não um upload.
    response = client.post("/imports", files={"file": ("", VALID_3, "text/csv")})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "body.file"


def test_control_chars_in_filename_are_stripped_in_response(client: TestClient) -> None:
    response = client.post("/imports", files={"file": ("a b.csv", VALID_3, "text/csv")})

    assert response.status_code == 201
    assert response.json()["filename"] == "ab.csv"

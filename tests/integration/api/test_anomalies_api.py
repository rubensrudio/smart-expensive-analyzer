"""Testes de integração de `GET /anomalies` (TASK-029; contrato 8.1; AS-6).

Requisitos: SEA-27, SEA-28, SEA-31, SEA-35, SEA-57, SEA-96; LAC-13 (GET não recalcula).
"""

import logging
from collections.abc import Callable, Iterator
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from app.api.routers.anomalies import get_anomaly_service
from app.api.schemas.anomalies import AnomalyOut
from app.core.config import Settings
from app.domain.entities import (
    Anomaly,
    AnomalyCandidate,
    NewTransaction,
    Period,
    Transaction,
    TransactionType,
)
from app.domain.ports import UnitOfWork
from app.main import create_app

HEADER = "date,description,amount,merchant,currency"
ERROR_KEYS = {"code", "message", "details", "error_id"}
ANOMALY_KEYS = {"id", "method", "value", "reason", "transaction"}
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
SECRET_SQL = "SELECT secret_column FROM anomalies"
OUTLIER_DATE = "2026-03-15"

UoWFactory = Callable[[], UnitOfWork]


def _csv(*lines: str) -> bytes:
    return ("\n".join([HEADER, *lines]) + "\n").encode("utf-8")


def _sea28_lines(currency: str = "BRL", outlier_date: str = OUTLIER_DATE) -> list[str]:
    """20 despesas entre 40,00 e 59,00 e uma de 5.000,00 no mesmo grupo (SEA-28)."""
    lines = [
        f"2026-02-{1 + i:02d},COMPRA {currency} {i},-{40 + i}.00,Loja {i},{currency}"
        for i in range(20)
    ]
    lines.append(f"{outlier_date},COMPRA GRANDE {currency},-5000.00,Loja X,{currency}")
    return lines


def _import(client: TestClient, content: bytes, filename: str = "extrato.csv") -> None:
    response = client.post("/imports", files={"file": (filename, content, "text/csv")})
    assert response.status_code == 201, response.text


def _anomaly_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM anomalies")).scalar_one())


# --- Caminho feliz -------------------------------------------------------------------


def test_sea28_import_lists_single_iqr_anomaly_without_auth(client: TestClient) -> None:
    """SEA-27, SEA-28, SEA-35: a de 5.000,00 é a única anomalia, sem cabeçalho de auth."""
    _import(client, _csv(*_sea28_lines()))

    response = client.get("/anomalies")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items"}
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert set(item) == ANOMALY_KEYS
    assert isinstance(item["id"], int)
    assert item["method"] == "IQR"
    assert item["value"] == "70.00"
    assert isinstance(item["reason"], str) and item["reason"].strip()
    tx = item["transaction"]
    assert set(tx) == TRANSACTION_KEYS
    assert tx["amount"] == "-5000.00"
    assert tx["date"] == OUTLIER_DATE
    assert tx["description"] == "COMPRA GRANDE BRL"
    assert tx["merchant"] == "Loja X"
    assert tx["currency"] == "BRL"
    assert tx["type"] == "despesa"
    assert set(tx["category"]) == {"id", "name"}
    assert isinstance(tx["import_id"], int)
    assert "authorization" not in {name.lower() for name in response.request.headers}


def test_empty_database_returns_empty_items(client: TestClient) -> None:
    """SEA-96: sem despesas → 200 com lista vazia."""
    response = client.get("/anomalies")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_below_min_sample_returns_empty_items(client: TestClient) -> None:
    """SEA-96: nenhum grupo atinge a amostra mínima → 200 com lista vazia."""
    _import(client, _csv("2026-01-01,A,-10.00,L,BRL", "2026-01-02,B,-9999.00,L,BRL"))

    response = client.get("/anomalies")

    assert response.status_code == 200
    assert response.json() == {"items": []}


# --- Período (SEA-31, SEA-57) ---------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "2026-03-16"},
        {"end_date": "2026-03-14"},
        {"start_date": "2026-01-01", "end_date": "2026-03-14"},
        {"start_date": "2026-03-16", "end_date": "2026-12-31"},
    ],
)
def test_period_excluding_anomaly_date_returns_empty(
    client: TestClient, params: dict[str, str]
) -> None:
    """SEA-31: período que exclui a data da anomalia → `items == []`."""
    _import(client, _csv(*_sea28_lines()))

    response = client.get("/anomalies", params=params)

    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"start_date": OUTLIER_DATE},
        {"end_date": OUTLIER_DATE},
        {"start_date": OUTLIER_DATE, "end_date": OUTLIER_DATE},
        {"start_date": "2026-01-01", "end_date": "2026-12-31"},
    ],
)
def test_period_including_anomaly_date_returns_it(
    client: TestClient, params: dict[str, str]
) -> None:
    """SEA-31 (intervalo fechado nas duas pontas) e SEA-57 (sem filtro = todo o histórico)."""
    _import(client, _csv(*_sea28_lines()))

    response = client.get("/anomalies", params=params)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [i["transaction"]["date"] for i in items] == [OUTLIER_DATE]


def test_inverted_period_returns_422_invalid_period(client: TestClient) -> None:
    response = client.get(
        "/anomalies", params={"start_date": "2026-03-16", "end_date": "2026-03-15"}
    )

    assert response.status_code == 422
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == "INVALID_PERIOD"


@pytest.mark.parametrize("param", ["start_date", "end_date"])
@pytest.mark.parametrize(
    "raw",
    [
        "abc",
        "",
        " ",
        "2026-13-01",
        "2026-02-30",
        "2026-00-10",
        "2026-1-5",
        "15/03/2026",
        "0000-01-01",
        "10000-01-01",
        "99999999999999999999-01-01",
        "-2026-01-01",
        "2026-03-15\x00",
        "\x00",
        "2026-03-15T25:00:00",
        "1e400",
        "NaN",
        "9" * 5000,
        "2026-03-15' OR '1'='1",
        "2026-03-15;DROP TABLE anomalies",
        "٢٠٢٦-01-01",
    ],
)
def test_invalid_date_param_returns_422_validation_error(
    client: TestClient, engine: Engine, param: str, raw: str
) -> None:
    """Entrada adversarial nunca vira 500: formato inválido/data impossível → 422."""
    response = client.get("/anomalies", params={param: raw})

    assert response.status_code == 422, response.text
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == "VALIDATION_ERROR"
    assert body["error_id"] is None
    # Nada foi apagado nem gravado pela tentativa de injeção.
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('anomalies')")).scalar_one() is not None


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "0001-01-01", "end_date": "9999-12-31"},
        {"start_date": "0001-01-01"},
        {"end_date": "9999-12-31"},
    ],
)
def test_extreme_valid_dates_are_accepted(client: TestClient, params: dict[str, str]) -> None:
    """Limites de `date` do Python são aceitos pelo banco, sem 500."""
    _import(client, _csv(*_sea28_lines()))

    response = client.get("/anomalies", params=params)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_unknown_query_params_are_ignored(client: TestClient) -> None:
    _import(client, _csv(*_sea28_lines()))

    response = client.get("/anomalies", params={"limit": "x", "foo": "\x00"})

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


# --- Ordenação e múltiplas moedas ------------------------------------------------------


def test_items_ordered_by_transaction_date_desc_then_id_desc(client: TestClient) -> None:
    """8.1: ordenado por data da transação desc e id desc; grupos por moeda (SEA-54)."""
    content = _csv(
        *_sea28_lines("BRL", "2026-03-10"),
        *_sea28_lines("USD", "2026-03-20"),
        *_sea28_lines("EUR", "2026-03-10"),
    )
    _import(client, content)

    items = client.get("/anomalies").json()["items"]

    assert [(i["transaction"]["date"], i["transaction"]["currency"]) for i in items][0] == (
        "2026-03-20",
        "USD",
    )
    keys = [(i["transaction"]["date"], i["id"]) for i in items]
    assert len(keys) == 3
    assert keys == sorted(keys, reverse=True)
    assert {i["transaction"]["currency"] for i in items} == {"BRL", "USD", "EUR"}


# --- LAC-13: GET só lê ------------------------------------------------------------------


def _seed_manual_anomaly(uow_factory: UoWFactory) -> int:
    """Grava uma anomalia que o IQR nunca geraria (1 transação), para provar que o GET só lê."""
    with uow_factory() as uow:
        import_id = uow.imports.create_processing("manual.csv", "b" * 64, datetime(2026, 1, 1))
        category_id = uow.categories.get_default().id
        uow.transactions.insert_ignoring_duplicates(
            [
                NewTransaction(
                    date=date(2026, 1, 10),
                    description="MANUAL",
                    merchant="M",
                    amount=Decimal("-12.34"),
                    currency="BRL",
                    type=TransactionType.EXPENSE,
                    category_id=category_id,
                    import_id=import_id,
                    dedup_key="manual-1",
                )
            ]
        )
        tx_id = uow.transactions.list_all_for_categorization()[0].id
        uow.anomalies.replace_all(
            [AnomalyCandidate(tx_id, "IQR", Decimal("1.00"), "semeada manualmente")]
        )
        uow.commit()
    return tx_id


def test_get_does_not_recompute_anomalies(
    client: TestClient, uow_factory: UoWFactory, engine: Engine
) -> None:
    """LAC-13: o GET lista o que está persistido e não recalcula."""
    tx_id = _seed_manual_anomaly(uow_factory)

    first = client.get("/anomalies")
    second = client.get("/anomalies")

    assert first.status_code == 200
    assert first.json() == second.json()
    items = first.json()["items"]
    assert len(items) == 1
    assert items[0]["transaction"]["id"] == tx_id
    assert items[0]["value"] == "1.00"
    assert items[0]["reason"] == "semeada manualmente"
    assert _anomaly_count(engine) == 1


# --- Serialização de dinheiro ------------------------------------------------------------


def _anomaly_entity(value: str, amount: str) -> Anomaly:
    return Anomaly(
        id=1,
        method="IQR",
        value=Decimal(value),
        reason="r",
        transaction=Transaction(
            id=2,
            date=date(2026, 1, 1),
            description="d",
            merchant="m",
            amount=Decimal(amount),
            currency="BRL",
            type=TransactionType.EXPENSE,
            category_id=3,
            category_name="Não categorizada",
            import_id=4,
        ),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("70", "70.00"), ("70.005", "70.01"), ("70.015", "70.02"), ("0.004", "0.00")],
)
def test_anomaly_value_is_money_with_two_places_half_up(raw: str, expected: str) -> None:
    """P-13/P-15: `value` sai como string com 2 casas, arredondado HALF_UP."""
    dumped = AnomalyOut.from_entity(_anomaly_entity(raw, "-5000")).model_dump(mode="json")

    assert dumped["value"] == expected
    assert dumped["transaction"]["amount"] == "-5000.00"
    assert set(dumped) == ANOMALY_KEYS


# --- Erros -------------------------------------------------------------------------------


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    application = create_app(settings)
    yield application
    application.dependency_overrides.clear()


def test_database_unavailable_returns_503_without_leaking_sql(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    class FailingService:
        def list(self, period: Period) -> list[Anomaly]:
            raise OperationalError(SECRET_SQL, {"p": "segredo"}, Exception("boom"))

    app.dependency_overrides[get_anomaly_service] = FailingService
    caplog.set_level(logging.DEBUG)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/anomalies")

    assert response.status_code == 503
    body = response.json()
    assert set(body) == ERROR_KEYS
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert "secret_column" not in response.text
    assert "segredo" not in response.text
    assert "secret_column" not in caplog.text


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_write_methods_are_not_allowed(client: TestClient, method: str) -> None:
    """A lista é somente leitura (spec, fora de escopo)."""
    response = client.request(method.upper(), "/anomalies")

    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


def test_openapi_documents_error_responses(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/anomalies"]["get"]

    assert {"422", "503"} <= set(operation["responses"])
    params = {p["name"] for p in operation["parameters"]}
    assert params == {"start_date", "end_date"}

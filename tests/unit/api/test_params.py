from datetime import date
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.errors import register_exception_handlers
from app.api.params import pagination_params, period_params
from app.domain.entities import Page, Period


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/period")
    def read_period(period: Annotated[Period, Depends(period_params)]) -> dict[str, Any]:
        return {"start": _iso(period.start), "end": _iso(period.end)}

    @app.get("/page")
    def read_page(page: Annotated[Page, Depends(pagination_params)]) -> dict[str, int]:
        return {"limit": page.limit, "offset": page.offset}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def test_period_without_params_is_whole_history(client: TestClient) -> None:
    response = client.get("/period")
    assert response.status_code == 200
    assert response.json() == {"start": None, "end": None}


def test_period_with_only_start_date_is_open_on_end(client: TestClient) -> None:
    response = client.get("/period", params={"start_date": "2026-01-01"})
    assert response.status_code == 200
    assert response.json() == {"start": "2026-01-01", "end": None}


def test_period_with_only_end_date_is_open_on_start(client: TestClient) -> None:
    response = client.get("/period", params={"end_date": "2026-01-31"})
    assert response.status_code == 200
    assert response.json() == {"start": None, "end": "2026-01-31"}


def test_period_with_equal_dates_is_accepted(client: TestClient) -> None:
    response = client.get("/period", params={"start_date": "2026-01-15", "end_date": "2026-01-15"})
    assert response.status_code == 200
    assert response.json() == {"start": "2026-01-15", "end": "2026-01-15"}


def test_period_start_after_end_returns_invalid_period(client: TestClient) -> None:
    response = client.get("/period", params={"start_date": "2026-02-01", "end_date": "2026-01-01"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_PERIOD"
    assert body["message"] == "A data inicial deve ser anterior ou igual à data final."


def test_period_with_non_iso_date_returns_validation_error(client: TestClient) -> None:
    response = client.get("/period", params={"start_date": "01/02/2026"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "query.start_date"


def test_period_params_direct_call_raises_on_inverted_range() -> None:
    from app.core.errors import InvalidPeriodError

    with pytest.raises(InvalidPeriodError):
        period_params(start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))


def test_pagination_without_params_defaults_to_50_0(client: TestClient) -> None:
    response = client.get("/page")
    assert response.status_code == 200
    assert response.json() == {"limit": 50, "offset": 0}


def test_pagination_params_direct_call_defaults() -> None:
    assert pagination_params() == Page(50, 0)


@pytest.mark.parametrize(
    "params",
    [{"limit": "0"}, {"limit": "501"}, {"offset": "-1"}, {"limit": "-5", "offset": "-1"}],
)
def test_pagination_out_of_range_returns_invalid_pagination(
    client: TestClient, params: dict[str, str]
) -> None:
    response = client.get("/page", params=params)
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_PAGINATION"
    assert body["message"] == (
        "Parâmetros de paginação inválidos: limit deve estar entre 1 e 500 e offset "
        "não pode ser negativo."
    )


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"limit": "500"}, {"limit": 500, "offset": 0}),
        ({"limit": "1", "offset": "0"}, {"limit": 1, "offset": 0}),
        ({"limit": "10", "offset": "30"}, {"limit": 10, "offset": 30}),
    ],
)
def test_pagination_boundaries_are_accepted(
    client: TestClient, params: dict[str, str], expected: dict[str, int]
) -> None:
    response = client.get("/page", params=params)
    assert response.status_code == 200
    assert response.json() == expected


def test_pagination_non_integer_returns_validation_error(client: TestClient) -> None:
    response = client.get("/page", params={"limit": "abc"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"

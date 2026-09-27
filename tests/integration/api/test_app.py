"""Testes da factory `create_app` (CT-26, DA-4, SEA-02)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.api.errors import ErrorResponse
from app.core.config import Settings
from app.main import create_app


def test_health_returns_ok_without_auth_header(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "authorization" not in {name.lower() for name in response.request.headers}


def test_openapi_exposes_title_and_version(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    info = response.json()["info"]
    assert info["title"] == "Smart Expense Analyzer"
    assert info["version"] == "0.1.0"
    assert "/health" in response.json()["paths"]


def test_unknown_route_returns_error_response_404(client: TestClient) -> None:
    response = client.get("/rota-inexistente")

    assert response.status_code == 404
    body = ErrorResponse.model_validate(response.json())
    assert body.code == "NOT_FOUND"
    assert set(response.json()) == {"code", "message", "details", "error_id"}


def test_create_app_without_database_url_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # sem `.env` no diretório corrente

    with pytest.raises(SystemExit) as exc_info:
        create_app()

    assert exc_info.value.code == 1


def test_create_app_uses_env_settings_when_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, postgres_url: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    monkeypatch.setenv("DEFAULT_CURRENCY", "usd")

    app = create_app()
    try:
        assert app.state.settings.default_currency == "USD"
    finally:
        app.state.engine.dispose()


def test_app_state_holds_settings_engine_and_session_factory(settings: Settings) -> None:
    app = create_app(settings)
    try:
        assert app.state.settings is settings
        assert isinstance(app.state.engine, Engine)
        assert isinstance(app.state.session_factory, sessionmaker)
        assert app.state.session_factory.kw["bind"] is app.state.engine
        assert app.state.engine.hide_parameters is True
    finally:
        app.state.engine.dispose()


def test_lifespan_disposes_engine_on_shutdown(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(settings)
    disposed: list[bool] = []
    original_dispose = app.state.engine.dispose

    def spy_dispose(*args: object, **kwargs: object) -> None:
        disposed.append(True)
        original_dispose()

    monkeypatch.setattr(app.state.engine, "dispose", spy_dispose)

    with TestClient(app) as test_client:
        assert test_client.get("/health").status_code == 200
        assert disposed == []

    assert disposed == [True]

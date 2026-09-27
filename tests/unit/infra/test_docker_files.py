"""Checagens estáticas do Dockerfile e do docker-compose.yml (TASK-030; SEA-01, DA-12, DA-13)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "docker-compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"
DOCKERIGNORE = ROOT / ".dockerignore"


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose(compose_text: str) -> dict[str, Any]:
    data = yaml.safe_load(compose_text)
    assert isinstance(data, dict)
    return data


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


# --- Dockerfile ---------------------------------------------------------------


def test_dockerfile_uses_python_312_slim(dockerfile: str) -> None:
    assert "FROM python:3.12-slim" in dockerfile


def test_dockerfile_copies_app_and_alembic(dockerfile: str) -> None:
    for fragment in ("app/", "alembic/", "alembic.ini"):
        assert fragment in dockerfile, fragment


def test_dockerfile_installs_package_without_dev_extras(dockerfile: str) -> None:
    assert "pip install" in dockerfile
    assert "[dev]" not in dockerfile


def test_dockerfile_cmd_runs_migrations_then_uvicorn(dockerfile: str) -> None:
    assert "alembic upgrade head" in dockerfile
    assert (
        "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --no-access-log"
        in dockerfile
    )
    assert dockerfile.index("alembic upgrade head") < dockerfile.index("exec uvicorn")


def test_dockerfile_runs_as_non_root(dockerfile: str) -> None:
    user_lines = [ln.split() for ln in dockerfile.splitlines() if ln.strip().startswith("USER ")]
    assert user_lines, "Dockerfile sem USER"
    assert user_lines[-1][1] not in {"root", "0"}


# --- docker-compose.yml ---------------------------------------------------------


def test_compose_api_port_bound_to_localhost(compose_text: str, compose: dict[str, Any]) -> None:
    assert "127.0.0.1:8000:8000" in compose_text
    assert compose["services"]["api"]["ports"] == ["127.0.0.1:8000:8000"]


def test_compose_api_waits_for_healthy_db(compose_text: str, compose: dict[str, Any]) -> None:
    assert "service_healthy" in compose_text
    api = compose["services"]["api"]
    assert api["depends_on"]["db"]["condition"] == "service_healthy"
    assert api["build"] == "."
    assert api["env_file"] in (".env", [".env"])


def test_compose_db_has_no_published_ports(compose: dict[str, Any]) -> None:
    db = compose["services"]["db"]
    assert "ports" not in db


def test_compose_db_postgres_with_healthcheck_and_volume(compose: dict[str, Any]) -> None:
    db = compose["services"]["db"]
    assert db["image"] == "postgres:16-alpine"
    test_cmd = db["healthcheck"]["test"]
    joined = test_cmd if isinstance(test_cmd, str) else " ".join(test_cmd)
    assert "pg_isready" in joined
    assert any(str(v).startswith("pgdata:") for v in db["volumes"])
    assert "pgdata" in compose["volumes"]
    # POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB vêm do .env, nunca do arquivo versionado.
    assert db["env_file"] in (".env", [".env"])


def test_compose_has_no_hardcoded_password(compose_text: str) -> None:
    assert "sea_dev_password" not in compose_text


# --- .env.example / .dockerignore ----------------------------------------------


def test_env_example_lists_plan_variables() -> None:
    env = _env_example()
    expected = {
        "DATABASE_URL",
        "DEFAULT_CURRENCY",
        "MAX_UPLOAD_MB",
        "ANOMALY_IQR_K",
        "ANOMALY_MIN_SAMPLE",
        "LOG_LEVEL",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    }
    assert set(env) == expected
    assert env["DATABASE_URL"] == "postgresql+psycopg://sea:sea_dev_password@db:5432/sea"


def test_dockerignore_excludes_env_and_venv() -> None:
    entries = {ln.strip() for ln in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()}
    for entry in (".venv", ".git", "reports", "__pycache__", ".env", ".specs"):
        assert entry in entries, entry

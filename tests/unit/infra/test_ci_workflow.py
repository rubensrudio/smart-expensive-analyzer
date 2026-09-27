"""Checagens estáticas do workflow de CI e do README (TASK-031; SEA-01, SEA-04, LAC-01)."""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "README.md"

EXPECTED_TEST_DB_URL = "postgresql+psycopg://sea:sea@localhost:5432/sea_test"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow(workflow_text: str) -> dict[Any, Any]:
    data = yaml.safe_load(workflow_text)
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


def _triggers(workflow: dict[Any, Any]) -> Any:
    # YAML 1.1: a chave `on` vira o booleano True no PyYAML.
    return workflow.get("on", workflow.get(True))


def _steps(workflow: dict[Any, Any], job: str) -> list[dict[str, Any]]:
    steps = workflow["jobs"][job]["steps"]
    assert isinstance(steps, list)
    return steps


def _run_commands(workflow: dict[Any, Any], job: str) -> str:
    return "\n".join(str(step.get("run", "")) for step in _steps(workflow, job))


def test_workflow_triggers_on_push_and_pull_request(
    workflow_text: str, workflow: dict[Any, Any]
) -> None:
    assert "push" in workflow_text
    assert "pull_request" in workflow_text
    triggers = _triggers(workflow)
    assert triggers is not None
    assert "push" in triggers
    assert "pull_request" in triggers


def test_test_job_uses_postgres_16_alpine_service(
    workflow_text: str, workflow: dict[Any, Any]
) -> None:
    assert "postgres:16-alpine" in workflow_text
    job = workflow["jobs"]["test"]
    assert job["runs-on"] == "ubuntu-latest"
    postgres = job["services"]["postgres"]
    assert postgres["image"] == "postgres:16-alpine"
    env = postgres["env"]
    assert env["POSTGRES_USER"] == "sea"
    assert env["POSTGRES_PASSWORD"] == "sea"
    assert env["POSTGRES_DB"] == "sea_test"
    assert "5432:5432" in [str(p) for p in postgres["ports"]]
    assert "pg_isready" in postgres["options"]


def test_test_job_runs_quality_gates_and_pytest(
    workflow_text: str, workflow: dict[Any, Any]
) -> None:
    assert "pytest -q" in workflow_text
    commands = _run_commands(workflow, "test")
    assert 'pip install -e ".[dev]"' in commands
    assert "ruff check . --output-format=concise" in commands
    assert "mypy app" in commands
    assert "pytest -q" in commands
    setup_python = [s for s in _steps(workflow, "test") if "setup-python" in str(s.get("uses"))]
    assert setup_python
    assert str(setup_python[0]["with"]["python-version"]) == "3.12"


def test_pytest_step_points_to_ci_postgres(workflow_text: str, workflow: dict[Any, Any]) -> None:
    assert "TEST_DATABASE_URL" in workflow_text
    pytest_steps = [s for s in _steps(workflow, "test") if "pytest -q" in str(s.get("run", ""))]
    assert len(pytest_steps) == 1
    assert pytest_steps[0]["env"]["TEST_DATABASE_URL"] == EXPECTED_TEST_DB_URL


def test_junit_report_uploaded_always(workflow: dict[Any, Any]) -> None:
    uploads = [
        s for s in _steps(workflow, "test") if "actions/upload-artifact" in str(s.get("uses"))
    ]
    assert len(uploads) == 1
    assert uploads[0]["if"] == "always()"
    assert uploads[0]["with"]["path"] == "reports/junit.xml"


def test_docker_job_builds_api_image(workflow: dict[Any, Any]) -> None:
    commands = _run_commands(workflow, "docker")
    assert "cp .env.example .env" in commands
    assert "docker compose build api" in commands


def test_workflow_has_no_deploy_or_secrets(workflow_text: str) -> None:
    lowered = workflow_text.lower()
    assert "deploy" not in lowered
    assert "secrets." not in lowered


def test_readme_documents_startup_and_no_auth_warning(readme: str) -> None:
    assert "docker compose up -d --build" in readme
    assert "cp .env.example .env" in readme
    assert "http://localhost:8000/docs" in readme
    assert "sem autenticação" in readme.lower()


def test_readme_documents_env_vars_csv_layout_and_tests(readme: str) -> None:
    for var in (
        "DATABASE_URL",
        "DEFAULT_CURRENCY",
        "MAX_UPLOAD_MB",
        "ANOMALY_IQR_K",
        "ANOMALY_MIN_SAMPLE",
        "LOG_LEVEL",
    ):
        assert f"`{var}`" in readme
    assert "date,description,amount,merchant,currency" in readme
    assert 'pip install -e ".[dev]"' in readme
    assert "pytest -q" in readme
    assert "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE" in readme

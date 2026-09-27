import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, load_settings_or_exit

ENV_VARS = (
    "DATABASE_URL",
    "DEFAULT_CURRENCY",
    "MAX_UPLOAD_MB",
    "ANOMALY_IQR_K",
    "ANOMALY_MIN_SAMPLE",
    "LOG_LEVEL",
)
DB_URL = "postgresql+psycopg://u:segredo@h/db"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Sem variáveis do ambiente real e sem .env do repositório."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def _critical_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.CRITICAL]


def test_defaults_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)

    settings = load_settings_or_exit()

    assert settings.database_url == DB_URL
    assert settings.max_upload_mb == 10
    assert settings.anomaly_iqr_k == 1.5
    assert settings.anomaly_min_sample == 8
    assert settings.default_currency == "BRL"
    assert settings.log_level == "INFO"


def test_missing_database_url_exits_with_code_1_and_names_variable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as exc:
        load_settings_or_exit()

    assert exc.value.code == 1
    messages = _critical_messages(caplog)
    assert any(
        m.startswith("Configuração inválida: DATABASE_URL ") for m in messages
    ), messages


def test_invalid_default_currency_exits_and_names_variable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("DEFAULT_CURRENCY", "XYZ")

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as exc:
        load_settings_or_exit()

    assert exc.value.code == 1
    messages = _critical_messages(caplog)
    assert any("Configuração inválida: DEFAULT_CURRENCY " in m for m in messages), messages
    assert not any("XYZ" in m for m in messages)


def test_default_currency_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("DEFAULT_CURRENCY", " usd ")

    assert load_settings_or_exit().default_currency == "USD"


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("MAX_UPLOAD_MB", "0"),
        ("MAX_UPLOAD_MB", "-1"),
        ("ANOMALY_MIN_SAMPLE", "1"),
        ("ANOMALY_IQR_K", "0"),
        ("ANOMALY_IQR_K", "abc"),
        ("LOG_LEVEL", "VERBOSE"),
    ],
)
def test_out_of_range_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    var: str,
    value: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv(var, value)

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as exc:
        load_settings_or_exit()

    assert exc.value.code == 1
    assert any(f"Configuração inválida: {var} " in m for m in _critical_messages(caplog))


def test_settings_raises_validation_error_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("ANOMALY_MIN_SAMPLE", "1")

    with pytest.raises(ValidationError):
        Settings()


def test_accepts_boundary_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("ANOMALY_MIN_SAMPLE", "2")
    monkeypatch.setenv("ANOMALY_IQR_K", "3.0")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = load_settings_or_exit()

    assert settings.max_upload_mb == 1
    assert settings.anomaly_min_sample == 2
    assert settings.anomaly_iqr_k == 3.0
    assert settings.log_level == "DEBUG"


def test_log_never_contains_secret_values(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    monkeypatch.setenv("DEFAULT_CURRENCY", "XYZ")

    with caplog.at_level(logging.DEBUG), pytest.raises(SystemExit):
        load_settings_or_exit()

    assert len(_critical_messages(caplog)) == 2
    assert "segredo" not in caplog.text
    assert DB_URL not in caplog.text


def test_reads_dotenv_file_and_ignores_unknown_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        f"DATABASE_URL={DB_URL}\nDEFAULT_CURRENCY=eur\nPOSTGRES_PASSWORD=x\n",
        encoding="utf-8",
    )

    settings = load_settings_or_exit()

    assert settings.database_url == DB_URL
    assert settings.default_currency == "EUR"

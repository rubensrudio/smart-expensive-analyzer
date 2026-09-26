"""Migration 0001 aplicada pelo Alembic contra PostgreSQL real (CT-5; SEA-01, SEA-52)."""

import io
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.infrastructure.db.models import Base

EXPECTED_TABLES = {
    "categories",
    "categorization_rules",
    "imports",
    "import_rejections",
    "transactions",
    "anomalies",
}

_DEDUP_KEY = "a" * 64


def _app_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) & EXPECTED_TABLES


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)


@pytest.fixture
def alembic_cfg(
    postgres_url: str, alembic_config_factory: Callable[[str | None], Config]
) -> Iterator[Config]:
    cfg = alembic_config_factory(postgres_url)
    yield cfg
    # Garante o schema em head para os próximos testes, mesmo se o teste falhar no meio.
    command.upgrade(cfg, "head")


def test_upgrade_head_creates_all_tables_and_default_category(engine: Engine) -> None:
    assert _app_tables(engine) == EXPECTED_TABLES
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        defaults = conn.execute(text("SELECT name FROM categories WHERE is_default")).scalars()
        assert version == "0001"
        assert list(defaults) == ["Não categorizada"]


def test_downgrade_base_removes_tables_and_upgrade_again_works(
    engine: Engine, alembic_cfg: Config
) -> None:
    command.downgrade(alembic_cfg, "base")
    assert _app_tables(engine) == set()

    command.upgrade(alembic_cfg, "head")
    assert _app_tables(engine) == EXPECTED_TABLES
    with engine.connect() as conn:
        defaults = conn.execute(text("SELECT name FROM categories WHERE is_default")).scalars()
        assert list(defaults) == ["Não categorizada"]


def test_category_name_is_unique_case_insensitive(engine: Engine) -> None:
    with pytest.raises(IntegrityError) as exc_info, engine.begin() as conn:
        conn.execute(text("INSERT INTO categories (name) VALUES ('NÃO CATEGORIZADA')"))
    assert _constraint_name(exc_info.value) == "uq_categories_name_ci"


def test_only_one_default_category_allowed(engine: Engine) -> None:
    with pytest.raises(IntegrityError) as exc_info, engine.begin() as conn:
        conn.execute(text("INSERT INTO categories (name, is_default) VALUES ('Outra', true)"))
    assert _constraint_name(exc_info.value) == "uq_categories_default"


def test_duplicate_dedup_key_violates_unique_constraint(engine: Engine) -> None:
    with engine.begin() as conn:
        category_id = conn.execute(text("SELECT id FROM categories WHERE is_default")).scalar_one()
        import_id = conn.execute(
            text(
                "INSERT INTO imports (filename, file_sha256, status) "
                "VALUES ('a.csv', :sha, 'concluida') RETURNING id"
            ),
            {"sha": "b" * 64},
        ).scalar_one()

    insert_tx = text(
        "INSERT INTO transactions "
        "(import_id, date, description, merchant, amount, currency, type, category_id, dedup_key) "
        "VALUES (:import_id, '2026-01-10', 'Mercado', 'Mercado', -10.50, 'BRL', 'despesa', "
        ":category_id, :dedup_key)"
    )
    params = {"import_id": import_id, "category_id": category_id, "dedup_key": _DEDUP_KEY}
    with engine.begin() as conn:
        conn.execute(insert_tx, params)

    with pytest.raises(IntegrityError) as exc_info, engine.begin() as conn:
        conn.execute(insert_tx, params)
    assert _constraint_name(exc_info.value) == "uq_transactions_dedup_key"


def test_check_constraints_reject_invalid_values(engine: Engine) -> None:
    with pytest.raises(IntegrityError) as exc_info, engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO imports (filename, file_sha256, status) "
                "VALUES ('a.csv', :sha, 'invalido')"
            ),
            {"sha": "c" * 64},
        )
    assert _constraint_name(exc_info.value) == "ck_imports_status"


def test_migrated_schema_matches_orm_models(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_offline_mode_uses_database_url_from_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    alembic_config_factory: Callable[[str | None], Config],
) -> None:
    monkeypatch.chdir(tmp_path)  # sem .env no diretório corrente
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    buffer = io.StringIO()
    cfg = alembic_config_factory(None)
    cfg.output_buffer = buffer

    command.upgrade(cfg, "head", sql=True)

    sql = buffer.getvalue()
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE {table}" in sql
    assert "Não categorizada" in sql

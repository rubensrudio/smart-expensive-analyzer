"""Fixtures compartilhadas dos testes de integração (CT-23, DA-14).

Único `conftest.py` do projeto. Todas as fixtures usam o mesmo `postgres_url` e a
mesma `engine`, então o que um teste grava por uma fixture é visto pelas outras.
O schema vem só do Alembic (`upgrade head`), nunca de `Base.metadata.create_all`.
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import Settings
from app.infrastructure.db.session import create_engine_from_url, create_session_factory

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.domain.ports import UnitOfWork

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_IMAGE = "postgres:16-alpine"

_CLEAN_TABLES_SQL = (
    "TRUNCATE anomalies, transactions, import_rejections, imports, categorization_rules "
    "RESTART IDENTITY CASCADE"
)
_CLEAN_CATEGORIES_SQL = "DELETE FROM categories WHERE NOT is_default"


def _make_alembic_config(database_url: str | None = None) -> Config:
    """Config do Alembic independente do diretório corrente e sem configurar logging.

    Não lê o `alembic.ini`: o `fileConfig` dele trocaria o logging global da sessão de
    testes (nível do root e handlers), o que atrapalha o `caplog` dos outros testes.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    if database_url is not None:
        # ConfigParser interpola "%": escapar para URLs com senha codificada.
        cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


@pytest.fixture
def alembic_config_factory() -> Callable[[str | None], Config]:
    """Fábrica de `Config` do Alembic para testes que rodam comandos de migration."""
    return _make_alembic_config


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    external_url = os.environ.get("TEST_DATABASE_URL")
    if external_url:
        yield external_url
        return

    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def engine(postgres_url: str) -> Iterator[Engine]:
    command.upgrade(_make_alembic_config(postgres_url), "head")
    db_engine = create_engine_from_url(postgres_url)
    yield db_engine
    db_engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def settings(postgres_url: str) -> Settings:
    return Settings(database_url=postgres_url, _env_file=None)


@pytest.fixture(autouse=True)
def clean_db(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(text(_CLEAN_TABLES_SQL))
        conn.execute(text(_CLEAN_CATEGORIES_SQL))


@pytest.fixture
def uow_factory(session_factory: sessionmaker[Session]) -> Callable[[], "UnitOfWork"]:
    # Import tardio: o módulo só existe a partir da TASK-010.
    from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

    return lambda: SqlAlchemyUnitOfWork(session_factory)


@pytest.fixture
def uow(uow_factory: Callable[[], "UnitOfWork"]) -> Iterator["UnitOfWork"]:
    with uow_factory() as u:
        yield u


@pytest.fixture
def client(settings: Settings) -> Iterator["TestClient"]:
    # Import tardio: `create_app` só existe a partir da TASK-012.
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as c:
        yield c

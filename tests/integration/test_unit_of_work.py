"""Unit of Work SQLAlchemy e providers de DI (CT-9, DA-2, DA-3).

Requisito: SEA-97.
"""

from collections.abc import Callable, Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_settings, get_uow, get_uow_factory
from app.core.config import Settings
from app.domain.ports import UnitOfWork
from app.infrastructure.db.repositories.anomalies import SqlAlchemyAnomalyRepository
from app.infrastructure.db.repositories.categories import SqlAlchemyCategoryRepository
from app.infrastructure.db.repositories.categorization_rules import (
    SqlAlchemyCategorizationRuleRepository,
)
from app.infrastructure.db.repositories.imports import SqlAlchemyImportRepository
from app.infrastructure.db.repositories.transactions import SqlAlchemyTransactionRepository
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

UoWFactory = Callable[[], UnitOfWork]


class _Boom(Exception):
    pass


def _exists(uow_factory: UoWFactory, name: str) -> bool:
    with uow_factory() as fresh:
        return fresh.categories.get_by_name_ci(name) is not None


def test_enter_exposes_five_repositories_sharing_one_session(uow_factory: UoWFactory) -> None:
    with uow_factory() as uow:
        assert isinstance(uow.categories, SqlAlchemyCategoryRepository)
        assert isinstance(uow.rules, SqlAlchemyCategorizationRuleRepository)
        assert isinstance(uow.transactions, SqlAlchemyTransactionRepository)
        assert isinstance(uow.imports, SqlAlchemyImportRepository)
        assert isinstance(uow.anomalies, SqlAlchemyAnomalyRepository)
        sessions = {
            id(repo._session)  # checagem de que a sessão é única
            for repo in (uow.categories, uow.rules, uow.transactions, uow.imports, uow.anomalies)
        }
        assert len(sessions) == 1


def test_exit_without_commit_discards_changes(uow_factory: UoWFactory) -> None:
    with uow_factory() as uow:
        uow.categories.add("Mercado")

    assert not _exists(uow_factory, "Mercado")


def test_commit_persists_changes(uow_factory: UoWFactory) -> None:
    with uow_factory() as uow:
        uow.categories.add("Mercado")
        uow.commit()

    assert _exists(uow_factory, "Mercado")


def test_exception_rolls_back_and_propagates(uow_factory: UoWFactory) -> None:
    with pytest.raises(_Boom), uow_factory() as uow:
        uow.categories.add("Mercado")
        raise _Boom

    assert not _exists(uow_factory, "Mercado")


def test_exception_after_commit_keeps_committed_work_only(uow_factory: UoWFactory) -> None:
    with pytest.raises(_Boom), uow_factory() as uow:
        uow.categories.add("Mercado")
        uow.commit()
        uow.categories.add("Lazer")
        raise _Boom

    assert _exists(uow_factory, "Mercado")
    assert not _exists(uow_factory, "Lazer")


def test_explicit_rollback_discards_pending_changes(uow_factory: UoWFactory) -> None:
    with uow_factory() as uow:
        uow.categories.add("Mercado")
        uow.rollback()
        uow.categories.add("Lazer")
        uow.commit()

    assert not _exists(uow_factory, "Mercado")
    assert _exists(uow_factory, "Lazer")


def test_session_is_closed_on_exit(session_factory: sessionmaker[Session]) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)
    with uow:
        session = uow.categories._session
        uow.categories.list_all()
        assert session.in_transaction()

    assert not session.in_transaction()


def test_commit_outside_context_raises(session_factory: sessionmaker[Session]) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)
    with pytest.raises(RuntimeError):
        uow.commit()


# --- providers de DI (app/api/deps.py) ---------------------------------------------------


@pytest.fixture
def deps_client(settings: Settings, session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.state.settings = settings
    app.state.session_factory = session_factory

    @app.get("/settings")
    def read_settings(s: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
        return {"default_currency": s.default_currency, "same": str(s is settings)}

    @app.post("/uow/{name}")
    def add_with_uow(
        name: str, uow: Annotated[UnitOfWork, Depends(get_uow)], commit: bool = False
    ) -> None:
        uow.categories.add(name)
        if commit:
            uow.commit()

    @app.post("/factory/{name}")
    def add_with_factory(
        name: str, factory: Annotated[UoWFactory, Depends(get_uow_factory)]
    ) -> None:
        with factory() as uow:
            uow.categories.add(name)
            uow.commit()

    with TestClient(app) as client:
        yield client


def test_get_settings_reads_app_state(deps_client: TestClient) -> None:
    response = deps_client.get("/settings")

    assert response.status_code == 200
    assert response.json() == {"default_currency": "BRL", "same": "True"}


def test_get_uow_commits_only_when_route_commits(
    deps_client: TestClient, uow_factory: UoWFactory
) -> None:
    assert deps_client.post("/uow/Mercado").status_code == 200
    assert deps_client.post("/uow/Lazer?commit=true").status_code == 200

    assert not _exists(uow_factory, "Mercado")
    assert _exists(uow_factory, "Lazer")


def test_get_uow_factory_builds_uow_on_app_session_factory(
    deps_client: TestClient, uow_factory: UoWFactory
) -> None:
    assert deps_client.post("/factory/Saude").status_code == 200

    assert _exists(uow_factory, "Saude")

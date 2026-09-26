"""Providers de injeção de dependência (CT-9, DA-3).

Lêem `request.app.state.settings` e `request.app.state.session_factory`, que o
`create_app` preenche. Providers de serviço ficam em cada router (DA-3).
"""

from collections.abc import Callable, Iterator
from typing import cast

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.domain.ports import UnitOfWork
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


def _session_factory(request: Request) -> sessionmaker[Session]:
    return cast(sessionmaker[Session], request.app.state.session_factory)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_uow(request: Request) -> Iterator[UnitOfWork]:
    """UoW aberto durante o request. Sem `commit()` da rota, nada é gravado."""
    with SqlAlchemyUnitOfWork(_session_factory(request)) as uow:
        yield uow


def get_uow_factory(request: Request) -> Callable[[], UnitOfWork]:
    """Fábrica para serviços que abrem mais de um UoW (ex.: import, DA-16)."""
    session_factory = _session_factory(request)

    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory

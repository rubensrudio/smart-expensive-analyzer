"""Dependências comuns de query da API: período e paginação (CT-22).

P-10 / SEA-57: limites de período opcionais; sem filtro = todo o histórico.
SEA-105: `limit`/`offset` chegam como `int` sem restrição no `Query` e são
validados aqui, para responder `INVALID_PAGINATION` com a mensagem do catálogo
em vez do `VALIDATION_ERROR` genérico.
"""

from datetime import date
from typing import Annotated

from fastapi import Query

from app.core.errors import InvalidPaginationError, InvalidPeriodError
from app.domain.entities import Page, Period

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def period_params(
    start_date: Annotated[
        date | None, Query(description="Data inicial (AAAA-MM-DD), inclusiva.")
    ] = None,
    end_date: Annotated[
        date | None, Query(description="Data final (AAAA-MM-DD), inclusiva.")
    ] = None,
) -> Period:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise InvalidPeriodError()
    return Period(start=start_date, end=end_date)


def pagination_params(
    limit: Annotated[
        int, Query(description=f"Itens por página (1 a {MAX_LIMIT}).")
    ] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(description="Quantidade de itens a pular (>= 0).")] = 0,
) -> Page:
    if not 1 <= limit <= MAX_LIMIT or offset < 0:
        raise InvalidPaginationError()
    return Page(limit=limit, offset=offset)

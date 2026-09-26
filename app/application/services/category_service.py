"""Serviço de Category (CT-18). Requisitos: SEA-15, SEA-16, SEA-51, SEA-53.

Só criação e listagem (LAC-09): edição e exclusão de Category estão fora de escopo.
"""

import builtins

from sqlalchemy.exc import IntegrityError

from app.core.errors import CategoryAlreadyExistsError, CategoryNameRequiredError
from app.domain.entities import Category
from app.domain.ports import UnitOfWork
from app.domain.text import normalize_whitespace

# Índice único `lower(name)` da migration 0001 (LAC-19).
_NAME_CI_CONSTRAINT = "uq_categories_name_ci"


def _is_name_ci_violation(error: IntegrityError) -> bool:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == _NAME_CI_CONSTRAINT


class CategoryService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def create(self, name: str | None) -> Category:
        normalized = normalize_whitespace(name) if name is not None else ""
        if not normalized:
            raise CategoryNameRequiredError()
        if self._uow.categories.get_by_name_ci(normalized) is not None:
            raise CategoryAlreadyExistsError()
        try:
            category = self._uow.categories.add(normalized)
            self._uow.commit()
        except IntegrityError as exc:
            # Corrida: outra requisição gravou o mesmo nome depois da checagem.
            self._uow.rollback()
            if _is_name_ci_violation(exc):
                raise CategoryAlreadyExistsError() from exc
            raise
        return category

    def list(self) -> builtins.list[Category]:
        return self._uow.categories.list_all()

"""Repositório SQLAlchemy de Category (CT-8, cumpre `CategoryRepository` de CT-7).

Não faz commit: a transação é do Unit of Work. `add` com nome duplicado (sem
distinguir caixa) propaga `IntegrityError`; a tradução é do serviço.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities import Category
from app.infrastructure.db.models import CategoryModel


def _to_entity(model: CategoryModel) -> Category:
    return Category(id=model.id, name=model.name, is_default=model.is_default)


class SqlAlchemyCategoryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, name: str) -> Category:
        model = CategoryModel(name=name, is_default=False)
        self._session.add(model)
        self._session.flush()
        return _to_entity(model)

    def get(self, category_id: int) -> Category | None:
        model = self._session.get(CategoryModel, category_id)
        return _to_entity(model) if model is not None else None

    def get_by_name_ci(self, name: str) -> Category | None:
        stmt = select(CategoryModel).where(func.lower(CategoryModel.name) == name.strip().lower())
        model = self._session.scalars(stmt).one_or_none()
        return _to_entity(model) if model is not None else None

    def get_default(self) -> Category:
        # Seed da migration 0001 garante exatamente uma (índice único parcial).
        stmt = select(CategoryModel).where(CategoryModel.is_default.is_(True))
        return _to_entity(self._session.scalars(stmt).one())

    def list_all(self) -> list[Category]:
        stmt = select(CategoryModel).order_by(CategoryModel.name, CategoryModel.id)
        return [_to_entity(model) for model in self._session.scalars(stmt)]

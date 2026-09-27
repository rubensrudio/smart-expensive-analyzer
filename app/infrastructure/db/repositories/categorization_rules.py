"""Repositório SQLAlchemy de CategorizationRule (CT-8, cumpre `CategorizationRuleRepository`).

Não faz commit: a transação é do Unit of Work. `list_all` segue a ordem de
avaliação das regras: `priority`, `created_at`, `id` (SEA-47).
`update` e `delete` são um único comando SQL cada (achado QA TASK-027-1): sem o
"get, altera, flush", uma exclusão concorrente não gera `StaleDataError` (500).
Nenhuma linha casada vira `None`/`False`, e o serviço responde 404.
"""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.domain.entities import CategorizationRule
from app.infrastructure.db.models import CategorizationRuleModel


def _to_entity(model: CategorizationRuleModel) -> CategorizationRule:
    return CategorizationRule(
        id=model.id,
        keyword=model.keyword,
        category_id=model.category_id,
        priority=model.priority,
        created_at=model.created_at,
    )


class SqlAlchemyCategorizationRuleRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, keyword: str, category_id: int, priority: int) -> CategorizationRule:
        model = CategorizationRuleModel(keyword=keyword, category_id=category_id, priority=priority)
        self._session.add(model)
        self._session.flush()
        # `created_at` vem do server_default: recarrega para obtê-lo.
        self._session.refresh(model)
        return _to_entity(model)

    def get(self, rule_id: int) -> CategorizationRule | None:
        model = self._session.get(CategorizationRuleModel, rule_id)
        return _to_entity(model) if model is not None else None

    def list_all(self) -> list[CategorizationRule]:
        stmt = select(CategorizationRuleModel).order_by(
            CategorizationRuleModel.priority,
            CategorizationRuleModel.created_at,
            CategorizationRuleModel.id,
        )
        return [_to_entity(model) for model in self._session.scalars(stmt)]

    def update(
        self, rule_id: int, keyword: str, category_id: int, priority: int
    ) -> CategorizationRule | None:
        stmt = (
            update(CategorizationRuleModel)
            .where(CategorizationRuleModel.id == rule_id)
            .values(keyword=keyword, category_id=category_id, priority=priority)
            .returning(CategorizationRuleModel)
        )
        model = self._session.scalars(stmt).one_or_none()
        return _to_entity(model) if model is not None else None

    def delete(self, rule_id: int) -> bool:
        stmt = (
            delete(CategorizationRuleModel)
            .where(CategorizationRuleModel.id == rule_id)
            .returning(CategorizationRuleModel.id)
        )
        return self._session.scalars(stmt).one_or_none() is not None

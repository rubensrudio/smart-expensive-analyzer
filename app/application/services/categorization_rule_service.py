"""Serviço de CategorizationRule (CT-18). Requisitos: SEA-18, SEA-48, SEA-49, SEA-50, SEA-64.

Nunca toca transações: criar, alterar ou excluir regra não recategoriza nada
(SEA-64, LAC-11). A recategorização é sob demanda, em outro serviço.
"""

import builtins

from app.core.errors import RuleCategoryNotFoundError, RuleNotFoundError
from app.domain.entities import CategorizationRule
from app.domain.ports import UnitOfWork
from app.domain.text import normalize_whitespace


def _normalize_keyword(keyword: str) -> str:
    normalized = normalize_whitespace(keyword)
    if not normalized:
        # O schema da API já recusa com 422 (SEA-50); aqui é defesa de invariante.
        raise ValueError("keyword não pode ser vazia")
    return normalized


class CategorizationRuleService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def create(self, keyword: str, category_id: int, priority: int) -> CategorizationRule:
        normalized = _normalize_keyword(keyword)
        self._require_category(category_id)
        rule = self._uow.rules.add(normalized, category_id, priority)
        self._uow.commit()
        return rule

    def get(self, rule_id: int) -> CategorizationRule:
        rule = self._uow.rules.get(rule_id)
        if rule is None:
            raise RuleNotFoundError()
        return rule

    def list(self) -> builtins.list[CategorizationRule]:
        return self._uow.rules.list_all()

    def update(
        self, rule_id: int, keyword: str, category_id: int, priority: int
    ) -> CategorizationRule:
        normalized = _normalize_keyword(keyword)
        if self._uow.rules.get(rule_id) is None:
            raise RuleNotFoundError()
        self._require_category(category_id)
        rule = self._uow.rules.update(rule_id, normalized, category_id, priority)
        if rule is None:
            raise RuleNotFoundError()
        self._uow.commit()
        return rule

    def delete(self, rule_id: int) -> None:
        if not self._uow.rules.delete(rule_id):
            raise RuleNotFoundError()
        self._uow.commit()

    def _require_category(self, category_id: int) -> None:
        if self._uow.categories.get(category_id) is None:
            raise RuleCategoryNotFoundError()

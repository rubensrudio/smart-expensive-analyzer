"""Casamento determinístico de regras de categorização (CT-11, LAC-08, LAC-10)."""

from collections.abc import Sequence

from app.domain.entities import CategorizationRule
from app.domain.text import fold_for_match


class RuleMatcher:
    """Escolhe a Category de uma transação a partir das regras recebidas.

    As regras são ordenadas uma vez por ``(priority, created_at, id)``. A primeira
    cuja palavra-chave, dobrada por ``fold_for_match``, esteja contida na descrição
    ou no estabelecimento vence. Sem casamento, devolve a categoria padrão.
    """

    __slots__ = ("_default_category_id", "_ordered")

    def __init__(self, rules: Sequence[CategorizationRule], default_category_id: int) -> None:
        ordered = sorted(rules, key=lambda r: (r.priority, r.created_at, r.id))
        # Palavra-chave vazia casaria com tudo; é descartada por segurança.
        self._ordered: tuple[tuple[str, int], ...] = tuple(
            (folded, rule.category_id)
            for rule in ordered
            if (folded := fold_for_match(rule.keyword)).strip()
        )
        self._default_category_id = default_category_id

    def match(self, description: str, merchant: str) -> int:
        folded_description = fold_for_match(description)
        folded_merchant = fold_for_match(merchant)
        for keyword, category_id in self._ordered:
            if keyword in folded_description or keyword in folded_merchant:
                return category_id
        return self._default_category_id

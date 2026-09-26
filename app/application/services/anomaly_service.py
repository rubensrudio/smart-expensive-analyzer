"""Serviço de anomalias: recálculo e listagem (CT-16).

Requisitos: SEA-27, SEA-29, SEA-30, SEA-31, SEA-57, SEA-60; DA-7.
Não faz commit: a transação pertence a quem chama (import, recategorização).
"""

import builtins
import logging
from collections import Counter

from app.domain.anomaly_detection import detect_iqr_anomalies
from app.domain.entities import Anomaly, ExpenseFilters, ExpenseRecord, Period
from app.domain.ports import UnitOfWork

logger = logging.getLogger(__name__)


class AnomalyService:
    def __init__(self, uow: UnitOfWork, k: float, min_sample: int) -> None:
        self._uow = uow
        self._k = k
        self._min_sample = min_sample

    def recompute_all(self) -> int:
        """Recalcula sobre todo o histórico de despesas e substitui o conjunto (SEA-60).

        ``list_expenses`` só devolve despesas (SEA-29). ``replace_all`` apaga e
        regrava sob advisory lock, sem duplicar (SEA-30). Retorna a quantidade.
        """
        expenses = self._uow.transactions.list_expenses(ExpenseFilters())
        candidates = detect_iqr_anomalies(expenses, self._k, self._min_sample)
        self._uow.anomalies.replace_all(candidates)
        logger.info(
            "anomalies_recomputed count=%d groups_evaluated=%d",
            len(candidates),
            self._groups_evaluated(expenses),
        )
        return len(candidates)

    def list(self, period: Period) -> builtins.list[Anomaly]:
        """Período vazio = todo o histórico (SEA-57); intervalo fechado (SEA-31)."""
        return self._uow.anomalies.list(period)

    def _groups_evaluated(self, expenses: builtins.list[ExpenseRecord]) -> int:
        sizes = Counter((e.category_id, e.currency) for e in expenses)
        return sum(1 for size in sizes.values() if size >= self._min_sample)

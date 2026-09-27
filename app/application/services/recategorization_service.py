"""Serviço de recategorização sob demanda (CT-20, LAC-11).

Requisitos: SEA-63, SEA-65, SEA-66, SEA-109.

AS-3: o log carrega só contagens, nunca descrição, estabelecimento ou valor.
"""

import logging
from dataclasses import dataclass

from app.application.services.anomaly_service import AnomalyService
from app.core.config import Settings
from app.domain.categorization import RuleMatcher
from app.domain.ports import UnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RecategorizationResult:
    evaluated: int
    changed: int


class RecategorizationService:
    """Reaplica as regras atuais a todas as transações, dentro do UoW recebido."""

    def __init__(self, uow: UnitOfWork, settings: Settings) -> None:
        self._uow = uow
        self._settings = settings

    def recategorize(self) -> RecategorizationResult:
        """Reavalia, grava só o que mudou, recalcula anomalias (SEA-65) e faz commit.

        Rodar de novo sem mudar regras não altera nada (SEA-66). Sem transações,
        devolve ``(0, 0)`` (SEA-109). Em erro, o ``__exit__`` do UoW faz rollback.
        """
        uow = self._uow
        matcher = RuleMatcher(uow.rules.list_all(), uow.categories.get_default().id)
        transactions = uow.transactions.list_all_for_categorization()

        new_category = {tx.id: matcher.match(tx.description, tx.merchant) for tx in transactions}
        # Updates em ordem crescente de id: escritas concorrentes travam as linhas
        # na mesma ordem e não entram em deadlock (lição da TASK-019).
        changes = {
            tx_id: new_category[tx_id]
            for tx_id in sorted(
                tx.id for tx in transactions if new_category[tx.id] != tx.category_id
            )
        }
        uow.transactions.update_categories(changes)

        AnomalyService(
            uow, self._settings.anomaly_iqr_k, self._settings.anomaly_min_sample
        ).recompute_all()
        uow.commit()

        result = RecategorizationResult(evaluated=len(transactions), changed=len(changes))
        logger.info(
            "recategorization_finished evaluated=%d changed=%d",
            result.evaluated,
            result.changed,
        )
        return result

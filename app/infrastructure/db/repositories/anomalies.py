"""Repositório SQLAlchemy de Anomaly (CT-25; SEA-27, SEA-30, SEA-31; DA-7).

Não faz commit: a transação pertence ao ``UnitOfWork`` (DA-2).
"""

import builtins
from collections.abc import Sequence

from sqlalchemy import delete, insert, select, text
from sqlalchemy.orm import Session

from app.domain.entities import Anomaly, AnomalyCandidate, Period, Transaction, TransactionType
from app.infrastructure.db.models import AnomalyModel, CategoryModel, TransactionModel

# Chave do advisory lock transacional que serializa o recálculo de anomalias (DA-7).
ANOMALY_LOCK_KEY = 815001

_LOCK_SQL = text("SELECT pg_advisory_xact_lock(:key)")


class SqlAlchemyAnomalyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_all(self, candidates: Sequence[AnomalyCandidate]) -> None:
        """Substitui o conjunto inteiro sob lock, na transação do caller (DA-7)."""
        self._session.execute(_LOCK_SQL, {"key": ANOMALY_LOCK_KEY})
        self._session.execute(delete(AnomalyModel))
        if candidates:
            self._session.execute(
                insert(AnomalyModel),
                [
                    {
                        "transaction_id": c.transaction_id,
                        "method": c.method,
                        "value": c.value,
                        "reason": c.reason,
                    }
                    for c in candidates
                ],
            )

    def list(self, period: Period) -> builtins.list[Anomaly]:
        stmt = (
            select(AnomalyModel, TransactionModel, CategoryModel.name)
            .join(TransactionModel, AnomalyModel.transaction_id == TransactionModel.id)
            .join(CategoryModel, TransactionModel.category_id == CategoryModel.id)
            .order_by(TransactionModel.date.desc(), AnomalyModel.id.desc())
        )
        if period.start is not None:
            stmt = stmt.where(TransactionModel.date >= period.start)
        if period.end is not None:
            stmt = stmt.where(TransactionModel.date <= period.end)

        return [
            Anomaly(
                id=anomaly.id,
                method=anomaly.method,
                value=anomaly.value,
                reason=anomaly.reason,
                transaction=Transaction(
                    id=tx.id,
                    date=tx.date,
                    description=tx.description,
                    merchant=tx.merchant,
                    amount=tx.amount,
                    currency=tx.currency,
                    type=TransactionType(tx.type),
                    category_id=tx.category_id,
                    category_name=category_name,
                    import_id=tx.import_id,
                ),
            )
            for anomaly, tx, category_name in self._session.execute(stmt).tuples()
        ]

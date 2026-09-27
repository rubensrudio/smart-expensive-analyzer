"""Schemas de `GET /anomalies` (contrato 8.1; SEA-27).

A resposta expõe só `id`, `method`, `value`, `reason` e `transaction` (TransactionOut).
`value` passa por `money()` (P-15, HALF_UP) antes do `Money` (P-13, string com 2 casas),
então nunca sai com mais de 2 casas nem com o arredondamento do `format`.
"""

from pydantic import BaseModel

from app.api.schemas.common import Money, TransactionOut
from app.domain.entities import Anomaly
from app.domain.statistics import money


class AnomalyOut(BaseModel):
    id: int
    method: str
    value: Money
    reason: str
    transaction: TransactionOut

    @classmethod
    def from_entity(cls, anomaly: Anomaly) -> "AnomalyOut":
        return cls(
            id=anomaly.id,
            method=anomaly.method,
            value=money(anomaly.value),
            reason=anomaly.reason,
            transaction=TransactionOut.from_entity(anomaly.transaction),
        )


class AnomalyListOut(BaseModel):
    items: list[AnomalyOut]

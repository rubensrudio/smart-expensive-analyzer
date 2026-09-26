"""Detecção de anomalias por IQR (CT-15, P-16, SEA-28, SEA-54, SEA-58, SEA-59).

Função pura, sem I/O. Recebe só despesas com ``value`` em módulo (SEA-29 é
garantido por ``list_expenses``). Agrupa por (categoria, moeda) e marca a
despesa com ``valor > Q3 + k·IQR`` do seu grupo. Quartis e comparação em
``float`` (P-16); números exibidos e persistidos passam por ``money`` (P-15).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal
from typing import Final

import numpy as np
import pandas as pd

from app.domain.entities import AnomalyCandidate, ExpenseRecord
from app.domain.statistics import money

IQR_METHOD: Final = "IQR"

_REASON: Final = (
    "Valor {value} {currency} acima do limite IQR {limit} "
    "(Q3 {q3} + {k} × IQR {iqr}) na categoria {category}, grupo de {n} despesas."
)


def detect_iqr_anomalies(
    records: Sequence[ExpenseRecord], k: float, min_sample: int
) -> list[AnomalyCandidate]:
    """Candidatos a anomalia ordenados por ``transaction_id``.

    Grupo com menos de ``min_sample`` despesas não é avaliado (SEA-59).
    ``k`` precisa ser finito e > 0; ``min_sample`` precisa ser >= 1.
    """
    _validate(k, min_sample)
    if not records:
        return []

    frame = pd.DataFrame(
        {
            "position": range(len(records)),
            "category_id": [r.category_id for r in records],
            "currency": [r.currency for r in records],
            "value": [float(r.value) for r in records],
        }
    )

    candidates: list[AnomalyCandidate] = []
    for _, group in frame.groupby(["category_id", "currency"], sort=True):
        size = len(group)
        if size < min_sample:
            continue
        q1, q3 = (float(q) for q in np.percentile(group["value"], [25, 75], method="linear"))
        iqr = q3 - q1
        limit = q3 + k * iqr
        for position, value in zip(group["position"], group["value"], strict=True):
            if value > limit:
                record = records[int(position)]
                candidates.append(_candidate(record, limit, q3, iqr, k, size))

    candidates.sort(key=lambda c: c.transaction_id)
    return candidates


def _validate(k: float, min_sample: int) -> None:
    if not math.isfinite(k) or k <= 0:
        raise ValueError(f"k must be a finite number > 0, got {k!r}")
    if min_sample < 1:
        raise ValueError(f"min_sample must be >= 1, got {min_sample!r}")


def _candidate(
    record: ExpenseRecord, limit: float, q3: float, iqr: float, k: float, size: int
) -> AnomalyCandidate:
    limit_money = _to_money(limit)
    reason = _REASON.format(
        value=money(record.value),
        currency=record.currency,
        limit=limit_money,
        q3=_to_money(q3),
        k=k,
        iqr=_to_money(iqr),
        category=record.category_name,
        n=size,
    )
    return AnomalyCandidate(
        transaction_id=record.transaction_id,
        method=IQR_METHOD,
        value=limit_money,
        reason=reason,
    )


def _to_money(value: float) -> Decimal:
    # repr curto do float evita que 2.675 vire 2.67499... antes do HALF_UP.
    return money(Decimal(repr(value)))

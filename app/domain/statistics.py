"""Estatísticas descritivas puras sobre ``Decimal`` (CT-13, DA-8, DA-9, P-15).

Sem I/O e sem agrupamento por moeda: quem chama entrega valores de uma
única moeda (SEA-54). Todo arredondamento é ``ROUND_HALF_UP`` em centavos e
acontece só no resultado final, nunca em valores intermediários.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from app.domain.entities import ExpenseRecord

_CENT = Decimal("0.01")
_ZERO = Decimal(0)
_HUNDRED_PERCENT_IN_CENTS = 10_000

HISTOGRAM_BOUNDS: tuple[Decimal, ...] = (Decimal(0), Decimal(50), Decimal(100), Decimal(500))


def money(value: Decimal) -> Decimal:
    """Quantiza em 2 casas com ``ROUND_HALF_UP`` (P-15)."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class SummaryStats:
    total: Decimal
    count: int
    mean: Decimal
    median: Decimal


@dataclass(frozen=True, slots=True)
class HistogramBucket:
    range_start: Decimal
    range_end: Decimal | None
    count: int
    total: Decimal


@dataclass(frozen=True, slots=True)
class MerchantTotal:
    merchant: str
    total: Decimal
    count: int


def summarize(values: Sequence[Decimal]) -> SummaryStats:
    """Total, quantidade, média e mediana (SEA-20, SEA-26). Vazio → tudo zero."""
    count = len(values)
    if count == 0:
        zero = money(_ZERO)
        return SummaryStats(total=zero, count=0, mean=zero, median=zero)

    total = sum(values, _ZERO)
    ordered = sorted(values)
    middle = count // 2
    median = ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return SummaryStats(
        total=money(total),
        count=count,
        mean=money(total / count),
        median=money(median),
    )


def histogram(values: Sequence[Decimal]) -> list[HistogramBucket]:
    """Sempre 4 faixas ``[a, b)`` de ``HISTOGRAM_BOUNDS``; a última é aberta (SEA-56)."""
    counts = [0] * len(HISTOGRAM_BOUNDS)
    totals = [_ZERO] * len(HISTOGRAM_BOUNDS)
    for value in values:
        if value < HISTOGRAM_BOUNDS[0]:
            raise ValueError(f"histogram value must be non-negative, got {value}")
        index = _bucket_index(value)
        counts[index] += 1
        totals[index] += value

    ends: list[Decimal | None] = [*HISTOGRAM_BOUNDS[1:], None]
    return [
        HistogramBucket(range_start=start, range_end=end, count=count, total=money(total))
        for start, end, count, total in zip(HISTOGRAM_BOUNDS, ends, counts, totals, strict=True)
    ]


def _bucket_index(value: Decimal) -> int:
    index = 0
    for position, start in enumerate(HISTOGRAM_BOUNDS):
        if value >= start:
            index = position
    return index


def percentages(totals: Sequence[Decimal]) -> list[Decimal]:
    """Percentual de cada total pelo maior resto em centésimos (DA-9, SEA-55).

    A soma é exatamente 100.00 quando o total geral é positivo. Empate de resto
    favorece o índice menor. Total geral zero → lista de zeros.
    """
    if any(total < _ZERO for total in totals):
        raise ValueError("percentages require non-negative totals")

    grand_total = sum(totals, _ZERO)
    if grand_total == _ZERO:
        return [money(_ZERO) for _ in totals]

    exact = [total * _HUNDRED_PERCENT_IN_CENTS / grand_total for total in totals]
    cents = [int(share.to_integral_value(rounding=ROUND_DOWN)) for share in exact]
    missing = _HUNDRED_PERCENT_IN_CENTS - sum(cents)
    by_remainder = sorted(range(len(totals)), key=lambda i: (-(exact[i] - cents[i]), i))
    for index in by_remainder[:missing]:
        cents[index] += 1

    return [money(Decimal(cent) * _CENT) for cent in cents]


def merchant_totals(records: Sequence[ExpenseRecord]) -> list[MerchantTotal]:
    """Total e quantidade por estabelecimento; total desc, merchant asc (SEA-22)."""
    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for record in records:
        totals[record.merchant] = totals.get(record.merchant, _ZERO) + record.value
        counts[record.merchant] = counts.get(record.merchant, 0) + 1

    result = [
        MerchantTotal(merchant=merchant, total=money(total), count=counts[merchant])
        for merchant, total in totals.items()
    ]
    result.sort(key=lambda item: (-item.total, item.merchant))
    return result

"""Série mensal de despesas por moeda (CT-14, P-11, SEA-32..34, SEA-54, SEA-62).

Função pura, sem I/O. Um único intervalo de meses vale para todas as moedas:
do mês de ``period.start`` (ou da despesa mais antiga) ao mês de
``period.end`` (ou da mais recente). Meses sem despesa entram com total 0.00
e count 0. Moedas nunca são somadas entre si.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.entities import ExpenseRecord, Period
from app.domain.statistics import money

_ZERO = Decimal(0)
_MONTHS_PER_YEAR = 12

# (ano, mês) — ordenável e sem ambiguidade de dia.
type _MonthKey = tuple[int, int]


@dataclass(frozen=True, slots=True)
class CategoryMonthTotal:
    category_id: int
    category_name: str
    total: Decimal
    count: int


@dataclass(frozen=True, slots=True)
class MonthPoint:
    month: str
    total: Decimal
    count: int
    by_category: list[CategoryMonthTotal]


@dataclass(frozen=True, slots=True)
class CurrencySeries:
    currency: str
    months: list[MonthPoint]


def monthly_series(records: Sequence[ExpenseRecord], period: Period) -> list[CurrencySeries]:
    """Série mensal contínua por moeda, moedas em ordem alfabética (P-11).

    Registros fora de ``period`` são ignorados. Sem despesas no escopo → ``[]``.
    """
    in_scope = [record for record in records if _in_period(record.date, period)]
    if not in_scope:
        return []

    first = _month_key(period.start) if period.start else min(_month_key(r.date) for r in in_scope)
    last = _month_key(period.end) if period.end else max(_month_key(r.date) for r in in_scope)
    months = _month_range(first, last)

    by_currency: dict[str, list[ExpenseRecord]] = {}
    for record in in_scope:
        by_currency.setdefault(record.currency, []).append(record)

    return [
        CurrencySeries(currency=currency, months=_series_for(by_currency[currency], months))
        for currency in sorted(by_currency)
    ]


def _series_for(records: Sequence[ExpenseRecord], months: list[_MonthKey]) -> list[MonthPoint]:
    by_month: dict[_MonthKey, list[ExpenseRecord]] = {}
    for record in records:
        by_month.setdefault(_month_key(record.date), []).append(record)

    return [_month_point(month, by_month.get(month, [])) for month in months]


def _month_point(month: _MonthKey, records: Sequence[ExpenseRecord]) -> MonthPoint:
    total = sum((record.value for record in records), _ZERO)
    return MonthPoint(
        month=f"{month[0]:04d}-{month[1]:02d}",
        total=money(total),
        count=len(records),
        by_category=_category_totals(records),
    )


def _category_totals(records: Sequence[ExpenseRecord]) -> list[CategoryMonthTotal]:
    """Total por categoria do mês; total desc, nome asc, id asc (SEA-34)."""
    totals: dict[int, Decimal] = {}
    counts: dict[int, int] = {}
    names: dict[int, str] = {}
    for record in records:
        totals[record.category_id] = totals.get(record.category_id, _ZERO) + record.value
        counts[record.category_id] = counts.get(record.category_id, 0) + 1
        names.setdefault(record.category_id, record.category_name)

    result = [
        CategoryMonthTotal(
            category_id=category_id,
            category_name=names[category_id],
            total=money(total),
            count=counts[category_id],
        )
        for category_id, total in totals.items()
    ]
    result.sort(key=lambda item: (-item.total, item.category_name, item.category_id))
    return result


def _in_period(day: date, period: Period) -> bool:
    if period.start is not None and day < period.start:
        return False
    return period.end is None or day <= period.end


def _month_key(day: date) -> _MonthKey:
    return (day.year, day.month)


def _month_range(first: _MonthKey, last: _MonthKey) -> list[_MonthKey]:
    """Meses de ``first`` a ``last`` inclusive; vazio se ``first > last``."""
    start_index = first[0] * _MONTHS_PER_YEAR + (first[1] - 1)
    end_index = last[0] * _MONTHS_PER_YEAR + (last[1] - 1)
    return [
        (index // _MONTHS_PER_YEAR, index % _MONTHS_PER_YEAR + 1)
        for index in range(start_index, end_index + 1)
    ]

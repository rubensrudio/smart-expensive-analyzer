"""Serviço de analytics: resumo, categorias e série mensal (CT-21).

Requisitos: SEA-20..SEA-25, SEA-54..SEA-57, SEA-61, SEA-62, SEA-95, SEA-101; DA-8.
Só leitura. O banco filtra as despesas (``list_expenses``); as estatísticas
são calculadas em Python com ``Decimal`` (DA-8). Cada moeda é um grupo
próprio, em ordem alfabética, e valores de moedas diferentes nunca são
somados (SEA-54). Escopo sem despesas → lista vazia (SEA-95).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.entities import ExpenseFilters, ExpenseRecord, Period
from app.domain.monthly_series import CurrencySeries, monthly_series
from app.domain.ports import UnitOfWork
from app.domain.statistics import (
    HistogramBucket,
    MerchantTotal,
    SummaryStats,
    histogram,
    merchant_totals,
    money,
    percentages,
    summarize,
)

_ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class CurrencySummary:
    currency: str
    stats: SummaryStats
    by_merchant: list[MerchantTotal]
    histogram: list[HistogramBucket]


@dataclass(frozen=True, slots=True)
class CategoryBreakdown:
    category_id: int
    category_name: str
    stats: SummaryStats
    percentage: Decimal


@dataclass(frozen=True, slots=True)
class CurrencyCategories:
    currency: str
    total: Decimal
    categories: list[CategoryBreakdown]


class AnalyticsService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def summary(self, filters: ExpenseFilters) -> list[CurrencySummary]:
        """Estatísticas, estabelecimentos e histograma por moeda (SEA-20..22, SEA-56)."""
        expenses = self._uow.transactions.list_expenses(filters)
        return [
            _currency_summary(currency, records)
            for currency, records in _group_by_currency(expenses)
        ]

    def categories(self, period: Period) -> list[CurrencyCategories]:
        """Estatística e percentual por categoria dentro de cada moeda (SEA-23, SEA-55)."""
        expenses = self._uow.transactions.list_expenses(ExpenseFilters(period=period))
        return [
            _currency_categories(currency, records)
            for currency, records in _group_by_currency(expenses)
        ]

    def monthly(self, period: Period) -> list[CurrencySeries]:
        """Série mensal por moeda (SEA-61, SEA-62, P-11)."""
        expenses = self._uow.transactions.list_expenses(ExpenseFilters(period=period))
        return monthly_series(expenses, period)


def _group_by_currency(
    records: Sequence[ExpenseRecord],
) -> list[tuple[str, list[ExpenseRecord]]]:
    """Agrupa por moeda, em ordem alfabética (SEA-54). Sem registros → ``[]``."""
    groups: dict[str, list[ExpenseRecord]] = {}
    for record in records:
        groups.setdefault(record.currency, []).append(record)
    return [(currency, groups[currency]) for currency in sorted(groups)]


def _currency_summary(currency: str, records: Sequence[ExpenseRecord]) -> CurrencySummary:
    values = [record.value for record in records]
    return CurrencySummary(
        currency=currency,
        stats=summarize(values),
        by_merchant=merchant_totals(records),
        histogram=histogram(values),
    )


def _currency_categories(currency: str, records: Sequence[ExpenseRecord]) -> CurrencyCategories:
    """Categorias por total desc, nome asc, id asc; percentual pelo total da moeda."""
    values_by_category: dict[int, list[Decimal]] = {}
    names: dict[int, str] = {}
    for record in records:
        values_by_category.setdefault(record.category_id, []).append(record.value)
        names.setdefault(record.category_id, record.category_name)

    # Totais exatos (sem arredondar) para ordenar e para o maior resto (DA-9).
    exact_totals = {cid: sum(values, _ZERO) for cid, values in values_by_category.items()}
    ordered_ids = sorted(exact_totals, key=lambda cid: (-exact_totals[cid], names[cid], cid))
    shares = percentages([exact_totals[cid] for cid in ordered_ids])

    categories = [
        CategoryBreakdown(
            category_id=cid,
            category_name=names[cid],
            stats=summarize(values_by_category[cid]),
            percentage=share,
        )
        for cid, share in zip(ordered_ids, shares, strict=True)
    ]
    return CurrencyCategories(
        currency=currency,
        total=money(sum(exact_totals.values(), _ZERO)),
        categories=categories,
    )

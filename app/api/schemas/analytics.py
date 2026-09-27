"""Schemas de `/analytics` (contrato 8.1; SEA-20..SEA-24, SEA-54..SEA-56, SEA-61, SEA-95).

Só conversão, sem cálculo: os números vêm prontos do `AnalyticsService` (CT-21). Todo
valor monetário e todo percentual passa por `money()` (P-15, HALF_UP) antes do `Money`
(P-13, que formata com `:.2f`, HALF_EVEN). Assim nenhum campo sai com mais de 2 casas
nem depende do arredondamento do `format`, mesmo que o serviço devolva um valor exato.
`money()` sobre um valor já quantizado não o altera, então os percentuais continuam
somando 100.00 por moeda (SEA-55). Cada moeda é um grupo próprio (SEA-54).
"""

from decimal import Decimal

from pydantic import BaseModel

from app.api.schemas.common import Money
from app.application.services.analytics_service import (
    CategoryBreakdown,
    CurrencyCategories,
    CurrencySummary,
)
from app.domain.monthly_series import CategoryMonthTotal, CurrencySeries, MonthPoint
from app.domain.statistics import HistogramBucket, MerchantTotal, money


def _optional_money(value: Decimal | None) -> Decimal | None:
    return None if value is None else money(value)


# --- /analytics/summary ---------------------------------------------------------------


class MerchantTotalOut(BaseModel):
    merchant: str
    total: Money
    count: int

    @classmethod
    def from_domain(cls, item: MerchantTotal) -> "MerchantTotalOut":
        return cls(merchant=item.merchant, total=money(item.total), count=item.count)


class HistogramBucketOut(BaseModel):
    range_start: Money
    range_end: Money | None
    count: int
    total: Money

    @classmethod
    def from_domain(cls, bucket: HistogramBucket) -> "HistogramBucketOut":
        return cls(
            range_start=money(bucket.range_start),
            range_end=_optional_money(bucket.range_end),
            count=bucket.count,
            total=money(bucket.total),
        )


class CurrencySummaryOut(BaseModel):
    currency: str
    total: Money
    count: int
    mean: Money
    median: Money
    by_merchant: list[MerchantTotalOut]
    histogram: list[HistogramBucketOut]

    @classmethod
    def from_domain(cls, summary: CurrencySummary) -> "CurrencySummaryOut":
        stats = summary.stats
        return cls(
            currency=summary.currency,
            total=money(stats.total),
            count=stats.count,
            mean=money(stats.mean),
            median=money(stats.median),
            by_merchant=[MerchantTotalOut.from_domain(m) for m in summary.by_merchant],
            histogram=[HistogramBucketOut.from_domain(b) for b in summary.histogram],
        )


class SummaryOut(BaseModel):
    currencies: list[CurrencySummaryOut]

    @classmethod
    def from_domain(cls, summaries: list[CurrencySummary]) -> "SummaryOut":
        return cls(currencies=[CurrencySummaryOut.from_domain(s) for s in summaries])


# --- /analytics/categories ------------------------------------------------------------


class CategoryBreakdownOut(BaseModel):
    category_id: int
    category_name: str
    total: Money
    count: int
    mean: Money
    median: Money
    percentage: Money

    @classmethod
    def from_domain(cls, item: CategoryBreakdown) -> "CategoryBreakdownOut":
        stats = item.stats
        return cls(
            category_id=item.category_id,
            category_name=item.category_name,
            total=money(stats.total),
            count=stats.count,
            mean=money(stats.mean),
            median=money(stats.median),
            percentage=money(item.percentage),
        )


class CurrencyCategoriesOut(BaseModel):
    currency: str
    total: Money
    categories: list[CategoryBreakdownOut]

    @classmethod
    def from_domain(cls, group: CurrencyCategories) -> "CurrencyCategoriesOut":
        return cls(
            currency=group.currency,
            total=money(group.total),
            categories=[CategoryBreakdownOut.from_domain(c) for c in group.categories],
        )


class CategoriesOut(BaseModel):
    currencies: list[CurrencyCategoriesOut]

    @classmethod
    def from_domain(cls, groups: list[CurrencyCategories]) -> "CategoriesOut":
        return cls(currencies=[CurrencyCategoriesOut.from_domain(g) for g in groups])


# --- /analytics/monthly ---------------------------------------------------------------


class CategoryMonthTotalOut(BaseModel):
    category_id: int
    category_name: str
    total: Money
    count: int

    @classmethod
    def from_domain(cls, item: CategoryMonthTotal) -> "CategoryMonthTotalOut":
        return cls(
            category_id=item.category_id,
            category_name=item.category_name,
            total=money(item.total),
            count=item.count,
        )


class MonthPointOut(BaseModel):
    month: str
    total: Money
    count: int
    by_category: list[CategoryMonthTotalOut]

    @classmethod
    def from_domain(cls, point: MonthPoint) -> "MonthPointOut":
        return cls(
            month=point.month,
            total=money(point.total),
            count=point.count,
            by_category=[CategoryMonthTotalOut.from_domain(c) for c in point.by_category],
        )


class CurrencySeriesOut(BaseModel):
    currency: str
    months: list[MonthPointOut]

    @classmethod
    def from_domain(cls, series: CurrencySeries) -> "CurrencySeriesOut":
        return cls(
            currency=series.currency,
            months=[MonthPointOut.from_domain(m) for m in series.months],
        )


class MonthlyOut(BaseModel):
    currencies: list[CurrencySeriesOut]

    @classmethod
    def from_domain(cls, series: list[CurrencySeries]) -> "MonthlyOut":
        return cls(currencies=[CurrencySeriesOut.from_domain(s) for s in series])

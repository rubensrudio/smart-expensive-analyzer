from datetime import date
from decimal import Decimal

import pytest

from app.domain.entities import ExpenseRecord
from app.domain.statistics import (
    HISTOGRAM_BOUNDS,
    HistogramBucket,
    MerchantTotal,
    SummaryStats,
    histogram,
    merchant_totals,
    money,
    percentages,
    summarize,
)


def _d(values: list[str | int]) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


def _expense(merchant: str, value: str, transaction_id: int = 1) -> ExpenseRecord:
    return ExpenseRecord(
        transaction_id=transaction_id,
        date=date(2026, 1, 1),
        value=Decimal(value),
        currency="BRL",
        category_id=1,
        category_name="Outros",
        merchant=merchant,
    )


# money ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2.345", "2.35"),
        ("2.344", "2.34"),
        ("2.355", "2.36"),
        ("10", "10.00"),
        ("0", "0.00"),
    ],
)
def test_money_quantizes_to_cents_half_up(raw: str, expected: str) -> None:
    result = money(Decimal(raw))
    assert result == Decimal(expected)
    assert result.as_tuple().exponent == -2


# summarize -----------------------------------------------------------------


def test_summarize_odd_count_returns_total_mean_and_median() -> None:
    assert summarize(_d([10, 20, 60])) == SummaryStats(
        total=Decimal("90.00"),
        count=3,
        mean=Decimal("30.00"),
        median=Decimal("20.00"),
    )


def test_summarize_even_count_median_is_average_of_two_middle_values() -> None:
    stats = summarize(_d([40, 10, 30, 20]))
    assert stats.median == Decimal("25.00")
    assert stats.count == 4
    assert stats.total == Decimal("100.00")


def test_summarize_empty_returns_all_zero() -> None:
    assert summarize([]) == SummaryStats(
        total=Decimal("0.00"), count=0, mean=Decimal("0.00"), median=Decimal("0.00")
    )


def test_summarize_rounds_mean_and_median_half_up() -> None:
    stats = summarize(_d(["0.01", "0.02"]))
    assert stats.mean == Decimal("0.02")
    assert stats.median == Decimal("0.02")
    assert summarize(_d([10, 10, 11])).mean == Decimal("10.33")


def test_summarize_keeps_decimal_exactness() -> None:
    stats = summarize(_d(["0.10", "0.20"]))
    assert stats.total == Decimal("0.30")
    assert isinstance(stats.total, Decimal)


# histogram -----------------------------------------------------------------


def test_histogram_bounds_constant() -> None:
    assert (Decimal(0), Decimal(50), Decimal(100), Decimal(500)) == HISTOGRAM_BOUNDS


def test_histogram_bucket_edges_are_left_closed() -> None:
    buckets = histogram(_d(["49.99", 50, 100, 500, 1000]))
    assert [b.count for b in buckets] == [1, 1, 1, 2]
    assert [b.total for b in buckets] == _d(["49.99", "50.00", "100.00", "1500.00"])


def test_histogram_empty_returns_four_empty_buckets() -> None:
    assert histogram([]) == [
        HistogramBucket(Decimal(0), Decimal(50), 0, Decimal("0.00")),
        HistogramBucket(Decimal(50), Decimal(100), 0, Decimal("0.00")),
        HistogramBucket(Decimal(100), Decimal(500), 0, Decimal("0.00")),
        HistogramBucket(Decimal(500), None, 0, Decimal("0.00")),
    ]


def test_histogram_last_bucket_is_open_ended() -> None:
    buckets = histogram(_d([0]))
    assert len(buckets) == 4
    assert buckets[-1].range_end is None
    assert buckets[0].count == 1


def test_histogram_rejects_negative_values() -> None:
    with pytest.raises(ValueError):
        histogram(_d(["-0.01"]))


# percentages ---------------------------------------------------------------


def test_percentages_three_equal_totals_use_largest_remainder() -> None:
    result = percentages(_d([1, 1, 1]))
    assert result == _d(["33.34", "33.33", "33.33"])
    assert sum(result) == Decimal("100.00")


def test_percentages_seven_equal_totals_sum_exactly_100() -> None:
    result = percentages(_d([1] * 7))
    assert sum(result) == Decimal("100.00")
    assert all(p in (Decimal("14.29"), Decimal("14.28")) for p in result)


def test_percentages_gives_extra_cent_to_largest_remainder() -> None:
    # exact: 16.666.., 16.666.., 66.666.. -> floors 16.66/16.66/66.66, 2 cents left
    result = percentages(_d(["1", "1", "4"]))
    assert result == _d(["16.67", "16.67", "66.66"])
    assert sum(result) == Decimal("100.00")


def test_percentages_zero_total_returns_zeros() -> None:
    assert percentages(_d([0, 0])) == _d(["0.00", "0.00"])


def test_percentages_empty_returns_empty() -> None:
    assert percentages([]) == []


def test_percentages_single_total_is_100() -> None:
    assert percentages(_d(["12.34"])) == _d(["100.00"])


def test_percentages_rejects_negative_totals() -> None:
    with pytest.raises(ValueError):
        percentages(_d(["10", "-1"]))


# merchant_totals -----------------------------------------------------------


def test_merchant_totals_sorted_by_total_desc_then_merchant_asc() -> None:
    records = [
        _expense("Padaria", "10.00", 1),
        _expense("Mercado", "30.005", 2),
        _expense("Padaria", "20.00", 3),
        _expense("Farmacia", "30.00", 4),
        _expense("Açougue", "5.00", 5),
    ]
    assert merchant_totals(records) == [
        MerchantTotal(merchant="Mercado", total=Decimal("30.01"), count=1),
        MerchantTotal(merchant="Farmacia", total=Decimal("30.00"), count=1),
        MerchantTotal(merchant="Padaria", total=Decimal("30.00"), count=2),
        MerchantTotal(merchant="Açougue", total=Decimal("5.00"), count=1),
    ]


def test_merchant_totals_empty_returns_empty() -> None:
    assert merchant_totals([]) == []

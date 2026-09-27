from datetime import date
from decimal import Decimal

from app.domain.entities import ExpenseRecord, Period
from app.domain.monthly_series import (
    CategoryMonthTotal,
    CurrencySeries,
    MonthPoint,
    monthly_series,
)


def _expense(
    day: date,
    value: str,
    currency: str = "BRL",
    category_id: int = 1,
    category_name: str = "Alimentação",
    transaction_id: int = 1,
) -> ExpenseRecord:
    return ExpenseRecord(
        transaction_id=transaction_id,
        date=day,
        value=Decimal(value),
        currency=currency,
        category_id=category_id,
        category_name=category_name,
        merchant="Loja",
    )


def _months(series: CurrencySeries) -> list[str]:
    return [point.month for point in series.months]


def test_fills_missing_month_with_zero_total_and_count() -> None:
    records = [
        _expense(date(2026, 1, 10), "10.00"),
        _expense(date(2026, 3, 5), "20.00"),
    ]

    result = monthly_series(records, Period(date(2026, 1, 1), date(2026, 3, 31)))

    assert len(result) == 1
    assert _months(result[0]) == ["2026-01", "2026-02", "2026-03"]
    february = result[0].months[1]
    assert february == MonthPoint(month="2026-02", total=Decimal("0.00"), count=0, by_category=[])
    assert str(february.total) == "0.00"


def test_period_bounds_extend_range_beyond_records() -> None:
    records = [_expense(date(2026, 2, 15), "10.00")]

    result = monthly_series(records, Period(date(2025, 12, 20), date(2026, 3, 1)))

    assert _months(result[0]) == ["2025-12", "2026-01", "2026-02", "2026-03"]
    assert [p.count for p in result[0].months] == [0, 0, 1, 0]


def test_empty_period_uses_oldest_to_newest_record_month() -> None:
    records = [
        _expense(date(2026, 4, 30), "5.00"),
        _expense(date(2025, 11, 2), "7.00"),
    ]

    result = monthly_series(records, Period())

    assert _months(result[0]) == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
    ]


def test_open_ended_period_uses_record_for_missing_side() -> None:
    records = [
        _expense(date(2026, 1, 3), "5.00"),
        _expense(date(2026, 2, 3), "5.00"),
    ]

    start_only = monthly_series(records, Period(start=date(2025, 12, 1)))
    end_only = monthly_series(records, Period(end=date(2026, 3, 31)))

    assert _months(start_only[0]) == ["2025-12", "2026-01", "2026-02"]
    assert _months(end_only[0]) == ["2026-01", "2026-02", "2026-03"]


def test_monthly_total_and_count_are_summed_and_rounded() -> None:
    records = [
        _expense(date(2026, 1, 1), "10.105", transaction_id=1),
        _expense(date(2026, 1, 31), "0.10", transaction_id=2),
    ]

    result = monthly_series(records, Period())

    point = result[0].months[0]
    assert point.count == 2
    assert point.total == Decimal("10.21")
    assert str(point.total) == "10.21"


def test_by_category_sorted_by_total_desc_then_name_asc() -> None:
    records = [
        _expense(date(2026, 1, 1), "30.00", category_id=3, category_name="Transporte"),
        _expense(date(2026, 1, 2), "50.00", category_id=2, category_name="Moradia"),
        _expense(date(2026, 1, 3), "20.00", category_id=2, category_name="Moradia"),
        _expense(date(2026, 1, 4), "30.00", category_id=1, category_name="Alimentação"),
    ]

    result = monthly_series(records, Period())

    assert result[0].months[0].by_category == [
        CategoryMonthTotal(category_id=2, category_name="Moradia", total=Decimal("70.00"), count=2),
        CategoryMonthTotal(
            category_id=1, category_name="Alimentação", total=Decimal("30.00"), count=1
        ),
        CategoryMonthTotal(
            category_id=3, category_name="Transporte", total=Decimal("30.00"), count=1
        ),
    ]


def test_by_category_lists_only_categories_of_that_month() -> None:
    records = [
        _expense(date(2026, 1, 1), "10.00", category_id=1, category_name="Alimentação"),
        _expense(date(2026, 2, 1), "10.00", category_id=2, category_name="Moradia"),
    ]

    result = monthly_series(records, Period())

    january, february = result[0].months
    assert [c.category_name for c in january.by_category] == ["Alimentação"]
    assert [c.category_name for c in february.by_category] == ["Moradia"]


def test_currencies_are_separated_and_sorted_alphabetically() -> None:
    records = [
        _expense(date(2026, 1, 1), "10.00", currency="USD"),
        _expense(date(2026, 1, 2), "100.00", currency="BRL"),
        _expense(date(2026, 3, 2), "5.00", currency="USD"),
    ]

    result = monthly_series(records, Period())

    assert [s.currency for s in result] == ["BRL", "USD"]
    brl, usd = result
    assert _months(brl) == _months(usd) == ["2026-01", "2026-02", "2026-03"]
    assert [p.total for p in brl.months] == [Decimal("100.00"), Decimal("0.00"), Decimal("0.00")]
    assert [p.total for p in usd.months] == [Decimal("10.00"), Decimal("0.00"), Decimal("5.00")]


def test_empty_records_return_empty_list() -> None:
    assert monthly_series([], Period()) == []
    assert monthly_series([], Period(date(2026, 1, 1), date(2026, 3, 31))) == []


def test_records_outside_period_are_ignored() -> None:
    records = [
        _expense(date(2025, 12, 31), "99.00"),
        _expense(date(2026, 1, 15), "10.00"),
    ]

    result = monthly_series(records, Period(date(2026, 1, 1), date(2026, 1, 31)))

    assert _months(result[0]) == ["2026-01"]
    assert result[0].months[0].total == Decimal("10.00")


def test_range_crosses_year_boundary() -> None:
    result = monthly_series([_expense(date(2026, 1, 1), "1.00")], Period(date(2025, 11, 5), None))

    assert _months(result[0]) == ["2025-11", "2025-12", "2026-01"]


def test_same_input_produces_same_output() -> None:
    records = [
        _expense(date(2026, 2, 1), "3.00", currency="USD"),
        _expense(date(2026, 1, 1), "4.00", category_id=2, category_name="Moradia"),
    ]

    assert monthly_series(records, Period()) == monthly_series(list(reversed(records)), Period())

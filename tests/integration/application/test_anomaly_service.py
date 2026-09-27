"""Serviço de anomalias contra PostgreSQL real (CT-16, TASK-018).

Requisitos: SEA-27, SEA-29, SEA-30, SEA-31, SEA-57, SEA-60.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.application.services.anomaly_service import AnomalyService
from app.domain.anomaly_detection import IQR_METHOD
from app.domain.entities import NewTransaction, Period, TransactionType
from app.domain.ports import UnitOfWork

UoWFactory = Callable[[], UnitOfWork]

K = 1.5
MIN_SAMPLE = 8
OUTLIER_DATE = date(2026, 3, 15)
RECEIVED_AT = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)


def _new_tx(
    import_id: int, category_id: int, idx: int, amount: str, tx_date: date
) -> NewTransaction:
    value = Decimal(amount)
    return NewTransaction(
        date=tx_date,
        description=f"COMPRA {idx}",
        merchant=f"Loja {idx}",
        amount=value,
        currency="BRL",
        type=TransactionType.from_amount(value),
        category_id=category_id,
        import_id=import_id,
        dedup_key=f"{idx:064d}",
    )


def _seed(uow_factory: UoWFactory, rows: Sequence[tuple[str, date]]) -> None:
    with uow_factory() as uow:
        import_id = uow.imports.create_processing("extrato.csv", "a" * 64, RECEIVED_AT)
        category_id = uow.categories.get_default().id
        items = [
            _new_tx(import_id, category_id, idx, amount, tx_date)
            for idx, (amount, tx_date) in enumerate(rows)
        ]
        assert uow.transactions.insert_ignoring_duplicates(items) == len(items)
        uow.commit()


def _sea28_rows() -> list[tuple[str, date]]:
    """20 despesas entre 40,00 e 60,00 e uma de 5.000,00 na mesma categoria (SEA-28)."""
    rows = [(f"-{40 + i}.00", date(2026, 2, 1 + i)) for i in range(20)]
    rows.append(("-5000.00", OUTLIER_DATE))
    return rows


def _recompute_and_commit(uow_factory: UoWFactory) -> int:
    with uow_factory() as uow:
        count = AnomalyService(uow, K, MIN_SAMPLE).recompute_all()
        uow.commit()
    return count


def _list(uow_factory: UoWFactory, period: Period) -> list[tuple[Decimal, date, str]]:
    with uow_factory() as uow:
        return [
            (a.transaction.amount, a.transaction.date, a.method)
            for a in AnomalyService(uow, K, MIN_SAMPLE).list(period)
        ]


def test_recompute_all_marks_only_the_outlier_sea28_sea60(uow_factory: UoWFactory) -> None:
    """SEA-27, SEA-60: recálculo sobre todo o histórico persiste só a de 5.000,00."""
    _seed(uow_factory, _sea28_rows())

    assert _recompute_and_commit(uow_factory) == 1

    with uow_factory() as uow:
        anomalies = AnomalyService(uow, K, MIN_SAMPLE).list(Period())
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly.transaction.amount == Decimal("-5000.00")
    assert anomaly.method == IQR_METHOD
    assert anomaly.reason
    assert anomaly.value > Decimal("60.00")


def test_recompute_all_twice_keeps_single_anomaly_sea30(uow_factory: UoWFactory) -> None:
    """SEA-30: rodar de novo com os mesmos dados não duplica Anomaly."""
    _seed(uow_factory, _sea28_rows())

    assert _recompute_and_commit(uow_factory) == 1
    assert _recompute_and_commit(uow_factory) == 1

    assert _list(uow_factory, Period()) == [(Decimal("-5000.00"), OUTLIER_DATE, IQR_METHOD)]


def test_high_income_never_generates_anomaly_sea29(uow_factory: UoWFactory) -> None:
    """SEA-29: receita de valor alto no mesmo grupo não vira anomalia."""
    rows = [(f"-{40 + i}.00", date(2026, 2, 1 + i)) for i in range(20)]
    rows.append(("50000.00", OUTLIER_DATE))
    _seed(uow_factory, rows)

    assert _recompute_and_commit(uow_factory) == 0
    assert _list(uow_factory, Period()) == []


def test_recompute_all_does_not_commit(uow_factory: UoWFactory) -> None:
    """CT-16: quem comita é o caller; sem commit o conjunto não persiste."""
    _seed(uow_factory, _sea28_rows())

    with uow_factory() as uow:
        assert AnomalyService(uow, K, MIN_SAMPLE).recompute_all() == 1

    assert _list(uow_factory, Period()) == []


def test_recompute_all_replaces_previous_set_sea60(uow_factory: UoWFactory) -> None:
    """SEA-60: com parâmetros que não marcam nada, o conjunto anterior some."""
    _seed(uow_factory, _sea28_rows())
    assert _recompute_and_commit(uow_factory) == 1

    with uow_factory() as uow:
        assert AnomalyService(uow, K, min_sample=50).recompute_all() == 0
        uow.commit()

    assert _list(uow_factory, Period()) == []


def test_recompute_all_on_empty_history_returns_zero(uow_factory: UoWFactory) -> None:
    assert _recompute_and_commit(uow_factory) == 0
    assert _list(uow_factory, Period()) == []


def test_list_filters_by_period_sea31_sea57(uow_factory: UoWFactory) -> None:
    """SEA-31: fora da data da anomalia → []; SEA-57: sem período → todas."""
    _seed(uow_factory, _sea28_rows())
    _recompute_and_commit(uow_factory)

    assert _list(uow_factory, Period(date(2026, 1, 1), date(2026, 3, 14))) == []
    assert _list(uow_factory, Period(start=date(2026, 3, 16))) == []
    expected = [(Decimal("-5000.00"), OUTLIER_DATE, IQR_METHOD)]
    assert _list(uow_factory, Period(OUTLIER_DATE, OUTLIER_DATE)) == expected
    assert _list(uow_factory, Period()) == expected


def test_recompute_all_logs_count_and_groups(
    uow_factory: UoWFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """Plan seção 14: `anomalies_recomputed count=<n> groups_evaluated=<n>`, sem valores."""
    _seed(uow_factory, _sea28_rows())

    with caplog.at_level(logging.INFO, logger="app.application.services.anomaly_service"):
        _recompute_and_commit(uow_factory)

    messages = [
        r.getMessage() for r in caplog.records if r.getMessage().startswith("anomalies_recomputed")
    ]
    assert messages == ["anomalies_recomputed count=1 groups_evaluated=1"]
    assert all("5000" not in r.getMessage() for r in caplog.records)


def test_invalid_k_raises_value_error(uow_factory: UoWFactory) -> None:
    """CT-15: parâmetro inválido propaga ValueError e nada é gravado."""
    _seed(uow_factory, _sea28_rows())

    with pytest.raises(ValueError), uow_factory() as uow:
        AnomalyService(uow, float("inf"), MIN_SAMPLE).recompute_all()

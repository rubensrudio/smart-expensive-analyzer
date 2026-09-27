"""Serviço de recategorização contra PostgreSQL real (CT-20, TASK-022).

Requisitos: SEA-63, SEA-65, SEA-66, SEA-109.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.application.services.recategorization_service import (
    RecategorizationResult,
    RecategorizationService,
)
from app.core.config import Settings
from app.domain.entities import NewTransaction, Period, TransactionType
from app.domain.ports import UnitOfWork

UoWFactory = Callable[[], UnitOfWork]

RECEIVED_AT = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
OUTLIER_DESCRIPTION = "PASSAGEM AEREA"
OUTLIER_AMOUNT = Decimal("-5000.00")


def _new_tx(
    import_id: int, category_id: int, idx: int, description: str, amount: str, tx_date: date
) -> NewTransaction:
    value = Decimal(amount)
    return NewTransaction(
        date=tx_date,
        description=description,
        merchant=f"Loja {idx}",
        amount=value,
        currency="BRL",
        type=TransactionType.from_amount(value),
        category_id=category_id,
        import_id=import_id,
        dedup_key=f"{idx:064d}",
    )


def _seed(uow_factory: UoWFactory, rows: Sequence[tuple[str, str, date]]) -> list[int]:
    """Grava as transações na categoria padrão e devolve os ids em ordem de inserção."""
    with uow_factory() as uow:
        import_id = uow.imports.create_processing("extrato.csv", "a" * 64, RECEIVED_AT)
        default_id = uow.categories.get_default().id
        items = [
            _new_tx(import_id, default_id, idx, description, amount, tx_date)
            for idx, (description, amount, tx_date) in enumerate(rows)
        ]
        assert uow.transactions.insert_ignoring_duplicates(items) == len(items)
        ids = [t.id for t in uow.transactions.list_all_for_categorization()]
        uow.commit()
    return ids


def _add_rule(uow_factory: UoWFactory, keyword: str, category_name: str) -> int:
    with uow_factory() as uow:
        category = uow.categories.add(category_name)
        uow.rules.add(keyword, category.id, 1)
        uow.commit()
    return category.id


def _recategorize(uow_factory: UoWFactory, settings: Settings) -> RecategorizationResult:
    with uow_factory() as uow:
        return RecategorizationService(uow, settings).recategorize()


def _category_of(uow_factory: UoWFactory, transaction_id: int) -> str:
    with uow_factory() as uow:
        tx = uow.transactions.get(transaction_id)
        assert tx is not None
        return tx.category_name


def _anomaly_amounts(uow_factory: UoWFactory) -> list[Decimal]:
    with uow_factory() as uow:
        return [a.transaction.amount for a in uow.anomalies.list(Period())]


def test_new_rule_moves_uncategorized_transaction_sea63(
    uow_factory: UoWFactory, settings: Settings
) -> None:
    """SEA-63: "UBER TRIP" em "Não categorizada" vai para Transporte após recategorizar."""
    (tx_id,) = _seed(uow_factory, [("UBER TRIP", "-25.00", date(2026, 3, 1))])
    before = _category_of(uow_factory, tx_id)
    _add_rule(uow_factory, "UBER", "Transporte")

    # SEA-64: a regra nova sozinha não muda nada.
    assert _category_of(uow_factory, tx_id) == before

    result = _recategorize(uow_factory, settings)

    assert result == RecategorizationResult(evaluated=1, changed=1)
    assert _category_of(uow_factory, tx_id) == "Transporte"


def test_second_call_changes_nothing_sea66(uow_factory: UoWFactory, settings: Settings) -> None:
    """SEA-66: sem mudança de regras, a segunda chamada informa 0 alteradas."""
    _seed(
        uow_factory,
        [
            ("UBER TRIP", "-25.00", date(2026, 3, 1)),
            ("MERCADO", "-80.00", date(2026, 3, 2)),
        ],
    )
    _add_rule(uow_factory, "UBER", "Transporte")

    first = _recategorize(uow_factory, settings)
    second = _recategorize(uow_factory, settings)

    assert first == RecategorizationResult(evaluated=2, changed=1)
    assert second == RecategorizationResult(evaluated=2, changed=0)


def test_without_transactions_returns_zeros_sea109(
    uow_factory: UoWFactory, settings: Settings
) -> None:
    """SEA-109: sem transações persistidas → (0, 0)."""
    _add_rule(uow_factory, "UBER", "Transporte")

    assert _recategorize(uow_factory, settings) == RecategorizationResult(evaluated=0, changed=0)
    assert _anomaly_amounts(uow_factory) == []


def test_moving_expenses_recomputes_persisted_anomalies_sea65(
    uow_factory: UoWFactory, settings: Settings
) -> None:
    """SEA-65: tirar o outlier do grupo (padrão, BRL) remove a anomalia persistida."""
    rows = [(f"COMPRA {i}", f"-{40 + i}.00", date(2026, 2, 1 + i)) for i in range(20)]
    rows.append((OUTLIER_DESCRIPTION, str(OUTLIER_AMOUNT), date(2026, 3, 15)))
    _seed(uow_factory, rows)

    # Sem regras: nada muda, mas o recálculo persiste o outlier do grupo padrão.
    assert _recategorize(uow_factory, settings) == RecategorizationResult(21, 0)
    assert _anomaly_amounts(uow_factory) == [OUTLIER_AMOUNT]

    # O outlier sai para um grupo de 1 despesa (< min_sample): o conjunto fica vazio.
    _add_rule(uow_factory, "PASSAGEM", "Viagem")
    assert _recategorize(uow_factory, settings) == RecategorizationResult(21, 1)
    assert _anomaly_amounts(uow_factory) == []


def test_changes_are_committed_by_the_service(uow_factory: UoWFactory, settings: Settings) -> None:
    """O serviço faz o commit: outro UoW já enxerga a categoria nova."""
    (tx_id,) = _seed(uow_factory, [("UBER TRIP", "-25.00", date(2026, 3, 1))])
    _add_rule(uow_factory, "UBER", "Transporte")

    with uow_factory() as uow:
        RecategorizationService(uow, settings).recategorize()
        # Sem commit aqui: se o serviço não comitasse, o __exit__ faria rollback.

    assert _category_of(uow_factory, tx_id) == "Transporte"


def test_log_has_counts_only_as3(
    uow_factory: UoWFactory, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """Seção 14 e AS-3: loga só as contagens, sem descrição, estabelecimento nem valor."""
    _seed(uow_factory, [("UBER TRIP", "-25.00", date(2026, 3, 1))])
    _add_rule(uow_factory, "UBER", "Transporte")

    with caplog.at_level(logging.INFO):
        _recategorize(uow_factory, settings)

    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.application.services.recategorization_service"
    ]
    assert messages == ["recategorization_finished evaluated=1 changed=1"]
    joined = " ".join(r.getMessage() for r in caplog.records)
    for secret in ("UBER", "Loja", "25.00"):
        assert secret not in joined

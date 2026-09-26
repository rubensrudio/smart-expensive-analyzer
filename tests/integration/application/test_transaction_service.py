"""Testes de integração do `TransactionService` (CT-19, TASK-021)."""

import hashlib
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.application.services.transaction_service import TransactionService
from app.core.errors import TransactionNotFoundError
from app.domain.entities import NewTransaction, Page, TransactionFilters, TransactionType
from app.domain.ports import UnitOfWork


def _new(
    *, import_id: int, category_id: int, merchant: str, description: str, amount: str = "-10.00"
) -> NewTransaction:
    value = Decimal(amount)
    day = date(2026, 1, 15)
    raw_key = f"{day.isoformat()}|{value:.2f}|{description}|BRL"
    return NewTransaction(
        date=day,
        description=description,
        merchant=merchant,
        amount=value,
        currency="BRL",
        type=TransactionType.from_amount(value),
        category_id=category_id,
        import_id=import_id,
        dedup_key=hashlib.sha256(raw_key.encode()).hexdigest(),
    )


@pytest.fixture
def seed(uow_factory: Callable[[], UnitOfWork]) -> Callable[..., None]:
    """Grava transações numa UoW própria e confirma, para a UoW do teste enxergar."""

    def _seed(*items: tuple[str, str]) -> None:
        with uow_factory() as u:
            import_id = u.imports.create_processing(
                "extrato.csv", "b" * 64, datetime(2026, 1, 1, tzinfo=UTC)
            )
            default_id = u.categories.get_default().id
            u.transactions.insert_ignoring_duplicates(
                [
                    _new(
                        import_id=import_id,
                        category_id=default_id,
                        merchant=merchant,
                        description=description,
                    )
                    for merchant, description in items
                ]
            )
            u.commit()

    return _seed


def test_get_missing_id_raises_transaction_not_found(uow: UnitOfWork) -> None:
    with pytest.raises(TransactionNotFoundError) as exc_info:
        TransactionService(uow).get(999999)

    assert exc_info.value.code == "TRANSACTION_NOT_FOUND"
    assert exc_info.value.http_status == 404


def test_get_existing_id_returns_transaction_with_category_name(
    uow: UnitOfWork, seed: Callable[..., None]
) -> None:
    seed(("UBER TRIP", "UBER TRIP 123"))
    listed = TransactionService(uow).list(TransactionFilters(), Page())
    tx_id = listed.items[0].id

    tx = TransactionService(uow).get(tx_id)

    assert tx.id == tx_id
    assert tx.merchant == "UBER TRIP"
    assert tx.category_name == uow.categories.get_default().name


def test_list_normalizes_merchant_whitespace_and_case(
    uow: UnitOfWork, seed: Callable[..., None]
) -> None:
    seed(("UBER TRIP", "UBER TRIP 123"), ("IFOOD", "IFOOD PEDIDO"))

    result = TransactionService(uow).list(TransactionFilters(merchant="  uber   trip "), Page())

    assert result.total == 1
    assert [t.merchant for t in result.items] == ["UBER TRIP"]


def test_list_without_filters_returns_all_with_total(
    uow: UnitOfWork, seed: Callable[..., None]
) -> None:
    seed(("UBER TRIP", "A"), ("IFOOD", "B"), ("PADARIA", "C"))

    result = TransactionService(uow).list(TransactionFilters(), Page(limit=2, offset=0))

    assert result.total == 3
    assert len(result.items) == 2


def test_list_merchant_without_match_returns_empty(
    uow: UnitOfWork, seed: Callable[..., None]
) -> None:
    seed(("UBER TRIP", "A"))

    result = TransactionService(uow).list(TransactionFilters(merchant="uber"), Page())

    assert result.total == 0
    assert result.items == []


class _SpyTransactions:
    def __init__(self) -> None:
        self.received: TransactionFilters | None = None

    def list(self, filters: TransactionFilters, page: Page) -> object:
        self.received = filters
        return object()


class _SpyUow:
    def __init__(self) -> None:
        self.transactions = _SpyTransactions()


def test_list_passes_normalized_merchant_to_repository() -> None:
    spy = _SpyUow()

    TransactionService(spy).list(  # type: ignore[arg-type]
        TransactionFilters(merchant="  uber   trip ", category_id=7), Page()
    )

    assert spy.transactions.received == TransactionFilters(merchant="uber trip", category_id=7)

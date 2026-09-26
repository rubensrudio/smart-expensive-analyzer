"""Testes de integração do `SqlAlchemyTransactionRepository` (CT-24, TASK-008)."""

import hashlib
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.entities import (
    ExpenseFilters,
    NewTransaction,
    Page,
    Period,
    TransactionFilters,
    TransactionType,
)
from app.infrastructure.db.models import CategoryModel, ImportModel, TransactionModel
from app.infrastructure.db.repositories.transactions import SqlAlchemyTransactionRepository


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s
        s.rollback()


@pytest.fixture
def repo(session: Session) -> SqlAlchemyTransactionRepository:
    return SqlAlchemyTransactionRepository(session)


@pytest.fixture
def default_category_id(session: Session) -> int:
    return session.execute(select(CategoryModel.id).where(CategoryModel.is_default)).scalar_one()


@pytest.fixture
def import_id(session: Session) -> int:
    return _add_import(session)


def _add_import(session: Session) -> int:
    record = ImportModel(
        filename="extrato.csv",
        file_sha256="a" * 64,
        status="processando",
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(record)
    session.flush()
    return record.id


def _add_category(session: Session, name: str) -> int:
    category = CategoryModel(name=name)
    session.add(category)
    session.flush()
    return category.id


def _new(
    *,
    import_id: int,
    category_id: int,
    day: date = date(2026, 1, 15),
    amount: str = "-10.00",
    description: str = "Compra",
    merchant: str | None = None,
    currency: str = "BRL",
    key: str | None = None,
) -> NewTransaction:
    value = Decimal(amount)
    raw_key = key or f"{day.isoformat()}|{value:.2f}|{description}|{currency}"
    return NewTransaction(
        date=day,
        description=description,
        merchant=merchant if merchant is not None else description,
        amount=value,
        currency=currency,
        type=TransactionType.from_amount(value),
        category_id=category_id,
        import_id=import_id,
        dedup_key=hashlib.sha256(raw_key.encode()).hexdigest(),
    )


def _count_by_key(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(TransactionModel.dedup_key, func.count()).group_by(TransactionModel.dedup_key)
    ).all()
    return {key: count for key, count in rows}


# --- insert_ignoring_duplicates -------------------------------------------------------------


def test_insert_ignores_existing_dedup_key_and_returns_inserted_count(
    repo: SqlAlchemyTransactionRepository,
    session: Session,
    import_id: int,
    default_category_id: int,
) -> None:
    existing = _new(import_id=import_id, category_id=default_category_id, key="k-existente")
    assert repo.insert_ignoring_duplicates([existing]) == 1

    batch = [
        _new(import_id=import_id, category_id=default_category_id, key="k-1"),
        _new(import_id=import_id, category_id=default_category_id, key="k-2"),
        _new(import_id=import_id, category_id=default_category_id, key="k-existente"),
    ]

    assert repo.insert_ignoring_duplicates(batch) == 2
    counts = _count_by_key(session)
    assert len(counts) == 3
    assert set(counts.values()) == {1}


def test_insert_ignores_duplicate_key_inside_same_batch(
    repo: SqlAlchemyTransactionRepository,
    session: Session,
    import_id: int,
    default_category_id: int,
) -> None:
    batch = [
        _new(import_id=import_id, category_id=default_category_id, key="mesma"),
        _new(import_id=import_id, category_id=default_category_id, key="mesma"),
    ]

    assert repo.insert_ignoring_duplicates(batch) == 1
    assert list(_count_by_key(session).values()) == [1]


def test_insert_large_batch_counts_across_chunks(
    repo: SqlAlchemyTransactionRepository,
    session: Session,
    import_id: int,
    default_category_id: int,
) -> None:
    keys = [f"k-{i}" for i in range(1500)] + ["k-0", "k-1499"]
    batch = [_new(import_id=import_id, category_id=default_category_id, key=k) for k in keys]

    assert repo.insert_ignoring_duplicates(batch) == 1500
    assert session.execute(select(func.count()).select_from(TransactionModel)).scalar_one() == 1500


def test_insert_empty_sequence_returns_zero(repo: SqlAlchemyTransactionRepository) -> None:
    assert repo.insert_ignoring_duplicates([]) == 0


def test_insert_does_not_commit(
    session_factory: sessionmaker[Session], default_category_id: int
) -> None:
    with session_factory() as s:
        imp = _add_import(s)
        SqlAlchemyTransactionRepository(s).insert_ignoring_duplicates(
            [_new(import_id=imp, category_id=default_category_id)]
        )
        s.rollback()

    with session_factory() as s:
        assert s.execute(select(func.count()).select_from(TransactionModel)).scalar_one() == 0


# --- get ------------------------------------------------------------------------------------


def test_get_returns_transaction_with_category_name_and_type(
    repo: SqlAlchemyTransactionRepository, session: Session, import_id: int
) -> None:
    category_id = _add_category(session, "Mercado")
    repo.insert_ignoring_duplicates(
        [
            _new(
                import_id=import_id,
                category_id=category_id,
                amount="-45.90",
                description="SUPERMERCADO X",
                merchant="Supermercado X",
            )
        ]
    )
    tx_id = session.execute(select(TransactionModel.id)).scalar_one()

    tx = repo.get(tx_id)

    assert tx is not None
    assert tx.id == tx_id
    assert tx.amount == Decimal("-45.90")
    assert tx.type is TransactionType.EXPENSE
    assert tx.category_id == category_id
    assert tx.category_name == "Mercado"
    assert tx.merchant == "Supermercado X"
    assert tx.currency == "BRL"
    assert tx.import_id == import_id


def test_get_unknown_id_returns_none(repo: SqlAlchemyTransactionRepository) -> None:
    assert repo.get(999_999) is None


# --- list -----------------------------------------------------------------------------------


def test_list_period_is_closed_interval(
    repo: SqlAlchemyTransactionRepository, import_id: int, default_category_id: int
) -> None:
    days = [9, 10, 15, 20, 21]
    repo.insert_ignoring_duplicates(
        [
            _new(import_id=import_id, category_id=default_category_id, day=date(2026, 1, d))
            for d in days
        ]
    )

    result = repo.list(
        TransactionFilters(period=Period(date(2026, 1, 10), date(2026, 1, 20))), Page()
    )

    assert sorted(t.date.day for t in result.items) == [10, 15, 20]
    assert result.total == 3


def test_list_open_period_bounds(
    repo: SqlAlchemyTransactionRepository, import_id: int, default_category_id: int
) -> None:
    repo.insert_ignoring_duplicates(
        [
            _new(import_id=import_id, category_id=default_category_id, day=date(2026, 1, d))
            for d in (5, 25)
        ]
    )

    only_start = repo.list(TransactionFilters(period=Period(start=date(2026, 1, 10))), Page())
    only_end = repo.list(TransactionFilters(period=Period(end=date(2026, 1, 10))), Page())

    assert [t.date.day for t in only_start.items] == [25]
    assert [t.date.day for t in only_end.items] == [5]


def test_list_pagination_returns_total_and_orders_by_date_desc_id_desc(
    repo: SqlAlchemyTransactionRepository, import_id: int, default_category_id: int
) -> None:
    items = [
        _new(import_id=import_id, category_id=default_category_id, day=date(2026, 1, d), key=k)
        for d, k in [(1, "a"), (2, "b"), (2, "c"), (3, "d"), (4, "e")]
    ]
    repo.insert_ignoring_duplicates(items)

    full = repo.list(TransactionFilters(), Page(limit=50, offset=0))
    page = repo.list(TransactionFilters(), Page(limit=2, offset=2))

    ordered = [(t.date, t.id) for t in full.items]
    assert ordered == sorted(ordered, reverse=True)
    assert len(page.items) == 2
    assert page.total == 5
    assert [t.id for t in page.items] == [t.id for t in full.items[2:4]]


def test_list_unknown_category_returns_empty(
    repo: SqlAlchemyTransactionRepository, import_id: int, default_category_id: int
) -> None:
    repo.insert_ignoring_duplicates([_new(import_id=import_id, category_id=default_category_id)])

    result = repo.list(TransactionFilters(category_id=999_999), Page())

    assert result.items == []
    assert result.total == 0


def test_list_filters_by_category_merchant_ci_and_import(
    repo: SqlAlchemyTransactionRepository,
    session: Session,
    import_id: int,
    default_category_id: int,
) -> None:
    other_import = _add_import(session)
    food = _add_category(session, "Alimentação")
    repo.insert_ignoring_duplicates(
        [
            _new(import_id=import_id, category_id=food, merchant="Padaria Sol", key="1"),
            _new(import_id=import_id, category_id=default_category_id, merchant="Posto", key="2"),
            _new(import_id=other_import, category_id=food, merchant="PADARIA SOL", key="3"),
        ]
    )

    by_category = repo.list(TransactionFilters(category_id=food), Page())
    by_merchant = repo.list(TransactionFilters(merchant="  padaria   sol "), Page())
    by_import = repo.list(TransactionFilters(import_id=other_import), Page())
    combined = repo.list(
        TransactionFilters(category_id=food, merchant="padaria sol", import_id=import_id), Page()
    )

    assert by_category.total == 2
    assert by_merchant.total == 2
    assert {t.merchant for t in by_merchant.items} == {"Padaria Sol", "PADARIA SOL"}
    assert by_import.total == 1
    assert by_import.items[0].import_id == other_import
    assert combined.total == 1
    assert combined.items[0].merchant == "Padaria Sol"


def test_list_merchant_is_not_substring_match(
    repo: SqlAlchemyTransactionRepository, import_id: int, default_category_id: int
) -> None:
    repo.insert_ignoring_duplicates(
        [_new(import_id=import_id, category_id=default_category_id, merchant="Padaria Sol")]
    )

    assert repo.list(TransactionFilters(merchant="Padaria"), Page()).total == 0


# --- list_expenses --------------------------------------------------------------------------


def test_list_expenses_ignores_income_and_returns_absolute_value(
    repo: SqlAlchemyTransactionRepository, session: Session, import_id: int
) -> None:
    category_id = _add_category(session, "Mercado")
    repo.insert_ignoring_duplicates(
        [
            _new(import_id=import_id, category_id=category_id, amount="-45.90", key="d"),
            _new(import_id=import_id, category_id=category_id, amount="1000.00", key="r"),
        ]
    )

    expenses = repo.list_expenses(ExpenseFilters())

    assert len(expenses) == 1
    expense = expenses[0]
    assert expense.value == Decimal("45.90")
    assert expense.category_id == category_id
    assert expense.category_name == "Mercado"
    assert expense.currency == "BRL"
    assert expense.date == date(2026, 1, 15)


def test_list_expenses_applies_filters(
    repo: SqlAlchemyTransactionRepository,
    session: Session,
    import_id: int,
    default_category_id: int,
) -> None:
    food = _add_category(session, "Alimentação")
    repo.insert_ignoring_duplicates(
        [
            _new(import_id=import_id, category_id=food, day=date(2026, 1, 5), key="1"),
            _new(
                import_id=import_id,
                category_id=food,
                day=date(2026, 1, 15),
                merchant="Padaria",
                key="2",
            ),
            _new(import_id=import_id, category_id=default_category_id, key="3"),
        ]
    )

    by_period = repo.list_expenses(
        ExpenseFilters(period=Period(date(2026, 1, 10), date(2026, 1, 31)))
    )
    by_category = repo.list_expenses(ExpenseFilters(category_id=food))
    by_merchant = repo.list_expenses(ExpenseFilters(merchant="PADARIA"))

    assert len(by_period) == 2
    assert len(by_category) == 2
    assert [e.merchant for e in by_merchant] == ["Padaria"]


# --- categorização em lote ------------------------------------------------------------------


def test_list_all_for_categorization_and_update_categories(
    repo: SqlAlchemyTransactionRepository,
    session: Session,
    import_id: int,
    default_category_id: int,
) -> None:
    food = _add_category(session, "Alimentação")
    repo.insert_ignoring_duplicates(
        [
            _new(import_id=import_id, category_id=default_category_id, description="A", key="1"),
            _new(import_id=import_id, category_id=default_category_id, description="B", key="2"),
            _new(import_id=import_id, category_id=default_category_id, description="C", key="3"),
        ]
    )
    before = repo.list_all_for_categorization()
    assert [t.description for t in before] == ["A", "B", "C"]
    assert {t.category_id for t in before} == {default_category_id}

    repo.update_categories({before[0].id: food, before[2].id: food})
    repo.update_categories({})

    after = {t.id: t.category_id for t in repo.list_all_for_categorization()}
    assert after == {before[0].id: food, before[1].id: default_category_id, before[2].id: food}
    tx = repo.get(before[0].id)
    assert tx is not None
    assert tx.category_name == "Alimentação"

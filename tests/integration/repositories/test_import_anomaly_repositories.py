"""Repositórios SQLAlchemy de Import e Anomaly contra PostgreSQL real.

CT-25 (TASK-009); SEA-27, SEA-30, SEA-31, SEA-41, SEA-43, SEA-107; DA-7.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.entities import (
    AnomalyCandidate,
    ImportStatus,
    Period,
    RowRejection,
    TransactionType,
)
from app.infrastructure.db.models import (
    AnomalyModel,
    CategoryModel,
    ImportModel,
    ImportRejectionModel,
    TransactionModel,
)
from app.infrastructure.db.repositories.anomalies import (
    ANOMALY_LOCK_KEY,
    SqlAlchemyAnomalyRepository,
)
from app.infrastructure.db.repositories.imports import SqlAlchemyImportRepository

HASH_A = "a" * 64
HASH_B = "b" * 64
RECEIVED_AT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s
        s.rollback()


def _default_category(session: Session) -> CategoryModel:
    return session.scalars(select(CategoryModel).where(CategoryModel.is_default)).one()


def _add_import(session: Session, status: str, file_sha256: str = HASH_A) -> int:
    model = ImportModel(
        filename="extrato.csv", file_sha256=file_sha256, status=status, received_at=RECEIVED_AT
    )
    session.add(model)
    session.flush()
    return model.id


def _add_transaction(
    session: Session,
    import_id: int,
    tx_date: date,
    amount: str = "-50.00",
    category_id: int | None = None,
) -> int:
    value = Decimal(amount)
    model = TransactionModel(
        import_id=import_id,
        date=tx_date,
        description=f"COMPRA {tx_date.isoformat()} {amount}",
        merchant="Mercado X",
        amount=value,
        currency="BRL",
        type=TransactionType.from_amount(value).value,
        category_id=category_id if category_id is not None else _default_category(session).id,
        dedup_key=f"{tx_date.isoformat()}{amount}".ljust(64, "0")[:64],
    )
    session.add(model)
    session.flush()
    return model.id


def _count(session: Session, model: type[AnomalyModel] | type[ImportRejectionModel]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


# ---------------------------------------------------------------- ImportRepository


def test_find_completed_by_hash_ignores_failed_import(session: Session) -> None:
    _add_import(session, ImportStatus.FAILED.value)
    repo = SqlAlchemyImportRepository(session)

    assert repo.find_completed_by_hash(HASH_A) is None


def test_find_completed_by_hash_returns_id_of_completed_import(session: Session) -> None:
    _add_import(session, ImportStatus.FAILED.value)
    completed_id = _add_import(session, ImportStatus.COMPLETED.value)
    repo = SqlAlchemyImportRepository(session)

    assert repo.find_completed_by_hash(HASH_A) == completed_id


def test_find_completed_by_hash_accepts_completed_with_rejections_only(session: Session) -> None:
    _add_import(session, ImportStatus.PROCESSING.value, HASH_B)
    with_rejections_id = _add_import(session, ImportStatus.COMPLETED_WITH_REJECTIONS.value)
    repo = SqlAlchemyImportRepository(session)

    assert repo.find_completed_by_hash(HASH_A) == with_rejections_id
    assert repo.find_completed_by_hash(HASH_B) is None
    assert repo.find_completed_by_hash("c" * 64) is None


def test_create_processing_persists_import_in_processing(session: Session) -> None:
    repo = SqlAlchemyImportRepository(session)

    import_id = repo.create_processing("extrato.csv", HASH_A, RECEIVED_AT)

    model = session.get(ImportModel, import_id)
    assert model is not None
    assert model.status == ImportStatus.PROCESSING.value
    assert model.filename == "extrato.csv"
    assert model.file_sha256 == HASH_A
    assert model.received_at == RECEIVED_AT
    assert model.finished_at is None


def test_finish_persists_counts_and_two_rejections(session: Session) -> None:
    repo = SqlAlchemyImportRepository(session)
    import_id = repo.create_processing("extrato.csv", HASH_A, RECEIVED_AT)
    rejections = [RowRejection(3, "data inválida"), RowRejection(7, "valor inválido")]

    record = repo.finish(
        import_id,
        ImportStatus.COMPLETED_WITH_REJECTIONS,
        rows_read=10,
        imported_count=6,
        rejected_count=2,
        duplicate_count=2,
        rejections=rejections,
    )

    assert record.id == import_id
    assert record.filename == "extrato.csv"
    assert record.status is ImportStatus.COMPLETED_WITH_REJECTIONS
    assert record.received_at == RECEIVED_AT
    assert (record.rows_read, record.imported_count) == (10, 6)
    assert (record.rejected_count, record.duplicate_count) == (2, 2)
    assert record.rejections == tuple(rejections)

    rows = session.execute(
        select(ImportRejectionModel.line_number, ImportRejectionModel.reason)
        .where(ImportRejectionModel.import_id == import_id)
        .order_by(ImportRejectionModel.line_number)
    ).all()
    assert [tuple(r) for r in rows] == [(3, "data inválida"), (7, "valor inválido")]

    model = session.get(ImportModel, import_id)
    assert model is not None
    session.refresh(model)
    assert model.status == ImportStatus.COMPLETED_WITH_REJECTIONS.value
    assert model.finished_at is not None


def test_finish_without_rejections_returns_empty_tuple(session: Session) -> None:
    repo = SqlAlchemyImportRepository(session)
    import_id = repo.create_processing("extrato.csv", HASH_A, RECEIVED_AT)

    record = repo.finish(import_id, ImportStatus.COMPLETED, 3, 3, 0, 0, [])

    assert record.status is ImportStatus.COMPLETED
    assert record.rejections == ()
    assert _count(session, ImportRejectionModel) == 0
    assert repo.find_completed_by_hash(HASH_A) == import_id


def test_finish_unknown_import_raises_lookup_error(session: Session) -> None:
    repo = SqlAlchemyImportRepository(session)

    with pytest.raises(LookupError):
        repo.finish(999_999, ImportStatus.COMPLETED, 0, 0, 0, 0, [])


def test_record_failure_creates_failed_import_invisible_to_hash_lookup(session: Session) -> None:
    repo = SqlAlchemyImportRepository(session)

    import_id = repo.record_failure("extrato.csv", HASH_A, RECEIVED_AT, "OperationalError")

    model = session.get(ImportModel, import_id)
    assert model is not None
    assert model.status == ImportStatus.FAILED.value
    assert model.failure_reason == "OperationalError"
    assert model.finished_at is not None
    assert repo.find_completed_by_hash(HASH_A) is None


def test_import_repository_does_not_commit(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as s:
        SqlAlchemyImportRepository(s).record_failure("x.csv", HASH_A, RECEIVED_AT, "Boom")
        s.rollback()

    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(ImportModel)) == 0


# --------------------------------------------------------------- AnomalyRepository


def test_anomaly_lock_key_matches_plan() -> None:
    assert ANOMALY_LOCK_KEY == 815001


def test_replace_all_twice_keeps_one_row_per_transaction_and_method(session: Session) -> None:
    import_id = _add_import(session, ImportStatus.COMPLETED.value)
    tx1 = _add_transaction(session, import_id, date(2026, 1, 10), "-900.00")
    tx2 = _add_transaction(session, import_id, date(2026, 1, 11), "-800.00")
    candidates = [
        AnomalyCandidate(tx1, "zscore", Decimal("900.00"), "z-score 3.2"),
        AnomalyCandidate(tx1, "iqr", Decimal("900.00"), "acima de Q3 + 1.5*IQR"),
        AnomalyCandidate(tx2, "zscore", Decimal("800.00"), "z-score 3.0"),
    ]
    repo = SqlAlchemyAnomalyRepository(session)

    repo.replace_all(candidates)
    repo.replace_all(candidates)

    rows = session.execute(
        select(AnomalyModel.transaction_id, AnomalyModel.method, func.count()).group_by(
            AnomalyModel.transaction_id, AnomalyModel.method
        )
    ).all()
    assert sorted((r[0], r[1], r[2]) for r in rows) == sorted(
        [(tx1, "iqr", 1), (tx1, "zscore", 1), (tx2, "zscore", 1)]
    )


def test_replace_all_discards_previous_set(session: Session) -> None:
    import_id = _add_import(session, ImportStatus.COMPLETED.value)
    tx1 = _add_transaction(session, import_id, date(2026, 1, 10), "-900.00")
    tx2 = _add_transaction(session, import_id, date(2026, 1, 11), "-800.00")
    repo = SqlAlchemyAnomalyRepository(session)

    repo.replace_all([AnomalyCandidate(tx1, "zscore", Decimal("900.00"), "antiga")])
    repo.replace_all([AnomalyCandidate(tx2, "iqr", Decimal("800.00"), "nova")])

    rows = session.execute(select(AnomalyModel.transaction_id, AnomalyModel.method)).all()
    assert [tuple(r) for r in rows] == [(tx2, "iqr")]

    repo.replace_all([])
    assert _count(session, AnomalyModel) == 0


def test_list_filters_by_transaction_date_closed_interval(session: Session) -> None:
    import_id = _add_import(session, ImportStatus.COMPLETED.value)
    before = _add_transaction(session, import_id, date(2025, 12, 31), "-100.00")
    on_start = _add_transaction(session, import_id, date(2026, 1, 1), "-200.00")
    on_end = _add_transaction(session, import_id, date(2026, 1, 31), "-300.00")
    after = _add_transaction(session, import_id, date(2026, 2, 1), "-400.00")
    repo = SqlAlchemyAnomalyRepository(session)
    repo.replace_all(
        [
            AnomalyCandidate(tx, "zscore", Decimal(v), "motivo")
            for tx, v in ((before, "100"), (on_start, "200"), (on_end, "300"), (after, "400"))
        ]
    )

    result = repo.list(Period(date(2026, 1, 1), date(2026, 1, 31)))

    assert [a.transaction.id for a in result] == [on_end, on_start]


def test_list_orders_by_date_desc_then_id_desc_and_maps_transaction(session: Session) -> None:
    import_id = _add_import(session, ImportStatus.COMPLETED.value)
    category = CategoryModel(name="Mercado")
    session.add(category)
    session.flush()
    old = _add_transaction(session, import_id, date(2026, 1, 5), "-100.00")
    same_day = _add_transaction(session, import_id, date(2026, 1, 20), "-250.50", category.id)
    repo = SqlAlchemyAnomalyRepository(session)
    repo.replace_all(
        [
            AnomalyCandidate(old, "zscore", Decimal("100.00"), "z"),
            AnomalyCandidate(same_day, "zscore", Decimal("250.50"), "z"),
            AnomalyCandidate(same_day, "iqr", Decimal("250.50"), "iqr"),
        ]
    )

    result = repo.list(Period())

    assert [a.transaction.id for a in result] == [same_day, same_day, old]
    assert result[0].id > result[1].id
    first = result[0]
    assert first.value == Decimal("250.50")
    tx = first.transaction
    assert tx.date == date(2026, 1, 20)
    assert tx.amount == Decimal("-250.50")
    assert tx.type is TransactionType.EXPENSE
    assert tx.currency == "BRL"
    assert tx.merchant == "Mercado X"
    assert tx.category_id == category.id
    assert tx.category_name == "Mercado"
    assert tx.import_id == import_id


def test_list_with_open_bounds(session: Session) -> None:
    import_id = _add_import(session, ImportStatus.COMPLETED.value)
    early = _add_transaction(session, import_id, date(2026, 1, 1), "-100.00")
    late = _add_transaction(session, import_id, date(2026, 3, 1), "-200.00")
    repo = SqlAlchemyAnomalyRepository(session)
    repo.replace_all(
        [
            AnomalyCandidate(early, "zscore", Decimal("100.00"), "z"),
            AnomalyCandidate(late, "zscore", Decimal("200.00"), "z"),
        ]
    )

    assert [a.transaction.id for a in repo.list(Period(start=date(2026, 2, 1)))] == [late]
    assert [a.transaction.id for a in repo.list(Period(end=date(2026, 2, 1)))] == [early]

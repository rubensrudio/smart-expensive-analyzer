import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.entities import (
    Anomaly,
    AnomalyCandidate,
    CategorizableTransaction,
    CategorizationRule,
    Category,
    ExpenseFilters,
    ExpenseRecord,
    ImportRecord,
    ImportStatus,
    NewTransaction,
    Page,
    PageResult,
    Period,
    RowRejection,
    Transaction,
    TransactionFilters,
    TransactionType,
)


def _transaction() -> Transaction:
    return Transaction(
        id=1,
        date=date(2026, 1, 10),
        description="Compra mercado",
        merchant="Mercado X",
        amount=Decimal("-45.90"),
        currency="BRL",
        type=TransactionType.EXPENSE,
        category_id=2,
        category_name="Alimentação",
        import_id=3,
    )


# --- TransactionType.from_amount (LAC-20) ---


@pytest.mark.parametrize("amount", [Decimal("-10.00"), Decimal("-0.01"), Decimal("-1E+3")])
def test_from_amount_negative_is_expense(amount: Decimal) -> None:
    assert TransactionType.from_amount(amount) == TransactionType.EXPENSE


@pytest.mark.parametrize("amount", [Decimal("5"), Decimal("0.01"), Decimal("1234.56")])
def test_from_amount_positive_is_income(amount: Decimal) -> None:
    assert TransactionType.from_amount(amount) == TransactionType.INCOME


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-0"), Decimal("0.00")])
def test_from_amount_zero_raises_value_error(amount: Decimal) -> None:
    with pytest.raises(ValueError):
        TransactionType.from_amount(amount)


@pytest.mark.parametrize("amount", [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity")])
def test_from_amount_non_finite_raises_value_error(amount: Decimal) -> None:
    with pytest.raises(ValueError):
        TransactionType.from_amount(amount)


# --- Enums ---


def test_transaction_type_values() -> None:
    assert TransactionType.EXPENSE.value == "despesa"
    assert TransactionType.INCOME.value == "receita"
    assert TransactionType("despesa") is TransactionType.EXPENSE


def test_import_status_values() -> None:
    assert ImportStatus.PROCESSING.value == "processando"
    assert ImportStatus.COMPLETED.value == "concluida"
    assert ImportStatus.COMPLETED_WITH_REJECTIONS.value == "concluida_com_rejeicoes"
    assert ImportStatus.FAILED.value == "falhou"
    assert len(ImportStatus) == 4


# --- Defaults de filtros e paginação ---


def test_period_defaults_to_open_interval() -> None:
    period = Period()
    assert period.start is None
    assert period.end is None


def test_page_defaults() -> None:
    page = Page()
    assert page.limit == 50
    assert page.offset == 0


def test_transaction_filters_defaults() -> None:
    filters = TransactionFilters()
    assert filters.period == Period()
    assert filters.category_id is None
    assert filters.merchant is None
    assert filters.import_id is None


def test_expense_filters_defaults() -> None:
    filters = ExpenseFilters()
    assert filters.period == Period()
    assert filters.category_id is None
    assert filters.merchant is None


def test_page_result_holds_items_and_total() -> None:
    result: PageResult[Category] = PageResult(items=[Category(1, "A", False)], total=7)
    assert result.total == 7
    assert result.items[0].name == "A"


# --- Imutabilidade e slots (DA-1, CT-6) ---


def test_entities_are_frozen() -> None:
    category = Category(id=1, name="Não categorizada", is_default=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        category.name = "outra"  # type: ignore[misc]


def test_entities_use_slots() -> None:
    assert not hasattr(Category(1, "A", False), "__dict__")
    assert not hasattr(Period(), "__dict__")


@pytest.mark.parametrize(
    ("cls", "fields"),
    [
        (Category, ["id", "name", "is_default"]),
        (CategorizationRule, ["id", "keyword", "category_id", "priority", "created_at"]),
        (
            NewTransaction,
            [
                "date", "description", "merchant", "amount", "currency",
                "type", "category_id", "import_id", "dedup_key",
            ],
        ),
        (
            Transaction,
            [
                "id", "date", "description", "merchant", "amount", "currency",
                "type", "category_id", "category_name", "import_id",
            ],
        ),
        (CategorizableTransaction, ["id", "description", "merchant", "category_id"]),
        (RowRejection, ["line_number", "reason"]),
        (
            ImportRecord,
            [
                "id", "filename", "status", "received_at", "rows_read",
                "imported_count", "rejected_count", "duplicate_count", "rejections",
            ],
        ),
        (
            ExpenseRecord,
            [
                "transaction_id", "date", "value", "currency",
                "category_id", "category_name", "merchant",
            ],
        ),
        (AnomalyCandidate, ["transaction_id", "method", "value", "reason"]),
        (Anomaly, ["id", "method", "value", "reason", "transaction"]),
        (Period, ["start", "end"]),
        (Page, ["limit", "offset"]),
        (TransactionFilters, ["period", "category_id", "merchant", "import_id"]),
        (ExpenseFilters, ["period", "category_id", "merchant"]),
        (PageResult, ["items", "total"]),
    ],
)
def test_entity_fields_match_contract(cls: type, fields: list[str]) -> None:
    assert [f.name for f in dataclasses.fields(cls)] == fields
    params = cls.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen is True


def test_import_record_and_anomaly_compose() -> None:
    record = ImportRecord(
        id=1,
        filename="extrato.csv",
        status=ImportStatus.COMPLETED_WITH_REJECTIONS,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        rows_read=3,
        imported_count=2,
        rejected_count=1,
        duplicate_count=0,
        rejections=(RowRejection(line_number=3, reason="amount igual a zero"),),
    )
    anomaly = Anomaly(
        id=9, method="iqr", value=Decimal("45.90"), reason="acima", transaction=_transaction()
    )
    assert record.rejections[0].line_number == 3
    assert anomaly.transaction.type is TransactionType.EXPENSE


# --- Portas (CT-7) ---


def test_ports_module_declares_protocols() -> None:
    from typing import Protocol

    from app.domain import ports

    names = [
        "CategoryRepository",
        "CategorizationRuleRepository",
        "TransactionRepository",
        "ImportRepository",
        "AnomalyRepository",
        "UnitOfWork",
    ]
    for name in names:
        proto = getattr(ports, name)
        assert Protocol in proto.__mro__, name
        assert getattr(proto, "_is_protocol", False) is True, name


def test_ports_declare_contract_methods() -> None:
    from app.domain import ports

    expected = {
        "CategoryRepository": {"add", "get", "get_by_name_ci", "get_default", "list_all"},
        "CategorizationRuleRepository": {"add", "get", "list_all", "update", "delete"},
        "TransactionRepository": {
            "insert_ignoring_duplicates", "get", "list", "list_expenses",
            "list_all_for_categorization", "update_categories",
        },
        "ImportRepository": {
            "find_completed_by_hash", "create_processing", "finish", "record_failure",
        },
        "AnomalyRepository": {"replace_all", "list"},
        "UnitOfWork": {"commit", "rollback", "__enter__", "__exit__"},
    }
    for name, methods in expected.items():
        proto = getattr(ports, name)
        for method in methods:
            assert callable(getattr(proto, method, None)), f"{name}.{method}"


def test_unit_of_work_declares_repository_attributes() -> None:
    from app.domain import ports

    annotations = ports.UnitOfWork.__annotations__
    assert set(annotations) >= {"categories", "rules", "transactions", "imports", "anomalies"}

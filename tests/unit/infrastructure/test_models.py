"""Inspeção de `Base.metadata` e da fábrica de sessão (CT-4), sem banco."""

from typing import Any

import pytest
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db.models import (
    AnomalyModel,
    Base,
    CategorizationRuleModel,
    CategoryModel,
    ImportModel,
    ImportRejectionModel,
    TransactionModel,
)
from app.infrastructure.db.session import create_engine_from_url, create_session_factory

TABLES = Base.metadata.tables
URL = "postgresql+psycopg://u:p@localhost/x"


def _table(name: str) -> Table:
    return TABLES[name]


def _col(table: str, column: str) -> Column[Any]:
    return _table(table).c[column]


def _index(table: str, name: str) -> Index:
    matches = [ix for ix in _table(table).indexes if ix.name == name]
    assert len(matches) == 1, f"índice {name} ausente em {table}"
    return matches[0]


def _constraint(table: str, name: str) -> Any:
    matches = [c for c in _table(table).constraints if c.name == name]
    assert len(matches) == 1, f"constraint {name} ausente em {table}"
    return matches[0]


def _fk(table: str, column: str) -> ForeignKeyConstraint:
    fks = [
        fk for fk in _table(table).foreign_key_constraints if fk.column_keys == [column]
    ]
    assert len(fks) == 1, f"FK de {table}.{column} ausente"
    return fks[0]


def _compile(expr: Any) -> str:
    return str(expr.compile(dialect=postgresql.dialect()))


def test_metadata_has_exactly_the_six_tables() -> None:
    assert set(TABLES) == {
        "categories",
        "categorization_rules",
        "imports",
        "import_rejections",
        "transactions",
        "anomalies",
    }


def test_models_map_to_expected_tables() -> None:
    assert CategoryModel.__tablename__ == "categories"
    assert CategorizationRuleModel.__tablename__ == "categorization_rules"
    assert ImportModel.__tablename__ == "imports"
    assert ImportRejectionModel.__tablename__ == "import_rejections"
    assert TransactionModel.__tablename__ == "transactions"
    assert AnomalyModel.__tablename__ == "anomalies"


@pytest.mark.parametrize("table", sorted(TABLES))
def test_every_table_has_bigint_identity_by_default_pk(table: str) -> None:
    pk = list(_table(table).primary_key.columns)
    assert [c.name for c in pk] == ["id"]
    col = pk[0]
    assert isinstance(col.type, BigInteger)
    assert col.identity is not None
    assert not col.identity.always


def test_transactions_columns_types_and_nullability() -> None:
    amount = _col("transactions", "amount")
    assert isinstance(amount.type, Numeric)
    assert (amount.type.precision, amount.type.scale) == (14, 2)
    assert isinstance(_col("transactions", "date").type, Date)
    assert isinstance(_col("transactions", "description").type, Text)
    assert isinstance(_col("transactions", "merchant").type, Text)
    currency = _col("transactions", "currency").type
    assert isinstance(currency, String) and currency.length == 3
    assert "CHAR" in _compile(currency)
    tx_type = _col("transactions", "type").type
    assert isinstance(tx_type, String) and tx_type.length == 10
    dedup = _col("transactions", "dedup_key").type
    assert isinstance(dedup, String) and dedup.length == 64
    assert "CHAR" in _compile(dedup)
    created = _col("transactions", "created_at").type
    assert isinstance(created, DateTime) and created.timezone
    for column in _table("transactions").c:
        assert not column.nullable, f"transactions.{column.name} deveria ser NOT NULL"


def test_transactions_dedup_key_unique_constraint() -> None:
    uq = _constraint("transactions", "uq_transactions_dedup_key")
    assert isinstance(uq, UniqueConstraint)
    assert [c.name for c in uq.columns] == ["dedup_key"]


def test_transactions_checks_and_indexes() -> None:
    amount_ck = _constraint("transactions", "ck_transactions_amount_nonzero")
    assert isinstance(amount_ck, CheckConstraint)
    assert _compile(amount_ck.sqltext).replace(" ", "") == "amount<>0"
    type_ck = _constraint("transactions", "ck_transactions_type")
    assert isinstance(type_ck, CheckConstraint)
    sql = _compile(type_ck.sqltext)
    assert "'despesa'" in sql and "'receita'" in sql
    assert [c.name for c in _index("transactions", "ix_transactions_import").columns] == [
        "import_id"
    ]
    assert [c.name for c in _index("transactions", "ix_transactions_date").columns] == ["date"]
    assert [c.name for c in _index("transactions", "ix_transactions_category").columns] == [
        "category_id"
    ]
    assert [
        c.name for c in _index("transactions", "ix_transactions_currency_type").columns
    ] == ["currency", "type"]


def test_foreign_keys_and_on_delete_rules() -> None:
    expected = {
        ("categorization_rules", "category_id"): ("categories.id", "RESTRICT"),
        ("import_rejections", "import_id"): ("imports.id", "CASCADE"),
        ("transactions", "import_id"): ("imports.id", None),
        ("transactions", "category_id"): ("categories.id", "RESTRICT"),
        ("anomalies", "transaction_id"): ("transactions.id", "CASCADE"),
    }
    for (table, column), (target, ondelete) in expected.items():
        fk = _fk(table, column)
        assert fk.elements[0].target_fullname == target
        assert fk.ondelete == ondelete
    all_fks = sum(len(t.foreign_key_constraints) for t in TABLES.values())
    assert all_fks == len(expected)


def test_categories_case_insensitive_unique_and_partial_default_index() -> None:
    name = _col("categories", "name").type
    assert isinstance(name, String) and name.length == 100
    assert isinstance(_col("categories", "is_default").type, Boolean)
    assert _col("categories", "is_default").server_default is not None

    name_ci = _index("categories", "uq_categories_name_ci")
    assert name_ci.unique
    assert [_compile(e) for e in name_ci.expressions] == ["lower(categories.name)"]

    default_ix = _index("categories", "uq_categories_default")
    assert default_ix.unique
    assert [c.name for c in default_ix.columns] == ["is_default"]
    where = default_ix.dialect_options["postgresql"]["where"]
    assert where is not None
    assert "is_default" in _compile(where)


def test_categorization_rules_columns_and_order_index() -> None:
    keyword = _col("categorization_rules", "keyword").type
    assert isinstance(keyword, String) and keyword.length == 200
    assert isinstance(_col("categorization_rules", "priority").type, Integer)
    assert [c.name for c in _index("categorization_rules", "ix_rules_order").columns] == [
        "priority",
        "created_at",
        "id",
    ]


def test_imports_columns_check_and_index() -> None:
    assert _col("imports", "filename").type.length == 255  # type: ignore[attr-defined]
    assert "CHAR(64)" in _compile(_col("imports", "file_sha256").type)
    assert _col("imports", "finished_at").nullable
    assert _col("imports", "failure_reason").nullable
    assert _col("imports", "failure_reason").type.length == 500  # type: ignore[attr-defined]
    for counter in ("rows_read", "imported_count", "rejected_count", "duplicate_count"):
        column = _col("imports", counter)
        assert isinstance(column.type, Integer)
        assert not column.nullable
        assert column.server_default is not None
    status_ck = _constraint("imports", "ck_imports_status")
    sql = _compile(status_ck.sqltext)
    for status in ("processando", "concluida", "concluida_com_rejeicoes", "falhou"):
        assert f"'{status}'" in sql
    assert [c.name for c in _index("imports", "ix_imports_sha256_status").columns] == [
        "file_sha256",
        "status",
    ]


def test_import_rejections_columns() -> None:
    assert isinstance(_col("import_rejections", "line_number").type, Integer)
    assert _col("import_rejections", "reason").type.length == 500  # type: ignore[attr-defined]
    assert [
        c.name for c in _index("import_rejections", "ix_import_rejections_import").columns
    ] == ["import_id"]


def test_anomalies_columns_and_unique_transaction_method() -> None:
    value = _col("anomalies", "value").type
    assert isinstance(value, Numeric) and (value.precision, value.scale) == (14, 2)
    assert _col("anomalies", "method").type.length == 10  # type: ignore[attr-defined]
    assert isinstance(_col("anomalies", "reason").type, Text)
    uq = _constraint("anomalies", "uq_anomalies_transaction_method")
    assert isinstance(uq, UniqueConstraint)
    assert [c.name for c in uq.columns] == ["transaction_id", "method"]


def test_timestamps_are_timestamptz_with_now_default() -> None:
    for table, column in (
        ("categories", "created_at"),
        ("categorization_rules", "created_at"),
        ("imports", "received_at"),
        ("transactions", "created_at"),
        ("anomalies", "detected_at"),
    ):
        col = _col(table, column)
        assert isinstance(col.type, DateTime) and col.type.timezone
        assert not col.nullable
        assert col.server_default is not None
    finished = _col("imports", "finished_at").type
    assert isinstance(finished, DateTime) and finished.timezone


def test_create_engine_from_url_hides_parameters_without_connecting() -> None:
    engine = create_engine_from_url(URL)
    try:
        assert engine.hide_parameters is True
        assert engine.pool._pre_ping is True
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()


def test_create_session_factory_disables_expire_on_commit() -> None:
    engine = create_engine_from_url(URL)
    try:
        factory = create_session_factory(engine)
        assert isinstance(factory, sessionmaker)
        assert factory.kw["bind"] is engine
        assert factory.kw["expire_on_commit"] is False
        assert issubclass(factory.class_, Session)
    finally:
        engine.dispose()

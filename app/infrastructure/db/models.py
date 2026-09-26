"""Modelos ORM SQLAlchemy 2 (CT-4, seção 7 do plan).

Espelham exatamente o esquema criado pela migration `0001`. Não contêm regra de
negócio: validação e normalização ficam no domínio e nos serviços.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Literais repetidos aqui (e na migration) de propósito: a infraestrutura não
# depende de `app.domain.entities` para definir o esquema.
_TRANSACTION_TYPES = ("despesa", "receita")
_IMPORT_STATUSES = ("processando", "concluida", "concluida_com_rejeicoes", "falhou")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _pk() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=False), primary_key=True)


def _timestamp_now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _counter() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, server_default=text("0"))


class Base(DeclarativeBase):
    pass


class CategoryModel(Base):
    __tablename__ = "categories"
    __table_args__ = (
        Index(
            "uq_categories_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[int] = _pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    created_at: Mapped[datetime] = _timestamp_now()


# Índice funcional declarado fora da classe para referenciar a coluna mapeada.
Index("uq_categories_name_ci", func.lower(CategoryModel.name), unique=True)


class CategorizationRuleModel(Base):
    __tablename__ = "categorization_rules"
    __table_args__ = (Index("ix_rules_order", "priority", "created_at", "id"),)

    id: Mapped[int] = _pk()
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _timestamp_now()


class ImportModel(Base):
    __tablename__ = "imports"
    __table_args__ = (
        CheckConstraint(_in_list("status", _IMPORT_STATUSES), name="ck_imports_status"),
        Index("ix_imports_sha256_status", "file_sha256", "status"),
    )

    id: Mapped[int] = _pk()
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = _timestamp_now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_read: Mapped[int] = _counter()
    imported_count: Mapped[int] = _counter()
    rejected_count: Mapped[int] = _counter()
    duplicate_count: Mapped[int] = _counter()
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ImportRejectionModel(Base):
    __tablename__ = "import_rejections"
    __table_args__ = (Index("ix_import_rejections_import", "import_id"),)

    id: Mapped[int] = _pk()
    import_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("imports.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class TransactionModel(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_transactions_amount_nonzero"),
        CheckConstraint(_in_list("type", _TRANSACTION_TYPES), name="ck_transactions_type"),
        UniqueConstraint("dedup_key", name="uq_transactions_dedup_key"),
        Index("ix_transactions_import", "import_id"),
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_category", "category_id"),
        Index("ix_transactions_currency_type", "currency", "type"),
    )

    id: Mapped[int] = _pk()
    import_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("imports.id"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    merchant: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    dedup_key: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = _timestamp_now()


class AnomalyModel(Base):
    __tablename__ = "anomalies"
    __table_args__ = (
        UniqueConstraint("transaction_id", "method", name="uq_anomalies_transaction_method"),
    )

    id: Mapped[int] = _pk()
    transaction_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = _timestamp_now()

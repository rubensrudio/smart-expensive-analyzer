"""Schema inicial e categoria padrão "Não categorizada".

Revision ID: 0001
Revises:
Create Date: 2026-09-26

Cria as 6 tabelas da seção 7 do plan de forma explícita (sem autogenerate em
runtime). Nomes de constraints e índices iguais aos de `app/infrastructure/db/models.py`.
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literais repetidos de propósito: a migration não importa código da aplicação,
# para que o histórico continue reproduzível se os modelos mudarem.
_TRANSACTION_TYPES = ("despesa", "receita")
_IMPORT_STATUSES = ("processando", "concluida", "concluida_com_rejeicoes", "falhou")
_DEFAULT_CATEGORY_NAME = "Não categorizada"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def _pk() -> sa.Column[int]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True)


def _timestamp_now(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _counter(name: str) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), nullable=False, server_default=sa.text("0"))


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        _pk(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        _timestamp_now("created_at"),
    )
    op.create_index("uq_categories_name_ci", "categories", [sa.text("lower(name)")], unique=True)
    op.create_index(
        "uq_categories_default",
        "categories",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "categorization_rules",
        _pk(),
        sa.Column("keyword", sa.String(200), nullable=False),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        _timestamp_now("created_at"),
    )
    op.create_index("ix_rules_order", "categorization_rules", ["priority", "created_at", "id"])

    op.create_table(
        "imports",
        _pk(),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _timestamp_now("received_at"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _counter("rows_read"),
        _counter("imported_count"),
        _counter("rejected_count"),
        _counter("duplicate_count"),
        sa.Column("failure_reason", sa.String(500), nullable=True),
        sa.CheckConstraint(_in_list("status", _IMPORT_STATUSES), name="ck_imports_status"),
    )
    op.create_index("ix_imports_sha256_status", "imports", ["file_sha256", "status"])

    op.create_table(
        "import_rejections",
        _pk(),
        sa.Column(
            "import_id",
            sa.BigInteger(),
            sa.ForeignKey("imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
    )
    op.create_index("ix_import_rejections_import", "import_rejections", ["import_id"])

    op.create_table(
        "transactions",
        _pk(),
        sa.Column("import_id", sa.BigInteger(), sa.ForeignKey("imports.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("merchant", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column(
            "category_id",
            sa.BigInteger(),
            sa.ForeignKey("categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("dedup_key", sa.CHAR(64), nullable=False),
        _timestamp_now("created_at"),
        sa.CheckConstraint("amount <> 0", name="ck_transactions_amount_nonzero"),
        sa.CheckConstraint(_in_list("type", _TRANSACTION_TYPES), name="ck_transactions_type"),
        sa.UniqueConstraint("dedup_key", name="uq_transactions_dedup_key"),
    )
    op.create_index("ix_transactions_import", "transactions", ["import_id"])
    op.create_index("ix_transactions_date", "transactions", ["date"])
    op.create_index("ix_transactions_category", "transactions", ["category_id"])
    op.create_index("ix_transactions_currency_type", "transactions", ["currency", "type"])

    op.create_table(
        "anomalies",
        _pk(),
        sa.Column(
            "transaction_id",
            sa.BigInteger(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _timestamp_now("detected_at"),
        sa.UniqueConstraint("transaction_id", "method", name="uq_anomalies_transaction_method"),
    )

    op.bulk_insert(categories, [{"name": _DEFAULT_CATEGORY_NAME, "is_default": True}])


def downgrade() -> None:
    # Ordem reversa de FK. Os índices caem junto com as tabelas.
    op.drop_table("anomalies")
    op.drop_table("transactions")
    op.drop_table("import_rejections")
    op.drop_table("imports")
    op.drop_table("categorization_rules")
    op.drop_table("categories")

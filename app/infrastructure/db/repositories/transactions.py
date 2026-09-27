"""Repositório SQLAlchemy de transações (CT-24, cumpre `TransactionRepository` de CT-7).

Não faz commit: a transação do banco pertence ao Unit of Work (DA-2).
"""

import builtins
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ColumnElement, Row, Select, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.entities import (
    CategorizableTransaction,
    ExpenseFilters,
    ExpenseRecord,
    NewTransaction,
    Page,
    PageResult,
    Period,
    Transaction,
    TransactionFilters,
    TransactionType,
)
from app.domain.text import normalize_whitespace
from app.infrastructure.db.models import CategoryModel, TransactionModel

_T = TransactionModel

# 9 colunas por linha: 1000 linhas ficam bem abaixo do limite de 65535 parâmetros do PostgreSQL.
_INSERT_CHUNK_SIZE = 1000


def _period_conditions(period: Period) -> list[ColumnElement[bool]]:
    """Intervalo fechado: inclui as datas de início e fim."""
    conditions: list[ColumnElement[bool]] = []
    if period.start is not None:
        conditions.append(_T.date >= period.start)
    if period.end is not None:
        conditions.append(_T.date <= period.end)
    return conditions


def _common_conditions(
    period: Period, category_id: int | None, merchant: str | None
) -> list[ColumnElement[bool]]:
    conditions = _period_conditions(period)
    if category_id is not None:
        conditions.append(_T.category_id == category_id)
    if merchant is not None:
        # P-09: igualdade sem distinguir caixa, após normalizar espaços.
        conditions.append(func.lower(_T.merchant) == func.lower(normalize_whitespace(merchant)))
    return conditions


def _transaction_select() -> Select[tuple[TransactionModel, str]]:
    return select(_T, CategoryModel.name).join(CategoryModel, CategoryModel.id == _T.category_id)


def _to_transaction(row: Row[tuple[TransactionModel, str]]) -> Transaction:
    model, category_name = row
    return Transaction(
        id=model.id,
        date=model.date,
        description=model.description,
        merchant=model.merchant,
        amount=model.amount,
        currency=model.currency,
        type=TransactionType(model.type),
        category_id=model.category_id,
        category_name=category_name,
        import_id=model.import_id,
    )


def _to_row_values(item: NewTransaction) -> dict[str, Any]:
    return {
        "import_id": item.import_id,
        "date": item.date,
        "description": item.description,
        "merchant": item.merchant,
        "amount": item.amount,
        "currency": item.currency,
        "type": item.type.value,
        "category_id": item.category_id,
        "dedup_key": item.dedup_key,
    }


class SqlAlchemyTransactionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert_ignoring_duplicates(self, items: Sequence[NewTransaction]) -> int:
        """`INSERT ... ON CONFLICT (dedup_key) DO NOTHING RETURNING id` (DA-6, SEA-106)."""
        inserted = 0
        for start in range(0, len(items), _INSERT_CHUNK_SIZE):
            chunk = items[start : start + _INSERT_CHUNK_SIZE]
            stmt = (
                insert(_T)
                .values([_to_row_values(item) for item in chunk])
                .on_conflict_do_nothing(index_elements=["dedup_key"])
                .returning(_T.id)
            )
            inserted += len(self._session.execute(stmt).scalars().all())
        return inserted

    def get(self, transaction_id: int) -> Transaction | None:
        row = self._session.execute(_transaction_select().where(_T.id == transaction_id)).first()
        return _to_transaction(row) if row is not None else None

    def list(self, filters: TransactionFilters, page: Page) -> PageResult[Transaction]:
        conditions = _common_conditions(filters.period, filters.category_id, filters.merchant)
        if filters.import_id is not None:
            conditions.append(_T.import_id == filters.import_id)

        total = self._session.execute(
            select(func.count()).select_from(_T).where(*conditions)
        ).scalar_one()
        rows = self._session.execute(
            _transaction_select()
            .where(*conditions)
            .order_by(_T.date.desc(), _T.id.desc())
            .limit(page.limit)
            .offset(page.offset)
        ).all()
        return PageResult(items=[_to_transaction(row) for row in rows], total=total)

    def list_expenses(self, filters: ExpenseFilters) -> builtins.list[ExpenseRecord]:
        """Só `type='despesa'`, com `value = abs(amount)` (LAC-03, LAC-20)."""
        conditions = _common_conditions(filters.period, filters.category_id, filters.merchant)
        rows = self._session.execute(
            select(
                _T.id,
                _T.date,
                func.abs(_T.amount),
                _T.currency,
                _T.category_id,
                CategoryModel.name,
                _T.merchant,
            )
            .join(CategoryModel, CategoryModel.id == _T.category_id)
            .where(_T.type == TransactionType.EXPENSE.value, *conditions)
            .order_by(_T.date, _T.id)
        ).all()
        return [
            ExpenseRecord(
                transaction_id=tx_id,
                date=tx_date,
                value=value,
                currency=currency,
                category_id=category_id,
                category_name=category_name,
                merchant=merchant,
            )
            for tx_id, tx_date, value, currency, category_id, category_name, merchant in rows
        ]

    def list_all_for_categorization(self) -> builtins.list[CategorizableTransaction]:
        rows = self._session.execute(
            select(_T.id, _T.description, _T.merchant, _T.category_id).order_by(_T.id)
        ).all()
        return [
            CategorizableTransaction(
                id=tx_id, description=description, merchant=merchant, category_id=category_id
            )
            for tx_id, description, merchant, category_id in rows
        ]

    def update_categories(self, changes: Mapping[int, int]) -> None:
        """Update em lote por chave primária: `transaction_id -> category_id`."""
        if not changes:
            return
        self._session.execute(
            update(_T),
            [
                {"id": transaction_id, "category_id": category_id}
                for transaction_id, category_id in changes.items()
            ],
        )

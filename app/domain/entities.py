"""Entidades, enums e filtros de domínio (CT-6, DA-1).

Tipos imutáveis (dataclasses ``frozen=True, slots=True``) e sem dependência
de framework web, ORM ou biblioteca de dataframes.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class TransactionType(StrEnum):
    EXPENSE = "despesa"
    INCOME = "receita"

    @classmethod
    def from_amount(cls, amount: Decimal) -> "TransactionType":
        """Negativo = despesa, positivo = receita, zero = inválido (LAC-20)."""
        if not amount.is_finite():
            raise ValueError("amount deve ser um número finito")
        if amount.is_zero():
            raise ValueError("amount igual a zero não define tipo de transação")
        return cls.EXPENSE if amount < 0 else cls.INCOME


class ImportStatus(StrEnum):
    PROCESSING = "processando"
    COMPLETED = "concluida"
    COMPLETED_WITH_REJECTIONS = "concluida_com_rejeicoes"
    FAILED = "falhou"


@dataclass(frozen=True, slots=True)
class Category:
    id: int
    name: str
    is_default: bool


@dataclass(frozen=True, slots=True)
class CategorizationRule:
    id: int
    keyword: str
    category_id: int
    priority: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NewTransaction:
    date: date
    description: str
    merchant: str
    amount: Decimal
    currency: str
    type: TransactionType
    category_id: int
    import_id: int
    dedup_key: str


@dataclass(frozen=True, slots=True)
class Transaction:
    id: int
    date: date
    description: str
    merchant: str
    amount: Decimal
    currency: str
    type: TransactionType
    category_id: int
    category_name: str
    import_id: int


@dataclass(frozen=True, slots=True)
class CategorizableTransaction:
    id: int
    description: str
    merchant: str
    category_id: int


@dataclass(frozen=True, slots=True)
class RowRejection:
    line_number: int
    reason: str


@dataclass(frozen=True, slots=True)
class ImportRecord:
    id: int
    filename: str
    status: ImportStatus
    received_at: datetime
    rows_read: int
    imported_count: int
    rejected_count: int
    duplicate_count: int
    rejections: tuple[RowRejection, ...]


@dataclass(frozen=True, slots=True)
class ExpenseRecord:
    """Despesa para cálculos. ``value`` é o módulo de ``amount`` (LAC-20)."""

    transaction_id: int
    date: date
    value: Decimal
    currency: str
    category_id: int
    category_name: str
    merchant: str


@dataclass(frozen=True, slots=True)
class AnomalyCandidate:
    transaction_id: int
    method: str
    value: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class Anomaly:
    id: int
    method: str
    value: Decimal
    reason: str
    transaction: Transaction


@dataclass(frozen=True, slots=True)
class Period:
    """Intervalo fechado de datas. ``None`` = sem limite naquele lado."""

    start: date | None = None
    end: date | None = None


@dataclass(frozen=True, slots=True)
class Page:
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class TransactionFilters:
    period: Period = field(default_factory=Period)
    category_id: int | None = None
    merchant: str | None = None
    import_id: int | None = None


@dataclass(frozen=True, slots=True)
class ExpenseFilters:
    period: Period = field(default_factory=Period)
    category_id: int | None = None
    merchant: str | None = None


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    items: list[T]
    total: int

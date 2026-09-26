"""Portas de persistência do domínio (CT-7, DA-1).

Protocols estruturais: a infraestrutura cumpre o contrato sem herdar daqui.
Nenhum método de repositório faz commit; isso é papel do ``UnitOfWork``.
"""

import builtins
from collections.abc import Mapping, Sequence
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

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
)


class CategoryRepository(Protocol):
    def add(self, name: str) -> Category: ...

    def get(self, category_id: int) -> Category | None: ...

    def get_by_name_ci(self, name: str) -> Category | None: ...

    def get_default(self) -> Category: ...

    def list_all(self) -> list[Category]: ...


class CategorizationRuleRepository(Protocol):
    def add(self, keyword: str, category_id: int, priority: int) -> CategorizationRule: ...

    def get(self, rule_id: int) -> CategorizationRule | None: ...

    def list_all(self) -> list[CategorizationRule]:
        """Ordem: ``priority``, ``created_at``, ``id``."""
        ...

    def update(
        self, rule_id: int, keyword: str, category_id: int, priority: int
    ) -> CategorizationRule | None: ...

    def delete(self, rule_id: int) -> bool: ...


class TransactionRepository(Protocol):
    # `builtins.list` evita colisão com o método `list` no escopo da classe.
    def insert_ignoring_duplicates(self, items: Sequence[NewTransaction]) -> int:
        """Insere ignorando ``dedup_key`` repetida. Retorna quantas linhas entraram."""
        ...

    def get(self, transaction_id: int) -> Transaction | None: ...

    def list(self, filters: TransactionFilters, page: Page) -> PageResult[Transaction]: ...

    def list_expenses(self, filters: ExpenseFilters) -> builtins.list[ExpenseRecord]:
        """Só ``type='despesa'``, com ``value = abs(amount)``."""
        ...

    def list_all_for_categorization(self) -> builtins.list[CategorizableTransaction]: ...

    def update_categories(self, changes: Mapping[int, int]) -> None:
        """``changes``: ``transaction_id -> category_id``."""
        ...


class ImportRepository(Protocol):
    def find_completed_by_hash(self, file_sha256: str) -> int | None:
        """Id do Import com status ``concluida`` ou ``concluida_com_rejeicoes``."""
        ...

    def create_processing(self, filename: str, file_sha256: str, received_at: datetime) -> int: ...

    def finish(
        self,
        import_id: int,
        status: ImportStatus,
        rows_read: int,
        imported_count: int,
        rejected_count: int,
        duplicate_count: int,
        rejections: Sequence[RowRejection],
    ) -> ImportRecord: ...

    def record_failure(
        self, filename: str, file_sha256: str, received_at: datetime, reason: str
    ) -> int: ...


class AnomalyRepository(Protocol):
    def replace_all(self, candidates: Sequence[AnomalyCandidate]) -> None: ...

    def list(self, period: Period) -> builtins.list[Anomaly]: ...


class UnitOfWork(Protocol):
    categories: CategoryRepository
    rules: CategorizationRuleRepository
    transactions: TransactionRepository
    imports: ImportRepository
    anomalies: AnomalyRepository

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Faz rollback se houve exceção e sempre fecha a sessão."""
        ...

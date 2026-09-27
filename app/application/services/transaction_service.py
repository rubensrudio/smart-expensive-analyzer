"""Consulta de transações sobre a unidade de trabalho (CT-19)."""

from dataclasses import replace

from app.core.errors import TransactionNotFoundError
from app.domain.entities import Page, PageResult, Transaction, TransactionFilters
from app.domain.ports import UnitOfWork
from app.domain.text import normalize_whitespace


class TransactionService:
    """Serviço fino de leitura: busca por id e listagem filtrada e paginada."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def get(self, transaction_id: int) -> Transaction:
        transaction = self._uow.transactions.get(transaction_id)
        if transaction is None:
            raise TransactionNotFoundError()
        return transaction

    def list(self, filters: TransactionFilters, page: Page) -> PageResult[Transaction]:
        # P-09: igualdade sem caixa após normalizar espaços. A caixa fica com o repositório.
        if filters.merchant is not None:
            filters = replace(filters, merchant=normalize_whitespace(filters.merchant))
        return self._uow.transactions.list(filters, page)

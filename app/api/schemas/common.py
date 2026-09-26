"""Schemas compartilhados entre routers (CT-22, 8.1).

P-13: dinheiro vai no JSON como string com 2 casas, sem ponto flutuante.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

from app.domain.entities import Transaction, TransactionType


def _format_money(value: Decimal) -> str:
    return f"{value:.2f}"


Money = Annotated[Decimal, PlainSerializer(_format_money, return_type=str)]


class CategoryRef(BaseModel):
    id: int
    name: str


class TransactionOut(BaseModel):
    id: int
    date: date
    description: str
    merchant: str
    amount: Money
    currency: str
    type: TransactionType
    category: CategoryRef
    import_id: int

    @classmethod
    def from_entity(cls, t: Transaction) -> "TransactionOut":
        return cls(
            id=t.id,
            date=t.date,
            description=t.description,
            merchant=t.merchant,
            amount=t.amount,
            currency=t.currency,
            type=t.type,
            category=CategoryRef(id=t.category_id, name=t.category_name),
            import_id=t.import_id,
        )

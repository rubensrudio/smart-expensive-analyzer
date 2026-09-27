from datetime import date
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.api.schemas.common import CategoryRef, Money, TransactionOut
from app.domain.entities import Transaction, TransactionType


class _MoneyHolder(BaseModel):
    value: Money


def _transaction(amount: Decimal = Decimal("-45.9")) -> Transaction:
    return Transaction(
        id=7,
        date=date(2026, 1, 15),
        description="Compra mercado",
        merchant="Mercado X",
        amount=amount,
        currency="BRL",
        type=TransactionType.from_amount(amount),
        category_id=3,
        category_name="Alimentação",
        import_id=2,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("90"), "90.00"),
        (Decimal("-45.9"), "-45.90"),
        (Decimal("0.5"), "0.50"),
        (Decimal("1234567.891"), "1234567.89"),
    ],
)
def test_money_serializes_as_two_decimal_string(value: Decimal, expected: str) -> None:
    assert _MoneyHolder(value=value).model_dump(mode="json") == {"value": expected}


def test_money_json_schema_is_string() -> None:
    schema = _MoneyHolder.model_json_schema(mode="serialization")
    assert schema["properties"]["value"]["type"] == "string"


def test_category_ref_fields() -> None:
    assert CategoryRef(id=1, name="Lazer").model_dump() == {"id": 1, "name": "Lazer"}


def test_transaction_out_from_entity_serializes_contract_fields() -> None:
    out = TransactionOut.from_entity(_transaction())
    assert out.model_dump(mode="json") == {
        "id": 7,
        "date": "2026-01-15",
        "description": "Compra mercado",
        "merchant": "Mercado X",
        "amount": "-45.90",
        "currency": "BRL",
        "type": "despesa",
        "category": {"id": 3, "name": "Alimentação"},
        "import_id": 2,
    }


def test_transaction_out_income_keeps_positive_amount_and_type() -> None:
    payload = TransactionOut.from_entity(_transaction(Decimal("1500"))).model_dump(mode="json")
    assert payload["amount"] == "1500.00"
    assert payload["type"] == "receita"
    assert payload["category"]["name"] == "Alimentação"

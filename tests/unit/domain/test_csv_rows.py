import dataclasses
import hashlib
import re
from datetime import date
from decimal import Decimal

import pytest

from app.domain.csv_rows import ParsedRow, dedup_key, format_rejection, parse_row
from app.domain.entities import RowRejection, TransactionType

VALID = {"date": "2026-01-15", "description": "Padaria", "amount": "-45.9"}


def _row(**overrides: str) -> dict[str, str]:
    values = dict(VALID)
    values.update(overrides)
    return values


def _parse(values: dict[str, str], default_currency: str = "BRL") -> ParsedRow:
    result = parse_row(7, values, default_currency)
    assert isinstance(result, ParsedRow), result
    return result


def _reject(values: dict[str, str]) -> RowRejection:
    result = parse_row(7, values, "BRL")
    assert isinstance(result, RowRejection), result
    return result


def test_valid_negative_amount_becomes_expense_with_two_decimals() -> None:
    assert _parse(_row()) == ParsedRow(
        line_number=7,
        date=date(2026, 1, 15),
        description="Padaria",
        merchant="Padaria",
        amount=Decimal("-45.90"),
        currency="BRL",
        type=TransactionType.EXPENSE,
    )


def test_positive_amount_becomes_income() -> None:
    parsed = _parse(_row(amount="+1200"))
    assert parsed.amount == Decimal("1200.00")
    assert parsed.type is TransactionType.INCOME


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.005", Decimal("10.01")),
        ("-10.005", Decimal("-10.01")),
        ("10.004", Decimal("10.00")),
        (" 3 ", Decimal("3.00")),
        ("0010.5", Decimal("10.50")),
    ],
)
def test_amount_is_rounded_half_up_to_two_places(raw: str, expected: Decimal) -> None:
    assert _parse(_row(amount=raw)).amount == expected


@pytest.mark.parametrize("raw", ["0.00", "0", "-0", "0.004", "-0.001"])
def test_zero_amount_after_rounding_is_rejected(raw: str) -> None:
    assert _reject(_row(amount=raw)) == RowRejection(7, "valor igual a zero")


@pytest.mark.parametrize(
    "raw",
    ["1,50", "1.000,00", "1e3", "abc", "NaN", "Infinity", "--1", "1.", ".5", "1 000", "R$10", "١٢"],
)
def test_non_numeric_amount_is_rejected(raw: str) -> None:
    assert _reject(_row(amount=raw)) == RowRejection(7, "valor não numérico")


@pytest.mark.parametrize("raw", ["", "   "])
def test_missing_amount_is_rejected(raw: str) -> None:
    assert _reject(_row(amount=raw)) == RowRejection(7, "valor ausente")


def test_absurdly_long_amount_is_rejected_without_crashing() -> None:
    assert _reject(_row(amount="9" * 60)).reason == "valor não numérico"


@pytest.mark.parametrize(
    "raw",
    ["1234567890123.00", "1000000000000", "-1000000000000.00", "999999999999.995"],
)
def test_amount_beyond_numeric_14_2_is_rejected_as_non_numeric(raw: str) -> None:
    assert _reject(_row(amount=raw)) == RowRejection(7, "valor não numérico")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("999999999999.99", Decimal("999999999999.99")),
        ("-999999999999.994", Decimal("-999999999999.99")),
    ],
)
def test_amount_at_numeric_14_2_limit_is_accepted(raw: str, expected: Decimal) -> None:
    assert _parse(_row(amount=raw)).amount == expected


@pytest.mark.parametrize(
    "raw",
    [
        "2026-02-30",
        "2026-13-01",
        "15/01/2026",
        "20260115",
        "2026-1-15",
        "2026-01-15T00:00",
        "２０２６-01-15",
    ],
)
def test_invalid_date_is_rejected(raw: str) -> None:
    assert _reject(_row(date=raw)) == RowRejection(7, "data inválida")


def test_date_with_surrounding_spaces_is_accepted() -> None:
    assert _parse(_row(date=" 2024-02-29 ")).date == date(2024, 2, 29)


@pytest.mark.parametrize("raw", ["", "  "])
def test_missing_date_is_rejected(raw: str) -> None:
    assert _reject(_row(date=raw)) == RowRejection(7, "data ausente")


def test_missing_keys_are_treated_as_empty() -> None:
    result = parse_row(3, {}, "BRL")
    assert result == RowRejection(3, "data ausente; descrição vazia; valor ausente")


@pytest.mark.parametrize("raw", ["", "   ", "\t"])
def test_blank_description_is_rejected(raw: str) -> None:
    assert _reject(_row(description=raw)) == RowRejection(7, "descrição vazia")


def test_description_whitespace_is_normalized() -> None:
    assert _parse(_row(description="  a   b ")).description == "a b"


def test_empty_merchant_falls_back_to_normalized_description() -> None:
    parsed = _parse(_row(description="  Mercado   Central ", merchant="   "))
    assert parsed.merchant == "Mercado Central"


def test_absent_merchant_falls_back_to_normalized_description() -> None:
    assert _parse(_row(description=" Uber  Trip")).merchant == "Uber Trip"


def test_merchant_is_normalized_when_present() -> None:
    assert _parse(_row(merchant="  Loja   X ")).merchant == "Loja X"


def test_currency_code_is_uppercased() -> None:
    assert _parse(_row(currency="usd")).currency == "USD"


@pytest.mark.parametrize("raw", ["", "   "])
def test_empty_currency_uses_default(raw: str) -> None:
    assert _parse(_row(currency=raw), default_currency="EUR").currency == "EUR"


def test_absent_currency_uses_default() -> None:
    assert _parse(_row(), default_currency="USD").currency == "USD"


@pytest.mark.parametrize("raw", ["xx1", "XYZ", "HRK", "reais"])
def test_currency_outside_iso_4217_is_rejected(raw: str) -> None:
    assert _reject(_row(currency=raw)) == RowRejection(7, "moeda fora da ISO 4217")


def test_all_reasons_are_joined_in_contract_order() -> None:
    result = _reject({"date": "2026-02-30", "description": " ", "amount": "1,5", "currency": "zz"})
    assert result.reason == (
        "data inválida; descrição vazia; valor não numérico; moeda fora da ISO 4217"
    )


def test_rejection_reasons_never_contain_cell_content() -> None:
    secret = "SEGREDO-123"
    result = _reject({"date": secret, "description": "", "amount": secret, "currency": secret})
    assert secret not in result.reason
    assert secret.lower() not in result.reason.lower()


def test_parsed_row_is_frozen() -> None:
    parsed = _parse(_row())
    with pytest.raises(dataclasses.FrozenInstanceError):
        parsed.amount = Decimal("1")  # type: ignore[misc]


def test_format_rejection() -> None:
    assert format_rejection(RowRejection(12, "data inválida")) == "Linha 12: data inválida"


def test_dedup_key_is_deterministic_sha256_hex() -> None:
    first = dedup_key(date(2026, 1, 15), Decimal("-45.90"), "Padaria", "BRL")
    second = dedup_key(date(2026, 1, 15), Decimal("-45.90"), "Padaria", "BRL")
    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)


def test_dedup_key_matches_da6_formula() -> None:
    expected = hashlib.sha256(b"2026-01-15|-45.90|Padaria|BRL").hexdigest()
    assert dedup_key(date(2026, 1, 15), Decimal("-45.9"), "Padaria", "BRL") == expected


@pytest.mark.parametrize(
    ("args"),
    [
        (date(2026, 1, 16), Decimal("-45.90"), "Padaria", "BRL"),
        (date(2026, 1, 15), Decimal("45.90"), "Padaria", "BRL"),
        (date(2026, 1, 15), Decimal("-45.90"), "padaria", "BRL"),
        (date(2026, 1, 15), Decimal("-45.90"), "Padaria", "USD"),
    ],
)
def test_dedup_key_changes_with_each_field(args: tuple[date, Decimal, str, str]) -> None:
    base = dedup_key(date(2026, 1, 15), Decimal("-45.90"), "Padaria", "BRL")
    assert dedup_key(*args) != base

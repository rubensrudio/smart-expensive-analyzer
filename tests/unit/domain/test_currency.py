import pytest

from app.domain.currency import ISO_4217_CODES, normalize_currency_code


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("brl", "BRL"),
        (" usd ", "USD"),
        ("EUR", "EUR"),
        ("\tjpy\n", "JPY"),
    ],
)
def test_normalize_returns_uppercase_code_for_known_codes(raw: str, expected: str) -> None:
    assert normalize_currency_code(raw) == expected


@pytest.mark.parametrize("raw", ["XYZ", "BR", "BRLL", "R$", "12A", "b r l"])
def test_normalize_returns_none_for_unknown_codes(raw: str) -> None:
    assert normalize_currency_code(raw) is None


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_normalize_returns_none_for_empty_input(raw: str) -> None:
    assert normalize_currency_code(raw) is None


def test_iso_codes_has_at_least_150_active_codes() -> None:
    assert len(ISO_4217_CODES) >= 150


def test_iso_codes_is_frozenset_of_three_uppercase_letters() -> None:
    assert isinstance(ISO_4217_CODES, frozenset)
    assert all(len(c) == 3 and c.isascii() and c.isalpha() and c.isupper() for c in ISO_4217_CODES)


def test_iso_codes_excludes_withdrawn_codes() -> None:
    assert {"BRL", "USD", "EUR"} <= ISO_4217_CODES
    assert not {"DEM", "FRF", "HRK", "VEF", "ZWL"} & ISO_4217_CODES

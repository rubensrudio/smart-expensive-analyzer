import pytest

from app.domain.text import fold_for_match, normalize_whitespace


def test_normalize_whitespace_strips_and_collapses_mixed_whitespace() -> None:
    assert normalize_whitespace("  PADARIA   São\tJoão ") == "PADARIA São João"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a\n\nb", "a b"),
        ("\t a \r\n b \t", "a b"),
        ("a  b", "a b"),
        ("sem-espaco", "sem-espaco"),
    ],
)
def test_normalize_whitespace_handles_any_whitespace_sequence(raw: str, expected: str) -> None:
    assert normalize_whitespace(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "\t\n\r "])
def test_normalize_whitespace_returns_empty_for_blank_input(raw: str) -> None:
    assert normalize_whitespace(raw) == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AÇAÍ DA PRAIA", "acai da praia"),
        ("São João", "sao joao"),
        ("Uber Trip", "uber trip"),
        ("ÀÉÎÕÜ ñ", "aeiou n"),
        ("Straße", "strasse"),
    ],
)
def test_fold_for_match_removes_accents_and_case(raw: str, expected: str) -> None:
    assert fold_for_match(raw) == expected


def test_fold_for_match_applies_compatibility_decomposition() -> None:
    assert fold_for_match("ＵＢＥＲ") == "uber"


def test_fold_for_match_is_idempotent() -> None:
    once = fold_for_match("Café Ação")
    assert fold_for_match(once) == once


def test_fold_for_match_returns_empty_for_empty_input() -> None:
    assert fold_for_match("") == ""

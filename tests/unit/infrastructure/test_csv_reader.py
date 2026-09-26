import dataclasses

import pytest

from app.core.errors import EmptyFileError, InvalidCsvError, MissingColumnsError
from app.infrastructure.csv_reader import REQUIRED_COLUMNS, RawRow, read_csv_rows

HEADER = "date,description,amount"


def _csv(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_required_columns_are_in_contract_order() -> None:
    assert REQUIRED_COLUMNS == ("date", "description", "amount")


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"   \n\t\n",
        _csv(HEADER),
        HEADER.encode("utf-8"),
        _csv(HEADER, "", ""),
        _csv(HEADER, ",,", "  ,  ,  "),
    ],
    ids=[
        "no-bytes",
        "only-whitespace",
        "header-only",
        "header-no-newline",
        "header-blank-lines",
        "header-blank-cells",
    ],
)
def test_file_without_data_rows_raises_empty_file(content: bytes) -> None:
    with pytest.raises(EmptyFileError):
        read_csv_rows(content)


@pytest.mark.parametrize(
    "content",
    [
        b"\xff\xfe\x00d",
        b"date,description,amount\n2026-01-01,caf\xe9,1\n",
        b"date,description,amount\n2026-01-01,a\x00b,1\n",
    ],
    ids=["utf16-bom", "latin1", "nul-byte"],
)
def test_non_utf8_or_binary_content_raises_invalid_csv(content: bytes) -> None:
    with pytest.raises(InvalidCsvError):
        read_csv_rows(content)


def test_invalid_csv_error_does_not_chain_the_original_exception() -> None:
    with pytest.raises(InvalidCsvError) as info:
        read_csv_rows(b"date,description,amount\n2026-01-01,caf\xe9,1\n")
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__ is True


def test_row_with_more_fields_than_header_raises_invalid_csv() -> None:
    with pytest.raises(InvalidCsvError):
        read_csv_rows(_csv(HEADER, "2026-01-01,a,1,extra"))


def test_missing_description_column_is_reported() -> None:
    with pytest.raises(MissingColumnsError) as info:
        read_csv_rows(_csv("date,amount", "2026-01-01,1"))
    assert info.value.details == ["description"]


def test_missing_columns_are_listed_in_contract_order() -> None:
    with pytest.raises(MissingColumnsError) as info:
        read_csv_rows(_csv("merchant,foo", "x,y"))
    assert info.value.details == ["date", "description", "amount"]


def test_missing_columns_takes_precedence_over_empty_file() -> None:
    with pytest.raises(MissingColumnsError):
        read_csv_rows(_csv("date,amount"))


def test_header_names_are_stripped_and_lowercased_and_extras_ignored() -> None:
    rows = read_csv_rows(_csv(" Date , DESCRIPTION,Amount ,Extra", "2026-01-01,Mercado,-10,x"))
    assert rows == [RawRow(2, {"date": "2026-01-01", "description": "Mercado", "amount": "-10"})]


def test_utf8_bom_is_removed_from_first_column() -> None:
    rows = read_csv_rows(b"\xef\xbb\xbf" + _csv(HEADER, "2026-01-01,a,1"))
    assert rows[0].values["date"] == "2026-01-01"


def test_optional_columns_are_kept_when_present() -> None:
    rows = read_csv_rows(_csv("date,description,amount,merchant,currency", "2026-01-01,a,1,M,usd"))
    assert dict(rows[0].values) == {
        "date": "2026-01-01",
        "description": "a",
        "amount": "1",
        "merchant": "M",
        "currency": "usd",
    }


def test_blank_lines_are_skipped_and_line_numbers_are_physical() -> None:
    rows = read_csv_rows(_csv(HEADER, "2026-01-01,a,1", "", "2026-01-02,b,2"))
    assert [r.line_number for r in rows] == [2, 4]
    assert [r.values["description"] for r in rows] == ["a", "b"]


def test_line_numbers_account_for_blank_cells_rows_and_crlf() -> None:
    content = "\r\n".join([HEADER, "", ",,", "2026-01-01,a,1", "  ", "2026-01-02,b,2"]).encode()
    rows = read_csv_rows(content)
    assert [r.line_number for r in rows] == [4, 6]


def test_line_numbers_account_for_quoted_multiline_fields() -> None:
    rows = read_csv_rows(_csv(HEADER, '2026-01-01,"linha\num",1', "2026-01-02,b,2"))
    assert [r.line_number for r in rows] == [2, 4]
    assert rows[0].values["description"] == "linha\num"


def test_values_are_kept_as_raw_strings_without_type_inference() -> None:
    rows = read_csv_rows(_csv(HEADER, "2026-01-01,NA,0010.500"))
    assert rows[0].values["description"] == "NA"
    assert rows[0].values["amount"] == "0010.500"


def test_row_with_fewer_fields_gets_empty_strings() -> None:
    rows = read_csv_rows(_csv(HEADER, "2026-01-01,a"))
    assert rows[0].values["amount"] == ""


def test_row_with_some_content_is_not_treated_as_blank() -> None:
    rows = read_csv_rows(_csv(HEADER, ",,5"))
    assert rows == [RawRow(2, {"date": "", "description": "", "amount": "5"})]


def test_duplicated_normalized_column_keeps_first_occurrence() -> None:
    rows = read_csv_rows(_csv("date,description,amount,Date", "2026-01-01,a,1,1999-01-01"))
    assert rows[0].values["date"] == "2026-01-01"


def test_raw_row_is_frozen() -> None:
    row = RawRow(2, {"date": "x"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.line_number = 3  # type: ignore[misc]

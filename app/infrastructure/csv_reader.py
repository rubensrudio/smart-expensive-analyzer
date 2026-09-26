"""Leitura estrutural do CSV enviado (CT-12, DA-5).

Decodifica em UTF-8 estrito, lê com pandas sem inferência de tipos, valida o
cabeçalho (P-04) e devolve as linhas não vazias com o número físico da linha
(P-07, SEA-10). Nenhuma exceção ou mensagem daqui carrega conteúdo de célula
(AS-3).
"""

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from typing import Final

import pandas as pd

from app.core.errors import EmptyFileError, InvalidCsvError, MissingColumnsError

REQUIRED_COLUMNS: Final = ("date", "description", "amount")
OPTIONAL_COLUMNS: Final = ("merchant", "currency")
_KNOWN_COLUMNS: Final = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


@dataclass(frozen=True)
class RawRow:
    line_number: int
    values: Mapping[str, str]


def _decode(content: bytes) -> str:
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        # `from None`: o erro original traz trechos dos bytes do arquivo (AS-3).
        raise InvalidCsvError() from None
    if "\x00" in text:
        raise InvalidCsvError()
    return text


def _read_matrix(text: str) -> list[list[str]]:
    try:
        frame = pd.read_csv(
            BytesIO(text.encode("utf-8")),
            header=None,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            skip_blank_lines=False,
            encoding="utf-8",
        )
    except pd.errors.EmptyDataError:
        raise EmptyFileError() from None
    except (pd.errors.ParserError, ValueError, csv.Error, UnicodeError):
        # Inclui linha com mais campos que o cabeçalho (P-05).
        raise InvalidCsvError() from None
    return [[_cell(value) for value in row] for row in frame.itertuples(index=False, name=None)]


def _cell(value: object) -> str:
    # Campos faltantes podem vir como NaN mesmo com na_filter=False.
    return value if isinstance(value, str) else ""


def _column_positions(header: list[str]) -> dict[str, int]:
    positions: dict[str, int] = {}
    for index, name in enumerate(header):
        normalized = name.strip().lower()
        if normalized in _KNOWN_COLUMNS and normalized not in positions:
            positions[normalized] = index
    missing = [column for column in REQUIRED_COLUMNS if column not in positions]
    if missing:
        raise MissingColumnsError(missing)
    return positions


def read_csv_rows(content: bytes) -> list[RawRow]:
    """Devolve as linhas de dados não vazias; levanta os erros estruturais de CT-3."""
    text = _decode(content)
    if not text.strip():
        raise EmptyFileError()

    matrix = _read_matrix(text)
    positions = _column_positions(matrix[0])

    rows: list[RawRow] = []
    # Cabeçalho = linha física 1. Campos entre aspas com quebra de linha ocupam
    # mais de uma linha física, e o deslocamento é somado ao número seguinte.
    line_number = 1 + sum(cell.count("\n") for cell in matrix[0])
    for record in matrix[1:]:
        line_number += 1
        if any(cell.strip() for cell in record):
            values = {
                column: record[index] if index < len(record) else ""
                for column, index in positions.items()
            }
            rows.append(RawRow(line_number=line_number, values=values))
        line_number += sum(cell.count("\n") for cell in record)

    if not rows:
        raise EmptyFileError()
    return rows

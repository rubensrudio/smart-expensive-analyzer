"""Normalização de texto para armazenamento e casamento de regras (CT-10)."""

import unicodedata


def normalize_whitespace(value: str) -> str:
    """Remove espaços das pontas e colapsa qualquer sequência interna em um espaço."""
    return " ".join(value.split())


def fold_for_match(value: str) -> str:
    """Forma de comparação sem acento e sem caixa: NFKD, sem combinantes, casefold."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_marks.casefold()

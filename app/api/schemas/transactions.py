"""Schemas de `/transactions` (contrato 8.1; SEA-11, SEA-13, SEA-63, SEA-68).

Valores monetários saem por `TransactionOut` (CT-22). O filtro `merchant` é texto
livre vindo da query string e o tipo `MerchantFilter` barra com `VALIDATION_ERROR`
(422) tudo o que viraria 500 ou resposta enganosa mais adiante:
- caractere de controle (Unicode Cc) que não seja espaço, como NUL, ESC, DEL e C1.
  O PostgreSQL não aceita NUL em texto (`DataError`). Surrogate solto (Cs) também é
  recusado, porque não existe UTF-8 para ele e o driver quebraria ao codificar;
- valor vazio depois da mesma normalização do serviço (`normalize_whitespace`, P-09).
  Decisão (Jev): nenhum merchant gravado é vazio (SEA-37), então filtro vazio é
  entrada inválida, e não "sem filtro". Mesmo critério da keyword vazia (8.3);
- valor acima de `MERCHANT_FILTER_MAX_LENGTH`, medido depois da normalização. A
  coluna `transactions.merchant` é `TEXT` sem limite; o teto só limita o trabalho
  do banco com um filtro que nenhum estabelecimento real atinge.
Os Cc de espaço (`\\t`, `\\n`, `\\r`...) passam: a normalização os colapsa.
"""

import unicodedata
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel

from app.api.schemas.common import TransactionOut
from app.application.services.recategorization_service import RecategorizationResult
from app.domain.text import normalize_whitespace

MERCHANT_FILTER_MAX_LENGTH: Final = 1000
_REJECTED_CATEGORIES: Final = frozenset({"Cc", "Cs"})
MERCHANT_INVALID_CHAR_MESSAGE: Final = (
    "O estabelecimento não pode conter caracteres de controle nem surrogates."
)
MERCHANT_BLANK_MESSAGE: Final = "O estabelecimento não pode ser vazio nem só de espaços."
MERCHANT_TOO_LONG_MESSAGE: Final = (
    f"O estabelecimento pode ter no máximo {MERCHANT_FILTER_MAX_LENGTH} caracteres."
)


def _validate_merchant_filter(value: str) -> str:
    """Recusa Cc/Cs que não sejam espaço e valida o filtro já normalizado."""
    # `str.isspace()` casa com o que `str.split()` descarta na normalização.
    if any(unicodedata.category(ch) in _REJECTED_CATEGORIES and not ch.isspace() for ch in value):
        raise ValueError(MERCHANT_INVALID_CHAR_MESSAGE)
    normalized = normalize_whitespace(value)
    if not normalized:
        raise ValueError(MERCHANT_BLANK_MESSAGE)
    if len(normalized) > MERCHANT_FILTER_MAX_LENGTH:
        raise ValueError(MERCHANT_TOO_LONG_MESSAGE)
    return normalized


MerchantFilter = Annotated[str, AfterValidator(_validate_merchant_filter)]


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


class RecategorizeOut(BaseModel):
    evaluated: int
    changed: int

    @classmethod
    def from_result(cls, result: RecategorizationResult) -> "RecategorizeOut":
        return cls(evaluated=result.evaluated, changed=result.changed)

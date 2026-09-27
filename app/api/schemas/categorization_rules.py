"""Schemas de `/categorization-rules` (contrato 8.1; SEA-18, SEA-48, SEA-50, P-12).

O schema barra com `VALIDATION_ERROR` (422) tudo o que viraria 500 mais adiante:
- `keyword` vazia ou só espaços depois de tirar as pontas (SEA-50). Sem isso, o
  `CategorizationRuleService` levantaria `ValueError`;
- `keyword` acima do limite da coluna, medido depois de tirar as pontas;
- `keyword` com caractere de controle (Unicode Cc) que não seja espaço, como NUL.
  O PostgreSQL não aceita NUL em texto (`DataError`). Surrogate solto (Cs) também é
  recusado: o pydantic já barra no parse do `str`, e o validador é defesa extra,
  porque não existe UTF-8 para ele e o driver quebraria ao codificar;
- `priority` não inteira (`StrictInt`: recusa `1.5`, `1.0`, `"1"` e `true`) ou fora
  do `INTEGER` da coluna;
- `category_id` fora do `BIGINT` da coluna. Dentro da faixa, id sem Category chega
  ao serviço, que responde `RULE_CATEGORY_NOT_FOUND` (422).
Os Cc de espaço (`\\t`, `\\n`, `\\r`...) passam: a normalização do serviço os colapsa.
"""

import unicodedata
from datetime import datetime
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel, Field, StrictInt, StringConstraints

from app.domain.entities import CategorizationRule

KEYWORD_MAX_LENGTH: Final = 200  # `categorization_rules.keyword VARCHAR(200)`, migration 0001
INT32_MIN: Final = -(2**31)  # `categorization_rules.priority INTEGER`
INT32_MAX: Final = 2**31 - 1
INT64_MIN: Final = -(2**63)  # `id` e `category_id` BIGINT
INT64_MAX: Final = 2**63 - 1
_REJECTED_CATEGORIES: Final = frozenset({"Cc", "Cs"})
INVALID_CHAR_MESSAGE: Final = (
    "A palavra-chave não pode conter caracteres de controle nem surrogates."
)


def _reject_invalid_chars(value: str) -> str:
    # `str.isspace()` casa com o que `str.split()` descarta na normalização.
    if any(unicodedata.category(ch) in _REJECTED_CATEGORIES and not ch.isspace() for ch in value):
        raise ValueError(INVALID_CHAR_MESSAGE)
    return value


Keyword = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=KEYWORD_MAX_LENGTH),
    AfterValidator(_reject_invalid_chars),
]
Priority = Annotated[StrictInt, Field(ge=INT32_MIN, le=INT32_MAX)]
BigIntId = Annotated[int, Field(ge=INT64_MIN, le=INT64_MAX)]


class RuleIn(BaseModel):
    keyword: Keyword
    category_id: BigIntId
    priority: Priority


class RuleOut(BaseModel):
    id: int
    keyword: str
    category_id: int
    priority: int
    created_at: datetime

    @classmethod
    def from_entity(cls, rule: CategorizationRule) -> "RuleOut":
        return cls(
            id=rule.id,
            keyword=rule.keyword,
            category_id=rule.category_id,
            priority=rule.priority,
            created_at=rule.created_at,
        )

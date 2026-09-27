"""Schemas de `/categories` (contrato 8.1; SEA-15, SEA-16, SEA-53).

`name` é opcional no schema: ausente, vazio ou só espaços chegam ao serviço, que
responde `CATEGORY_NAME_REQUIRED` (422). O schema só barra (`VALIDATION_ERROR`):
- tipo inválido;
- nome acima do limite da coluna, medido depois de tirar os espaços das pontas;
- caractere de controle (Unicode Cc) que não seja espaço, como NUL, BEL, DEL e C1.
Sem isso, o banco recusaria com `DataError` (500): o PostgreSQL não aceita NUL em
texto. Os Cc de espaço (`\\t`, `\\n`, `\\r`...) passam, porque a normalização do
serviço os colapsa em um espaço.
"""

import unicodedata
from typing import Annotated, Final

from pydantic import AfterValidator, BaseModel, StringConstraints

from app.api.schemas.common import CategoryRef
from app.domain.entities import Category

CATEGORY_NAME_MAX_LENGTH: Final = 100  # `categories.name VARCHAR(100)`, migration 0001
_CONTROL_CATEGORY: Final = "Cc"
CONTROL_CHAR_MESSAGE: Final = "O nome não pode conter caracteres de controle."


def _reject_control_chars(value: str) -> str:
    # `str.isspace()` casa com o que `str.split()` descarta na normalização.
    if any(unicodedata.category(ch) == _CONTROL_CATEGORY and not ch.isspace() for ch in value):
        raise ValueError(CONTROL_CHAR_MESSAGE)
    return value


CategoryName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=CATEGORY_NAME_MAX_LENGTH),
    AfterValidator(_reject_control_chars),
]


class CategoryIn(BaseModel):
    name: CategoryName | None = None


def category_ref(category: Category) -> CategoryRef:
    return CategoryRef(id=category.id, name=category.name)

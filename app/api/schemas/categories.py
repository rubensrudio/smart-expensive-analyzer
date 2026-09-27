"""Schemas de `/categories` (contrato 8.1; SEA-15, SEA-16, SEA-53).

`name` é opcional no schema: ausente, vazio ou só espaços chegam ao serviço, que
responde `CATEGORY_NAME_REQUIRED` (422). O schema só barra tipo inválido e nome
acima do limite da coluna (`VALIDATION_ERROR`), medido depois de tirar os espaços
das pontas. Sem isso, o banco recusaria com `DataError` (500).
"""

from typing import Annotated, Final

from pydantic import BaseModel, StringConstraints

from app.api.schemas.common import CategoryRef
from app.domain.entities import Category

CATEGORY_NAME_MAX_LENGTH: Final = 100  # `categories.name VARCHAR(100)`, migration 0001

CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=CATEGORY_NAME_MAX_LENGTH)
]


class CategoryIn(BaseModel):
    name: CategoryName | None = None


def category_ref(category: Category) -> CategoryRef:
    return CategoryRef(id=category.id, name=category.name)

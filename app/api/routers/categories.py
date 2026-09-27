"""Router de Category: `POST /categories` e `GET /categories` (TASK-026; contrato 8.1).

AS-6: endpoints abertos, sem autenticação (LAC-01, risco aceito; mitigação DA-12).
Só criação e listagem (LAC-09): não há PUT/PATCH/DELETE.
O router só cuida do HTTP; normalização, obrigatoriedade e unicidade do nome ficam
no `CategoryService` (CT-18). Erros sobem para `app.api.errors`, sem try/except nem
log aqui (AS-3).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_uow
from app.api.errors import ErrorResponse
from app.api.schemas.categories import CategoryIn, category_ref
from app.api.schemas.common import CategoryRef
from app.application.services.category_service import CategoryService
from app.domain.ports import UnitOfWork

_SERVICE_UNAVAILABLE: dict[str, Any] = {
    "model": ErrorResponse,
    "description": "SERVICE_UNAVAILABLE",
}

_CREATE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "CATEGORY_ALREADY_EXISTS"},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "CATEGORY_NAME_REQUIRED | VALIDATION_ERROR",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: _SERVICE_UNAVAILABLE,
}

_LIST_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: _SERVICE_UNAVAILABLE,
}

router = APIRouter(tags=["categories"])


def get_category_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> CategoryService:
    """Provider do serviço (DA-3)."""
    return CategoryService(uow)


@router.post(
    "/categories",
    status_code=status.HTTP_201_CREATED,
    response_model=CategoryRef,
    responses=_CREATE_ERROR_RESPONSES,
    summary="Cria uma categoria",
)
def create_category(
    payload: CategoryIn,
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> CategoryRef:
    return category_ref(service.create(payload.name))


@router.get(
    "/categories",
    response_model=list[CategoryRef],
    responses=_LIST_ERROR_RESPONSES,
    summary="Lista as categorias, incluindo a padrão",
)
def list_categories(
    service: Annotated[CategoryService, Depends(get_category_service)],
) -> list[CategoryRef]:
    return [category_ref(category) for category in service.list()]

"""Router de Transaction: consulta e recategorização em `/transactions` (TASK-025; 8.1).

AS-6: endpoints abertos, sem autenticação (LAC-01, risco aceito; mitigação DA-12).
O router só cuida do HTTP. Normalização do merchant e existência da transação ficam
no `TransactionService` (CT-19); a recategorização, com commit, no
`RecategorizationService` (CT-20). Não há alteração manual de categoria (fora de
escopo). Erros sobem para `app.api.errors`, sem try/except nem log aqui (AS-3).

Todo inteiro que chega ao banco é limitado à faixa do BIGINT: fora dela o
PostgreSQL recusaria (500); aqui vira 422 `VALIDATION_ERROR`.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.exceptions import RequestValidationError

from app.api.deps import get_settings, get_uow
from app.api.errors import ErrorResponse
from app.api.params import pagination_params, period_params
from app.api.schemas.categorization_rules import INT64_MAX, INT64_MIN
from app.api.schemas.common import TransactionOut
from app.api.schemas.transactions import MerchantFilter, RecategorizeOut, TransactionPage
from app.application.services.recategorization_service import RecategorizationService
from app.application.services.transaction_service import TransactionService
from app.core.config import Settings
from app.domain.entities import Page, Period, TransactionFilters
from app.domain.ports import UnitOfWork

_SERVICE_UNAVAILABLE: dict[str, Any] = {
    "model": ErrorResponse,
    "description": "SERVICE_UNAVAILABLE",
}

_LIST_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "INVALID_PAGINATION | INVALID_PERIOD | VALIDATION_ERROR",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: _SERVICE_UNAVAILABLE,
}
_ITEM_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "TRANSACTION_NOT_FOUND"},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "VALIDATION_ERROR",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: _SERVICE_UNAVAILABLE,
}
_RECATEGORIZE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: _SERVICE_UNAVAILABLE,
}

OFFSET_TOO_LARGE_MESSAGE = f"offset deve ser menor ou igual a {INT64_MAX}."

TransactionId = Annotated[int, Path(ge=INT64_MIN, le=INT64_MAX, description="Id da transação.")]
CategoryIdFilter = Annotated[
    int | None,
    Query(ge=INT64_MIN, le=INT64_MAX, description="Filtra pela categoria (igualdade por id)."),
]
ImportIdFilter = Annotated[
    int | None,
    Query(ge=INT64_MIN, le=INT64_MAX, description="Filtra pela importação de origem."),
]
MerchantQuery = Annotated[
    MerchantFilter | None,
    Query(description="Estabelecimento: igualdade sem caixa, após normalizar espaços (P-09)."),
]

router = APIRouter(prefix="/transactions", tags=["transactions"])


def get_transaction_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> TransactionService:
    """Provider do serviço de consulta (DA-3)."""
    return TransactionService(uow)


def get_recategorization_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RecategorizationService:
    """Provider do serviço de recategorização (DA-3)."""
    return RecategorizationService(uow, settings)


def transaction_page_params(page: Annotated[Page, Depends(pagination_params)]) -> Page:
    """`pagination_params` (CT-22) mais o teto do `OFFSET`, que é BIGINT no PostgreSQL."""
    if page.offset > INT64_MAX:
        raise RequestValidationError(
            [
                {
                    "type": "less_than_equal",
                    "loc": ("query", "offset"),
                    "msg": OFFSET_TOO_LARGE_MESSAGE,
                }
            ]
        )
    return page


@router.get(
    "",
    response_model=TransactionPage,
    responses=_LIST_ERROR_RESPONSES,
    summary="Lista transações com filtros e paginação",
)
def list_transactions(
    period: Annotated[Period, Depends(period_params)],
    page: Annotated[Page, Depends(transaction_page_params)],
    service: Annotated[TransactionService, Depends(get_transaction_service)],
    category_id: CategoryIdFilter = None,
    merchant: MerchantQuery = None,
    import_id: ImportIdFilter = None,
) -> TransactionPage:
    filters = TransactionFilters(
        period=period, category_id=category_id, merchant=merchant, import_id=import_id
    )
    result = service.list(filters, page)
    return TransactionPage(
        items=[TransactionOut.from_entity(t) for t in result.items],
        total=result.total,
        limit=page.limit,
        offset=page.offset,
    )


# Declarada antes de `/{transaction_id}` (TASK-025).
@router.post(
    "/recategorize",
    response_model=RecategorizeOut,
    responses=_RECATEGORIZE_ERROR_RESPONSES,
    summary="Reaplica as regras atuais a todas as transações",
)
def recategorize_transactions(
    service: Annotated[RecategorizationService, Depends(get_recategorization_service)],
) -> RecategorizeOut:
    return RecategorizeOut.from_result(service.recategorize())


@router.get(
    "/{transaction_id}",
    response_model=TransactionOut,
    responses=_ITEM_ERROR_RESPONSES,
    summary="Consulta uma transação",
)
def get_transaction(
    transaction_id: TransactionId,
    service: Annotated[TransactionService, Depends(get_transaction_service)],
) -> TransactionOut:
    return TransactionOut.from_entity(service.get(transaction_id))

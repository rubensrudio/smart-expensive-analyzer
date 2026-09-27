"""Router de analytics: `/analytics/summary`, `/categories` e `/monthly` (TASK-028; 8.1).

AS-6: endpoints abertos, sem autenticação (LAC-01, risco aceito; mitigação DA-12).
Somente leitura. O router só cuida do HTTP: todo cálculo fica no `AnalyticsService`
(CT-21) e a conversão para JSON nos schemas. Período opcional (SEA-57), validado por
`period_params` (CT-22). Erros sobem para `app.api.errors`, sem try/except nem log
aqui (AS-3).

Filtros do resumo iguais aos de `/transactions`: `category_id` limitado à faixa do
BIGINT (fora dela o PostgreSQL recusaria com 500) e `merchant` pelo `MerchantFilter`
(controle, vazio e tamanho → 422 `VALIDATION_ERROR`).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_uow
from app.api.errors import ErrorResponse
from app.api.params import period_params
from app.api.schemas.analytics import CategoriesOut, MonthlyOut, SummaryOut
from app.api.schemas.categorization_rules import INT64_MAX, INT64_MIN
from app.api.schemas.transactions import MerchantFilter
from app.application.services.analytics_service import AnalyticsService
from app.domain.entities import ExpenseFilters, Period
from app.domain.ports import UnitOfWork

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "INVALID_PERIOD | VALIDATION_ERROR",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "SERVICE_UNAVAILABLE",
    },
}

CategoryIdFilter = Annotated[
    int | None,
    Query(ge=INT64_MIN, le=INT64_MAX, description="Filtra pela categoria (igualdade por id)."),
]
MerchantQuery = Annotated[
    MerchantFilter | None,
    Query(description="Estabelecimento: igualdade sem caixa, após normalizar espaços (P-09)."),
]

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_analytics_service(uow: Annotated[UnitOfWork, Depends(get_uow)]) -> AnalyticsService:
    """Provider do serviço (DA-3)."""
    return AnalyticsService(uow)


@router.get(
    "/summary",
    response_model=SummaryOut,
    responses=_ERROR_RESPONSES,
    summary="Estatísticas, estabelecimentos e histograma das despesas, por moeda",
)
def get_summary(
    period: Annotated[Period, Depends(period_params)],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    category_id: CategoryIdFilter = None,
    merchant: MerchantQuery = None,
) -> SummaryOut:
    filters = ExpenseFilters(period=period, category_id=category_id, merchant=merchant)
    return SummaryOut.from_domain(service.summary(filters))


@router.get(
    "/categories",
    response_model=CategoriesOut,
    responses=_ERROR_RESPONSES,
    summary="Estatística e percentual por categoria, por moeda",
)
def get_categories(
    period: Annotated[Period, Depends(period_params)],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> CategoriesOut:
    return CategoriesOut.from_domain(service.categories(period))


@router.get(
    "/monthly",
    response_model=MonthlyOut,
    responses=_ERROR_RESPONSES,
    summary="Série mensal de despesas, por moeda",
)
def get_monthly(
    period: Annotated[Period, Depends(period_params)],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> MonthlyOut:
    return MonthlyOut.from_domain(service.monthly(period))

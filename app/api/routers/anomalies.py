"""Router de Anomaly: `GET /anomalies` (TASK-029; contrato 8.1).

AS-6: endpoint aberto, sem autenticação (LAC-01, risco aceito; mitigação DA-12).
Somente leitura: lista o conjunto persistido e não recalcula (LAC-13); o recálculo
roda no fim do import e da recategorização. Período opcional (SEA-31, SEA-57),
validado por `period_params` (CT-22). Erros sobem para `app.api.errors`, sem
try/except nem log aqui (AS-3).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_settings, get_uow
from app.api.errors import ErrorResponse
from app.api.params import period_params
from app.api.schemas.anomalies import AnomalyListOut, AnomalyOut
from app.application.services.anomaly_service import AnomalyService
from app.core.config import Settings
from app.domain.entities import Period
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

router = APIRouter(tags=["anomalies"])


def get_anomaly_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AnomalyService:
    """Provider do serviço (DA-3)."""
    return AnomalyService(uow, settings.anomaly_iqr_k, settings.anomaly_min_sample)


@router.get(
    "/anomalies",
    response_model=AnomalyListOut,
    responses=_ERROR_RESPONSES,
    summary="Lista as possíveis anomalias, com filtro opcional de período",
)
def list_anomalies(
    period: Annotated[Period, Depends(period_params)],
    service: Annotated[AnomalyService, Depends(get_anomaly_service)],
) -> AnomalyListOut:
    return AnomalyListOut(items=[AnomalyOut.from_entity(a) for a in service.list(period)])

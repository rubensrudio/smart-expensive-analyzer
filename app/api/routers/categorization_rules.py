"""Router de CategorizationRule: CRUD em `/categorization-rules` (TASK-027; contrato 8.1).

AS-6: endpoints abertos, sem autenticação (LAC-01, risco aceito; mitigação DA-12).
O router só cuida do HTTP; normalização da keyword, existência da regra e da
Category ficam no `CategorizationRuleService` (CT-18). Nenhuma rota recategoriza
transações (SEA-64). Erros sobem para `app.api.errors`, sem try/except nem log
aqui (AS-3).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response, status

from app.api.deps import get_uow
from app.api.errors import ErrorResponse
from app.api.schemas.categorization_rules import INT64_MAX, INT64_MIN, RuleIn, RuleOut
from app.application.services.categorization_rule_service import CategorizationRuleService
from app.domain.ports import UnitOfWork

_SERVICE_UNAVAILABLE: dict[str, Any] = {
    "model": ErrorResponse,
    "description": "SERVICE_UNAVAILABLE",
}
_RULE_NOT_FOUND: dict[str, Any] = {"model": ErrorResponse, "description": "RULE_NOT_FOUND"}
_PATH_VALIDATION: dict[str, Any] = {"model": ErrorResponse, "description": "VALIDATION_ERROR"}

_CREATE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "RULE_CATEGORY_NOT_FOUND | VALIDATION_ERROR",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: _SERVICE_UNAVAILABLE,
}
_LIST_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: _SERVICE_UNAVAILABLE,
}
_ITEM_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: _RULE_NOT_FOUND,
    status.HTTP_422_UNPROCESSABLE_CONTENT: _PATH_VALIDATION,
    status.HTTP_503_SERVICE_UNAVAILABLE: _SERVICE_UNAVAILABLE,
}
_UPDATE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_ITEM_ERROR_RESPONSES,
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "RULE_CATEGORY_NOT_FOUND | VALIDATION_ERROR",
    },
}

# Faixa do BIGINT da coluna `id`: fora dela o banco quebraria (500); vira 422.
RuleId = Annotated[int, Path(ge=INT64_MIN, le=INT64_MAX, description="Id da regra.")]

router = APIRouter(prefix="/categorization-rules", tags=["categorization-rules"])


def get_categorization_rule_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> CategorizationRuleService:
    """Provider do serviço (DA-3)."""
    return CategorizationRuleService(uow)


ServiceDep = Annotated[CategorizationRuleService, Depends(get_categorization_rule_service)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RuleOut,
    responses=_CREATE_ERROR_RESPONSES,
    summary="Cria uma regra de categorização",
)
def create_rule(payload: RuleIn, service: ServiceDep) -> RuleOut:
    rule = service.create(payload.keyword, payload.category_id, payload.priority)
    return RuleOut.from_entity(rule)


@router.get(
    "",
    response_model=list[RuleOut],
    responses=_LIST_ERROR_RESPONSES,
    summary="Lista as regras por prioridade, criação e id",
)
def list_rules(service: ServiceDep) -> list[RuleOut]:
    return [RuleOut.from_entity(rule) for rule in service.list()]


@router.get(
    "/{rule_id}",
    response_model=RuleOut,
    responses=_ITEM_ERROR_RESPONSES,
    summary="Consulta uma regra",
)
def get_rule(rule_id: RuleId, service: ServiceDep) -> RuleOut:
    return RuleOut.from_entity(service.get(rule_id))


@router.put(
    "/{rule_id}",
    response_model=RuleOut,
    responses=_UPDATE_ERROR_RESPONSES,
    summary="Substitui uma regra (corpo completo)",
)
def update_rule(rule_id: RuleId, payload: RuleIn, service: ServiceDep) -> RuleOut:
    rule = service.update(rule_id, payload.keyword, payload.category_id, payload.priority)
    return RuleOut.from_entity(rule)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_ITEM_ERROR_RESPONSES,
    summary="Exclui uma regra",
)
def delete_rule(rule_id: RuleId, service: ServiceDep) -> Response:
    service.delete(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

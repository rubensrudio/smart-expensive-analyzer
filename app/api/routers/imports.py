"""Router de importação de CSV: `POST /imports` (TASK-024; contrato 8.1).

AS-6: endpoint aberto, sem autenticação (LAC-01, risco aceito; mitigação DA-12).
O router só cuida do HTTP: lê no máximo `MAX_UPLOAD_MB` + 1 bytes do upload e
delega tudo ao `ImportService` (limite, hash, duplicidade, DA-16 e logs).
Erros sobem para `app.api.errors`; o router não loga exceções (AS-3: a causa
encadeada de `ServiceUnavailableError` carrega parâmetros SQL).
"""

from collections.abc import Callable
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, File, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_settings, get_uow_factory
from app.api.errors import ErrorResponse
from app.api.schemas.imports import ImportOut
from app.application.services.import_service import ImportService
from app.core.config import Settings
from app.domain.ports import UnitOfWork

DEFAULT_FILENAME: Final = "arquivo.csv"
_BYTES_PER_MB: Final = 1024 * 1024

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {"model": ErrorResponse, "description": "DUPLICATE_FILE"},
    status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse, "description": "FILE_TOO_LARGE"},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "EMPTY_FILE | INVALID_CSV | MISSING_COLUMNS | VALIDATION_ERROR",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "SERVICE_UNAVAILABLE",
    },
}

router = APIRouter(tags=["imports"])


def get_import_service(
    uow_factory: Annotated[Callable[[], UnitOfWork], Depends(get_uow_factory)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImportService:
    """Provider do serviço (DA-3)."""
    return ImportService(uow_factory, settings)


@router.post(
    "/imports",
    status_code=status.HTTP_201_CREATED,
    response_model=ImportOut,
    responses=_ERROR_RESPONSES,
    summary="Importa um extrato CSV",
)
async def create_import(
    file: Annotated[UploadFile, File(description="Extrato CSV (UTF-8).")],
    service: Annotated[ImportService, Depends(get_import_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImportOut:
    # Lê no máximo limite + 1 byte: basta para o serviço detectar o excesso (413)
    # sem carregar um upload gigante inteiro na memória (AS-6, SEA-104).
    max_bytes = settings.max_upload_mb * _BYTES_PER_MB
    content = await file.read(max_bytes + 1)
    filename = file.filename or DEFAULT_FILENAME
    # O serviço é síncrono (banco + pandas): roda fora do event loop.
    record = await run_in_threadpool(service.import_csv, filename, content)
    return ImportOut.from_record(record)

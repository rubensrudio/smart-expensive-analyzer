"""Tradução centralizada de exceções para `ErrorResponse` (DA-11, CT-3, SEA-05/06/97/100).

Nenhum corpo de erro expõe stack trace, SQL ou mensagem interna de exceção.
"""

import logging
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, ServiceUnavailableError

logger = logging.getLogger(__name__)

VALIDATION_ERROR_MESSAGE = "Dados de entrada inválidos."
INTERNAL_ERROR_MESSAGE = "Erro interno. Identificador: {id}."

_HTTP_STATUS_ERRORS: dict[int, tuple[str, str]] = {
    404: ("NOT_FOUND", "Recurso não encontrado."),
    405: ("METHOD_NOT_ALLOWED", "Método não permitido."),
}


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[Any] | None = None
    error_id: str | None = None


def _error_response(
    status_code: int,
    body: ErrorResponse,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # pragma: no cover
        raise exc
    body = ErrorResponse(code=exc.code, message=exc.message, details=exc.details)
    return _error_response(exc.http_status, body)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        raise exc
    details = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": str(error.get("msg", "")),
        }
        for error in exc.errors()
    ]
    body = ErrorResponse(code="VALIDATION_ERROR", message=VALIDATION_ERROR_MESSAGE, details=details)
    return _error_response(422, body)


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        raise exc
    known = _HTTP_STATUS_ERRORS.get(exc.status_code)
    if known is not None:
        code, message = known
    else:
        code, message = f"HTTP_{exc.status_code}", str(exc.detail)
    body = ErrorResponse(code=code, message=message)
    return _error_response(exc.status_code, body, headers=exc.headers)


async def _handle_database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    # Sem traceback nem str(exc): a mensagem do SQLAlchemy carrega o SQL (DA-15).
    logger.error("database_unavailable path=%s", request.url.path)
    unavailable = ServiceUnavailableError()
    body = ErrorResponse(code=unavailable.code, message=unavailable.message)
    return _error_response(unavailable.http_status, body)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    error_id = uuid4().hex
    logger.exception(
        "unexpected_error error_id=%s path=%s method=%s",
        error_id,
        request.url.path,
        request.method,
        exc_info=exc,
    )
    body = ErrorResponse(
        code="INTERNAL_ERROR",
        message=INTERNAL_ERROR_MESSAGE.format(id=error_id),
        error_id=error_id,
    )
    return _error_response(500, body)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra os handlers que garantem o corpo `ErrorResponse` em todo erro."""
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(OperationalError, _handle_database_unavailable)
    app.add_exception_handler(InterfaceError, _handle_database_unavailable)
    app.add_exception_handler(Exception, _handle_unexpected)

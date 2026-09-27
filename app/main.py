"""Factory da aplicação FastAPI (CT-26, DA-4).

Execução: `uvicorn app.main:create_app --factory`. Nada é criado no import do
módulo; a validação do ambiente (SEA-03) roda dentro de `create_app`.
Cada task de router registra o seu `app.include_router(...)` aqui.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routers.categories import router as categories_router
from app.api.routers.categorization_rules import router as categorization_rules_router
from app.api.routers.imports import router as imports_router
from app.core.config import Settings, load_settings_or_exit
from app.core.logging import configure_logging
from app.infrastructure.db.session import create_engine_from_url, create_session_factory

APP_TITLE: Final[str] = "Smart Expense Analyzer"
APP_VERSION: Final[str] = "0.1.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Monta a app. Sem `settings`, carrega do ambiente e sai com código 1 se inválido."""
    resolved = settings if settings is not None else load_settings_or_exit()
    configure_logging(resolved.log_level)

    engine = create_engine_from_url(resolved.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            _app.state.engine.dispose()

    app = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=lifespan)
    app.state.settings = resolved
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    register_exception_handlers(app)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(imports_router)
    app.include_router(categories_router)
    app.include_router(categorization_rules_router)

    return app

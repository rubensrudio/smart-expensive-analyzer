"""Configuração por variáveis de ambiente (CT-1; SEA-03, SEA-108, SEA-58, SEA-59).

Nenhum valor de variável é logado: em erro, o log cita só o nome e o motivo.
"""

import logging

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.logging import LOG_LEVELS
from app.domain.currency import normalize_currency_code

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    default_currency: str = "BRL"
    max_upload_mb: int = Field(default=10, gt=0)
    anomaly_iqr_k: float = Field(default=1.5, gt=0)
    anomaly_min_sample: int = Field(default=8, ge=2)
    log_level: str = "INFO"

    @field_validator("default_currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        code = normalize_currency_code(value)
        if code is None:
            raise ValueError("não é um código ISO 4217 válido")
        return code

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in LOG_LEVELS:
            raise ValueError(f"deve ser um de {sorted(LOG_LEVELS)}")
        return level


def load_settings_or_exit() -> Settings:
    """Carrega Settings; em erro loga CRITICAL por variável (sem valor) e sai com código 1."""
    try:
        return Settings()
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False):
            var = str(error["loc"][0]).upper() if error["loc"] else "CONFIG"
            logger.critical("Configuração inválida: %s %s", var, error["msg"])
        raise SystemExit(1) from None

"""Configuração de logging da aplicação (plan, seção 14; CT-1)."""

import logging
import sys
from typing import Final

LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s %(message)s"
LOG_LEVELS: Final[frozenset[str]] = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})
_HANDLER_NAME: Final[str] = "smart_expense_analyzer"


def configure_logging(level: str) -> None:
    """Aplica formato e nível ao logger raiz. Idempotente: troca só o próprio handler."""
    level_name = level.strip().upper()
    if level_name not in LOG_LEVELS:
        raise ValueError(f"nível de log desconhecido; use um de {sorted(LOG_LEVELS)}")

    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == _HANDLER_NAME:
            root.removeHandler(handler)
            handler.close()

    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
    root.setLevel(level_name)

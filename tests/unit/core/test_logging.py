import logging
from collections.abc import Iterator

import pytest

from app.core.logging import LOG_FORMAT, configure_logging


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)


def _own_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if h.get_name() == "smart_expense_analyzer"]


def test_format_matches_plan() -> None:
    assert LOG_FORMAT == "%(asctime)s %(levelname)s %(name)s %(message)s"


def test_applies_level_and_format() -> None:
    configure_logging("DEBUG")

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    handlers = _own_handlers()
    assert len(handlers) == 1
    assert handlers[0].formatter is not None
    assert handlers[0].formatter._fmt == LOG_FORMAT


def test_level_is_case_insensitive() -> None:
    configure_logging("warning")

    assert logging.getLogger().level == logging.WARNING


def test_is_idempotent() -> None:
    configure_logging("INFO")
    configure_logging("ERROR")

    assert len(_own_handlers()) == 1
    assert logging.getLogger().level == logging.ERROR


def test_rejects_unknown_level() -> None:
    with pytest.raises(ValueError):
        configure_logging("VERBOSE")


def test_formatted_record_contains_level_name_and_message() -> None:
    configure_logging("INFO")
    handler = _own_handlers()[0]
    record = logging.LogRecord(
        "app.test", logging.INFO, __file__, 1, "import_started import_id=%s", (7,), None
    )

    line = handler.format(record)

    assert line.endswith("INFO app.test import_started import_id=7")

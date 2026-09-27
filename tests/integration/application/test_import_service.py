"""Testes de integração do `ImportService` contra PostgreSQL real (CT-17, TASK-019).

Requisitos: SEA-07, SEA-08, SEA-10, SEA-14, SEA-17, SEA-41, SEA-42, SEA-43, SEA-44,
SEA-45, SEA-60, SEA-97, SEA-98, SEA-102, SEA-103, SEA-104, SEA-106, SEA-107; AS-3.
"""

import hashlib
import logging
import threading
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from app.application.services.anomaly_service import AnomalyService
from app.application.services.import_service import ImportService
from app.core.config import Settings
from app.core.errors import (
    AppError,
    DuplicateFileError,
    EmptyFileError,
    FileTooLargeError,
    InvalidCsvError,
    MissingColumnsError,
    ServiceUnavailableError,
)
from app.domain.entities import ImportRecord, ImportStatus
from app.domain.ports import UnitOfWork
from app.infrastructure.db.repositories.imports import SqlAlchemyImportRepository
from app.infrastructure.db.repositories.transactions import SqlAlchemyTransactionRepository

UoWFactory = Callable[[], UnitOfWork]

HEADER = "date,description,amount,merchant,currency"
SERVICE_LOGGER = "app.application.services.import_service"


def _csv(*lines: str, header: str = HEADER) -> bytes:
    return ("\n".join((header, *lines)) + "\n").encode("utf-8")


def _service(uow_factory: UoWFactory, settings: Settings) -> ImportService:
    return ImportService(uow_factory, settings)


def _scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _count(engine: Engine, table: str) -> int:
    # `table` vem só de literais dos próprios testes.
    return int(_scalar(engine, f"SELECT count(*) FROM {table}"))


def _imports(engine: Engine) -> list[tuple[str, str | None, str]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT status, failure_reason, filename FROM imports ORDER BY id")
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


def _ten_valid_lines() -> list[str]:
    return [f"2026-01-{day:02d},COMPRA {day},-{day}.50,,BRL" for day in range(1, 11)]


def _boom(*_args: object, **_kwargs: object) -> Any:
    raise OperationalError("INSERT ...", {}, Exception("connection lost"))


# --- fluxo feliz, rejeições e contagens -------------------------------------------------


def test_valid_csv_with_blank_line_completes_sea07_sea08_sea10(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-07, SEA-08, SEA-10, SEA-45: 10 válidas + 1 vazia → concluída com 10 vinculadas."""
    lines = _ten_valid_lines()
    lines.insert(5, "")
    record = _service(uow_factory, settings).import_csv("extrato.csv", _csv(*lines))

    assert isinstance(record, ImportRecord)
    assert record.status is ImportStatus.COMPLETED
    assert (record.rows_read, record.imported_count) == (10, 10)
    assert (record.rejected_count, record.duplicate_count) == (0, 0)
    assert record.rejections == ()
    assert record.filename == "extrato.csv"
    linked = _scalar(engine, "SELECT count(*) FROM transactions WHERE import_id = :i", i=record.id)
    assert linked == 10
    assert _imports(engine) == [("concluida", None, "extrato.csv")]


def test_rows_are_normalized_and_merchant_falls_back_sea09_sea37(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-09, SEA-37: descrição normalizada, merchant = descrição, moeda padrão, tipo."""
    content = _csv(
        "2026-02-03,  Mercado   Central ,-12.345,,", "2026-02-04,Salario,1000,Empresa,usd"
    )
    _service(uow_factory, settings).import_csv("a.csv", content)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT description, merchant, amount::text, currency, type "
                "FROM transactions ORDER BY description"
            )
        ).all()
    assert [tuple(r) for r in rows] == [
        ("Mercado Central", "Mercado Central", "-12.35", "BRL", "despesa"),
        ("Salario", "Empresa", "1000.00", "USD", "receita"),
    ]


def test_invalid_date_row_completes_with_rejections_sea41_sea42(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-41, SEA-42: 2 válidas + 1 data inválida → rejeição com a linha física certa."""
    content = _csv("2026-01-01,A,-1.00,,", "2026-13-40,B,-2.00,,", "2026-01-03,C,-3.00,,")
    record = _service(uow_factory, settings).import_csv("r.csv", content)

    assert record.status is ImportStatus.COMPLETED_WITH_REJECTIONS
    assert (record.rows_read, record.imported_count, record.rejected_count) == (3, 2, 1)
    assert [(r.line_number, r.reason) for r in record.rejections] == [(3, "data inválida")]
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT line_number, reason FROM import_rejections")).all()
    assert [tuple(r) for r in stored] == [(3, "data inválida")]
    assert _count(engine, "transactions") == 2


def test_all_rows_invalid_sea102(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-102: nenhuma válida → concluída com rejeições, 0 importadas, todas listadas."""
    content = _csv("x,A,-1.00,,", "2026-01-02,,-2.00,,", "2026-01-03,C,abc,,")
    record = _service(uow_factory, settings).import_csv("bad.csv", content)

    assert record.status is ImportStatus.COMPLETED_WITH_REJECTIONS
    assert (record.rows_read, record.imported_count, record.rejected_count) == (3, 0, 3)
    assert [r.line_number for r in record.rejections] == [2, 3, 4]
    assert _count(engine, "transactions") == 0


def test_persisted_and_in_file_duplicates_count_sea44_sea103(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-44, SEA-103: 1 já persistida + 1 repetida no arquivo → duplicate_count=2."""
    service = _service(uow_factory, settings)
    service.import_csv("first.csv", _csv("2026-01-01,ALUGUEL,-900.00,,"))

    second = service.import_csv(
        "second.csv",
        _csv(
            "2026-01-01,ALUGUEL,-900.00,,",  # já persistida
            "2026-01-05,FARMACIA,-30.00,Drogasil,",  # primeira ocorrência vence
            "2026-01-05,FARMACIA,-30.00,Outra,",  # mesma chave no arquivo
        ),
    )

    assert second.status is ImportStatus.COMPLETED
    assert (second.rows_read, second.imported_count, second.duplicate_count) == (3, 1, 2)
    merchant = _scalar(engine, "SELECT merchant FROM transactions WHERE description = 'FARMACIA'")
    assert merchant == "Drogasil"
    assert _count(engine, "transactions") == 2


def test_dedup_key_uses_normalized_description_p08(
    uow_factory: UoWFactory, settings: Settings
) -> None:
    """P-08: espaços normalizados antes da chave; caixa diferente não é duplicata."""
    service = _service(uow_factory, settings)
    service.import_csv("a.csv", _csv("2026-01-01,UBER TRIP,-20.00,,"))

    record = service.import_csv(
        "b.csv", _csv("2026-01-01,  UBER    TRIP ,-20.00,,", "2026-01-01,uber trip,-20.00,,")
    )

    assert (record.imported_count, record.duplicate_count) == (1, 1)


# --- rejeições estruturais e duplicidade de arquivo ------------------------------------


def test_same_content_twice_raises_duplicate_file_sea43(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-43: mesmo conteúdo de Import concluído → 409 sem Import nem Transaction novos."""
    service = _service(uow_factory, settings)
    content = _csv("2026-01-01,A,-1.00,,")
    first = service.import_csv("a.csv", content)

    with pytest.raises(DuplicateFileError) as exc_info:
        service.import_csv("renomeado.csv", content)

    assert exc_info.value.http_status == 409
    assert str(first.id) in exc_info.value.message
    assert _imports(engine) == [("concluida", None, "a.csv")]
    assert _count(engine, "transactions") == 1


def test_resend_after_failed_import_is_accepted_sea107(
    uow_factory: UoWFactory,
    settings: Settings,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEA-107: após um Import `falhou` com o mesmo hash, o reenvio é aceito."""
    service = _service(uow_factory, settings)
    content = _csv("2026-01-01,A,-1.00,,")
    with monkeypatch.context() as patch:
        patch.setattr(SqlAlchemyTransactionRepository, "insert_ignoring_duplicates", _boom)
        with pytest.raises(ServiceUnavailableError):
            service.import_csv("a.csv", content)

    record = service.import_csv("a.csv", content)

    assert record.status is ImportStatus.COMPLETED
    assert [status for status, _, _ in _imports(engine)] == ["falhou", "concluida"]
    sha = hashlib.sha256(content).hexdigest()
    assert _scalar(engine, "SELECT count(DISTINCT file_sha256) FROM imports") == 1
    assert _scalar(engine, "SELECT min(file_sha256) FROM imports") == sha


def test_file_too_large_creates_nothing_sea104(
    uow_factory: UoWFactory, postgres_url: str, engine: Engine
) -> None:
    """SEA-104: conteúdo > MAX_UPLOAD_MB MiB → FileTooLargeError e nada gravado."""
    settings = Settings(database_url=postgres_url, max_upload_mb=1, _env_file=None)
    limit = 1024 * 1024
    head = _csv("2026-01-01,", header=HEADER)[:-1]
    tail = b",-1.00,,\n"
    exact = head + b"X" * (limit - len(head) - len(tail)) + tail
    assert len(exact) == limit
    service = _service(uow_factory, settings)

    with pytest.raises(FileTooLargeError) as exc_info:
        service.import_csv("big.csv", exact + b"\n")

    assert exc_info.value.http_status == 413
    assert _count(engine, "imports") == 0
    # Exatamente no limite ainda é aceito.
    assert service.import_csv("limit.csv", exact).imported_count == 1


@pytest.mark.parametrize(
    ("content", "error"),
    [
        (b"", EmptyFileError),
        (HEADER.encode() + b"\n\n\n", EmptyFileError),
        (b"\xff\xfe\x00bad", InvalidCsvError),
        (b"date,amount\n2026-01-01,-1.00\n", MissingColumnsError),
    ],
    ids=["empty", "header-only", "not-utf8", "missing-description"],
)
def test_structural_errors_create_nothing_sea90_sea92(
    uow_factory: UoWFactory,
    settings: Settings,
    engine: Engine,
    content: bytes,
    error: type[AppError],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SEA-90 a SEA-92: arquivo recusado estruturalmente não cria Import."""
    caplog.set_level(logging.INFO, logger=SERVICE_LOGGER)

    with pytest.raises(error):
        _service(uow_factory, settings).import_csv("x.csv", content)

    assert _count(engine, "imports") == 0
    messages = [r.getMessage() for r in caplog.records if r.name == SERVICE_LOGGER]
    assert any(m.startswith("import_rejected_structural filename=x.csv code=") for m in messages)


def test_long_filename_is_truncated_to_255(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """Seção 7 do plan: filename VARCHAR(255) truncado; controles e U+2028/U+2029 removidos."""
    name = "\x00a\nb\u2028\u2029" + "n" * 400 + ".csv"
    record = _service(uow_factory, settings).import_csv(name, _csv("2026-01-01,A,-1.00,,"))

    assert record.filename == ("ab" + "n" * 400)[:255]
    stored = _imports(engine)[0][2]
    assert stored == record.filename
    assert len(stored) == 255


# --- categorização e anomalias ---------------------------------------------------------


def test_rule_categorizes_matching_rows_sea17(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-17: regra "UBER" → Transporte; "PADARIA" fica na categoria padrão."""
    with uow_factory() as uow:
        transport = uow.categories.add("Transporte")
        uow.rules.add("UBER", transport.id, 1)
        uow.commit()

    _service(uow_factory, settings).import_csv(
        "c.csv", _csv("2026-01-01,UBER TRIP,-25.00,,", "2026-01-02,PADARIA,-8.00,,")
    )

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.description, c.name FROM transactions t "
                "JOIN categories c ON c.id = t.category_id ORDER BY t.description"
            )
        ).all()
    assert [tuple(r) for r in rows] == [
        ("PADARIA", "Não categorizada"),
        ("UBER TRIP", "Transporte"),
    ]


def test_anomalies_are_recomputed_after_import_sea60(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-60, SEA-28: 20 despesas entre 40 e 60 e uma de 5.000 → só ela vira anomalia."""
    lines = [f"2026-02-{i + 1:02d},COMPRA {i},-{40 + i}.00,,BRL" for i in range(20)]
    lines.append("2026-03-15,COMPRA GRANDE,-5000.00,,BRL")

    _service(uow_factory, settings).import_csv("anom.csv", _csv(*lines))

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.amount::text, a.method FROM anomalies a "
                "JOIN transactions t ON t.id = a.transaction_id"
            )
        ).all()
    assert [tuple(r) for r in rows] == [("-5000.00", "IQR")]


# --- falhas (DA-16, SEA-97) -------------------------------------------------------------


def test_operational_error_rolls_back_and_records_failure_sea97(
    uow_factory: UoWFactory,
    settings: Settings,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SEA-97: OperationalError → 503, 0 transações, 1 Import `falhou`, log import_failed."""
    monkeypatch.setattr(SqlAlchemyTransactionRepository, "insert_ignoring_duplicates", _boom)
    caplog.set_level(logging.INFO, logger=SERVICE_LOGGER)

    with pytest.raises(ServiceUnavailableError) as exc_info:
        _service(uow_factory, settings).import_csv("f.csv", _csv("2026-01-01,A,-1.00,,"))

    assert exc_info.value.http_status == 503
    assert isinstance(exc_info.value.__cause__, OperationalError)
    assert _count(engine, "transactions") == 0
    assert _imports(engine) == [("falhou", "OperationalError", "f.csv")]
    failed_id = _scalar(engine, "SELECT id FROM imports")
    errors = [r for r in caplog.records if r.name == SERVICE_LOGGER and r.levelno == logging.ERROR]
    assert [r.getMessage() for r in errors] == [
        f"import_failed import_id={failed_id} filename=f.csv reason=OperationalError"
    ]


def test_service_unavailable_from_domain_is_logged_and_reraised_sea97(
    uow_factory: UoWFactory,
    settings: Settings,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SEA-97: ServiceUnavailableError do domínio gera import_failed em ERROR antes do 503."""

    def _unavailable(*_args: object, **_kwargs: object) -> Any:
        raise ServiceUnavailableError()

    monkeypatch.setattr(SqlAlchemyTransactionRepository, "insert_ignoring_duplicates", _unavailable)
    caplog.set_level(logging.INFO, logger=SERVICE_LOGGER)

    with pytest.raises(ServiceUnavailableError):
        _service(uow_factory, settings).import_csv("s.csv", _csv("2026-01-01,A,-1.00,,"))

    assert _imports(engine) == [("falhou", "ServiceUnavailableError", "s.csv")]
    assert _count(engine, "transactions") == 0
    errors = [r for r in caplog.records if r.name == SERVICE_LOGGER and r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "import_failed" in errors[0].getMessage()
    assert errors[0].getMessage().endswith("reason=ServiceUnavailableError")


def test_unexpected_error_propagates_and_keeps_nothing_da16(
    uow_factory: UoWFactory,
    settings: Settings,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DA-16: erro não-SQL segue para o 500; transações e anomalias desfeitas; Import falhou."""

    def _explode(self: AnomalyService) -> int:
        raise RuntimeError("detalhe interno")

    monkeypatch.setattr(AnomalyService, "recompute_all", _explode)

    with pytest.raises(RuntimeError):
        _service(uow_factory, settings).import_csv("u.csv", _csv("2026-01-01,A,-1.00,,"))

    assert _count(engine, "transactions") == 0
    assert _count(engine, "import_rejections") == 0
    assert _imports(engine) == [("falhou", "RuntimeError", "u.csv")]


def test_failure_reason_is_truncated_to_500(
    uow_factory: UoWFactory,
    settings: Settings,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seção 7 do plan: failure_reason VARCHAR(500), truncado por defesa."""
    long_error = type("E" * 600, (Exception,), {})

    def _raise(*_args: object, **_kwargs: object) -> Any:
        raise long_error()

    monkeypatch.setattr(SqlAlchemyTransactionRepository, "insert_ignoring_duplicates", _raise)

    with pytest.raises(long_error):
        _service(uow_factory, settings).import_csv("l.csv", _csv("2026-01-01,A,-1.00,,"))

    assert _imports(engine) == [("falhou", "E" * 500, "l.csv")]


def test_failure_recording_is_best_effort_da16(
    uow_factory: UoWFactory,
    settings: Settings,
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DA-16: se gravar o `falhou` também falha, o 503 original continua e loga import_id=none."""
    monkeypatch.setattr(SqlAlchemyTransactionRepository, "insert_ignoring_duplicates", _boom)
    monkeypatch.setattr(SqlAlchemyImportRepository, "record_failure", _boom)
    caplog.set_level(logging.INFO, logger=SERVICE_LOGGER)

    with pytest.raises(ServiceUnavailableError):
        _service(uow_factory, settings).import_csv("b.csv", _csv("2026-01-01,A,-1.00,,"))

    assert _count(engine, "imports") == 0
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert "import_failed import_id=none filename=b.csv reason=OperationalError" in messages


# --- concorrência (SEA-98, SEA-106) -----------------------------------------------------


def _run_parallel(
    service: ImportService, jobs: list[tuple[str, bytes]]
) -> list[ImportRecord | BaseException]:
    barrier = threading.Barrier(len(jobs))
    results: list[ImportRecord | BaseException] = [RuntimeError("not run")] * len(jobs)

    def worker(index: int, filename: str, content: bytes) -> None:
        barrier.wait()
        try:
            results[index] = service.import_csv(filename, content)
        except BaseException as exc:  # noqa: BLE001 - o teste inspeciona o resultado
            results[index] = exc

    threads = [
        threading.Thread(target=worker, args=(i, name, content))
        for i, (name, content) in enumerate(jobs)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def test_parallel_imports_of_different_files_are_independent_sea98(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-98: dois arquivos diferentes em paralelo → contagens corretas e independentes."""
    file_a = _csv(*[f"2026-01-{d:02d},LOJA A {d},-{d}.00,," for d in range(1, 8)])
    file_b = _csv(*[f"2026-02-{d:02d},LOJA B {d},-{d}.00,," for d in range(1, 5)], "x,Y,-1,,")

    results = _run_parallel(_service(uow_factory, settings), [("a.csv", file_a), ("b.csv", file_b)])

    record_a, record_b = results
    assert isinstance(record_a, ImportRecord)
    assert isinstance(record_b, ImportRecord)
    assert (record_a.imported_count, record_a.rejected_count) == (7, 0)
    assert (record_b.imported_count, record_b.rejected_count) == (4, 1)
    for record, expected in ((record_a, 7), (record_b, 4)):
        linked = _scalar(
            engine, "SELECT count(*) FROM transactions WHERE import_id = :i", i=record.id
        )
        assert linked == expected


def test_parallel_overlapping_files_in_reverse_order_do_not_deadlock_sea98(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-98: 3000 chaves em comum em ordens inversas, em paralelo → sem deadlock nem 503."""
    common = [
        f"2026-05-{d % 28 + 1:02d},COMUM {d},-{d % 97 + 1}.{d % 100:02d},," for d in range(3000)
    ]
    file_a = _csv(*common, "2026-06-01,SO A,-1.00,,")
    file_b = _csv(*reversed(common), "2026-06-02,SO B,-1.00,,")

    results = _run_parallel(_service(uow_factory, settings), [("a.csv", file_a), ("b.csv", file_b)])

    record_a, record_b = results
    assert isinstance(record_a, ImportRecord), repr(record_a)
    assert isinstance(record_b, ImportRecord), repr(record_b)
    assert record_a.imported_count + record_b.imported_count == 3002
    assert record_a.duplicate_count + record_b.duplicate_count == 3000
    assert _count(engine, "transactions") == 3002
    assert [status for status, _, _ in _imports(engine)] == ["concluida", "concluida"]


def test_parallel_imports_of_same_content_never_duplicate_sea106(
    uow_factory: UoWFactory, settings: Settings, engine: Engine
) -> None:
    """SEA-106: mesmo conteúdo em paralelo → cada chave de deduplicação existe 1 vez."""
    content = _csv(*[f"2026-03-{d:02d},ITEM {d},-{d}.00,," for d in range(1, 11)])

    results = _run_parallel(_service(uow_factory, settings), [("x.csv", content)] * 2)

    records = [r for r in results if isinstance(r, ImportRecord)]
    others = [r for r in results if not isinstance(r, ImportRecord)]
    assert all(isinstance(e, DuplicateFileError) for e in others)
    assert sum(r.imported_count for r in records) == 10
    assert _count(engine, "transactions") == 10
    assert _scalar(engine, "SELECT count(DISTINCT dedup_key) FROM transactions") == 10


# --- observabilidade e AS-3 -------------------------------------------------------------


def test_logs_have_lifecycle_and_no_financial_data_sea14_as3(
    uow_factory: UoWFactory, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """SEA-14, AS-3: import_started/finished com id e duração; nada de descrição/merchant/valor."""
    secret_description = "FARMACIA SIGILOSA ZQX"
    secret_merchant = "ESTABELECIMENTO OCULTO WVK"
    secret_amount = "987.61"
    content = _csv(
        f"2026-04-01,{secret_description},-{secret_amount},{secret_merchant},",
        f"2026-04-02,{secret_description} 2,abc,,",
    )
    caplog.set_level(logging.DEBUG)

    record = _service(uow_factory, settings).import_csv("log.csv", content)

    messages = [r.getMessage() for r in caplog.records if r.name == SERVICE_LOGGER]
    started = [m for m in messages if m.startswith("import_started")]
    finished = [m for m in messages if m.startswith("import_finished")]
    assert started == [
        f"import_started import_id={record.id} filename=log.csv size_bytes={len(content)}"
    ]
    assert len(finished) == 1
    assert finished[0].startswith(
        f"import_finished import_id={record.id} filename=log.csv "
        "status=concluida_com_rejeicoes rows_read=2 imported=1 rejected=1 duplicates=0 duration_ms="
    )
    assert int(finished[0].rsplit("duration_ms=", 1)[1]) >= 0
    everything = caplog.text + "\n".join(
        f"{r.getMessage()} {r.args!r} {r.exc_text or ''}" for r in caplog.records
    )
    for secret in (secret_description, "SIGILOSA", secret_merchant, secret_amount):
        assert secret not in everything

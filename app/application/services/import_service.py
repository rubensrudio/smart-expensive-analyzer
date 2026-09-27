"""Serviço de importação de CSV (CT-17; fluxo 5.2 e DA-16 do plan).

Requisitos: SEA-07, SEA-08, SEA-14, SEA-17, SEA-41 a SEA-45, SEA-60, SEA-97, SEA-98,
SEA-102 a SEA-104, SEA-106, SEA-107.

AS-3: nenhum log ou ``failure_reason`` carrega descrição, estabelecimento ou valor.
Os logs citam só id, nome do arquivo, contagens, códigos e nomes de exceção.
"""

import hashlib
import logging
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, NoReturn

from sqlalchemy.exc import SQLAlchemyError

from app.application.services.anomaly_service import AnomalyService
from app.core.config import Settings
from app.core.errors import AppError, DuplicateFileError, FileTooLargeError, ServiceUnavailableError
from app.domain.categorization import RuleMatcher
from app.domain.csv_rows import ParsedRow, dedup_key, parse_row
from app.domain.entities import ImportRecord, ImportStatus, NewTransaction, RowRejection
from app.domain.ports import UnitOfWork
from app.infrastructure.csv_reader import RawRow, read_csv_rows

logger = logging.getLogger(__name__)

# Tamanhos das colunas `imports.filename` e `imports.failure_reason` (seção 7).
FILENAME_MAX_LENGTH: Final = 255
FAILURE_REASON_MAX_LENGTH: Final = 500
_BYTES_PER_MB: Final = 1024 * 1024
# Cc = controles (NUL, \n, \r...); Zl/Zp = U+2028/U+2029.
_STRIPPED_CATEGORIES: Final = frozenset({"Cc", "Zl", "Zp"})


def _clean_filename(filename: str) -> str:
    """Remove controles e separadores de linha/parágrafo e trunca em 255.

    O PostgreSQL recusa NUL em texto, e quebras de linha no nome (inclusive
    U+2028/U+2029) forjariam linhas de log. O nome limpo é o gravado, o logado e
    o devolvido.
    """
    printable = "".join(
        ch for ch in filename if unicodedata.category(ch) not in _STRIPPED_CATEGORIES
    )
    return printable[:FILENAME_MAX_LENGTH]


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


@dataclass(frozen=True, slots=True)
class _Upload:
    filename: str
    sha256: str
    size_bytes: int
    received_at: datetime
    started: float


@dataclass(frozen=True, slots=True)
class _RowsOutcome:
    unique: list[ParsedRow]
    rejections: list[RowRejection]
    in_file_duplicates: int


class ImportService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork], settings: Settings) -> None:
        self._uow_factory = uow_factory
        self._settings = settings

    def import_csv(self, filename: str, content: bytes) -> ImportRecord:
        """Importa o CSV de forma síncrona e devolve o Import já em estado terminal (SEA-45).

        Erros estruturais e de tamanho ocorrem antes de abrir o UoW e não gravam nada.
        Falhas depois disso seguem DA-16: rollback, Import ``falhou`` num UoW novo e
        relançamento (``SQLAlchemyError`` vira ``ServiceUnavailableError``).
        """
        started = time.perf_counter()
        received_at = datetime.now(UTC)
        clean_name = _clean_filename(filename)

        limit_mb = self._settings.max_upload_mb
        if len(content) > limit_mb * _BYTES_PER_MB:
            self._log_structural(clean_name, FileTooLargeError(limit_mb))

        try:
            raw_rows = read_csv_rows(content)
        except AppError as exc:
            self._log_structural(clean_name, exc)

        upload = _Upload(
            filename=clean_name,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            received_at=received_at,
            started=started,
        )
        try:
            return self._persist(upload, raw_rows)
        except DuplicateFileError:
            # Recusa esperada (SEA-43): nada foi gravado e não é falha.
            raise
        except Exception as exc:
            self._record_failure(upload, exc)
            if isinstance(exc, SQLAlchemyError):
                raise ServiceUnavailableError() from exc
            raise

    def _log_structural(self, filename: str, error: AppError) -> NoReturn:
        """Loga a recusa estrutural (seção 14) e relança o erro recebido."""
        logger.info("import_rejected_structural filename=%s code=%s", filename, error.code)
        raise error

    def _persist(self, upload: _Upload, raw_rows: list[RawRow]) -> ImportRecord:
        with self._uow_factory() as uow:
            existing_id = uow.imports.find_completed_by_hash(upload.sha256)
            if existing_id is not None:
                self._log_structural(upload.filename, DuplicateFileError(existing_id))

            import_id = uow.imports.create_processing(
                upload.filename, upload.sha256, upload.received_at
            )
            logger.info(
                "import_started import_id=%d filename=%s size_bytes=%d",
                import_id,
                upload.filename,
                upload.size_bytes,
            )

            outcome = self._parse_rows(raw_rows)
            matcher = RuleMatcher(uow.rules.list_all(), uow.categories.get_default().id)
            items = [
                NewTransaction(
                    date=row.date,
                    description=row.description,
                    merchant=row.merchant,
                    amount=row.amount,
                    currency=row.currency,
                    type=row.type,
                    category_id=matcher.match(row.description, row.merchant),
                    import_id=import_id,
                    dedup_key=dedup_key(row.date, row.amount, row.description, row.currency),
                )
                for row in outcome.unique
            ]
            # Ordem global por chave: imports paralelos com chaves em comum travam as
            # tuplas do índice único na mesma ordem e não entram em deadlock (SEA-98).
            items.sort(key=lambda item: item.dedup_key)
            inserted = uow.transactions.insert_ignoring_duplicates(items) if items else 0

            status = (
                ImportStatus.COMPLETED_WITH_REJECTIONS
                if outcome.rejections
                else ImportStatus.COMPLETED
            )
            record = uow.imports.finish(
                import_id,
                status,
                rows_read=len(raw_rows),
                imported_count=inserted,
                rejected_count=len(outcome.rejections),
                # Repetidas no arquivo + válidas únicas que o banco já tinha (SEA-44, SEA-103).
                duplicate_count=outcome.in_file_duplicates + (len(items) - inserted),
                rejections=outcome.rejections,
            )
            AnomalyService(
                uow, self._settings.anomaly_iqr_k, self._settings.anomaly_min_sample
            ).recompute_all()
            uow.commit()

        logger.info(
            "import_finished import_id=%d filename=%s status=%s rows_read=%d imported=%d "
            "rejected=%d duplicates=%d duration_ms=%d",
            record.id,
            upload.filename,
            record.status.value,
            record.rows_read,
            record.imported_count,
            record.rejected_count,
            record.duplicate_count,
            _elapsed_ms(upload.started),
        )
        return record

    def _parse_rows(self, raw_rows: list[RawRow]) -> _RowsOutcome:
        """Valida cada linha e deduplica dentro do arquivo: a primeira ocorrência vence."""
        unique: list[ParsedRow] = []
        rejections: list[RowRejection] = []
        seen: set[str] = set()
        in_file_duplicates = 0
        for raw in raw_rows:
            parsed = parse_row(raw.line_number, raw.values, self._settings.default_currency)
            if isinstance(parsed, RowRejection):
                rejections.append(parsed)
                continue
            # A descrição do ParsedRow já vem normalizada (P-08).
            key = dedup_key(parsed.date, parsed.amount, parsed.description, parsed.currency)
            if key in seen:
                in_file_duplicates += 1
                continue
            seen.add(key)
            unique.append(parsed)
        return _RowsOutcome(unique, rejections, in_file_duplicates)

    def _record_failure(self, upload: _Upload, error: Exception) -> None:
        """DA-16: grava o Import ``falhou`` num UoW novo (melhor esforço) e loga em ERROR."""
        reason = type(error).__name__[:FAILURE_REASON_MAX_LENGTH]
        failed_id: int | None = None
        try:
            with self._uow_factory() as uow:
                failed_id = uow.imports.record_failure(
                    upload.filename, upload.sha256, upload.received_at, reason
                )
                uow.commit()
        except Exception as record_error:
            failed_id = None
            logger.error(
                "import_failure_not_recorded filename=%s reason=%s",
                upload.filename,
                type(record_error).__name__,
            )
        logger.error(
            "import_failed import_id=%s filename=%s reason=%s",
            failed_id if failed_id is not None else "none",
            upload.filename,
            reason,
        )

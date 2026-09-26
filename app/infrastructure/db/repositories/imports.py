"""Repositório SQLAlchemy de Import (CT-25; SEA-41, SEA-43, SEA-107).

Não faz commit: a transação pertence ao ``UnitOfWork`` (DA-2).
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.entities import ImportRecord, ImportStatus, RowRejection
from app.infrastructure.db.models import ImportModel, ImportRejectionModel

# Só um Import concluído bloqueia o reenvio do mesmo arquivo (SEA-43, SEA-107).
_COMPLETED_STATUSES = (
    ImportStatus.COMPLETED.value,
    ImportStatus.COMPLETED_WITH_REJECTIONS.value,
)


class SqlAlchemyImportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_completed_by_hash(self, file_sha256: str) -> int | None:
        stmt = (
            select(ImportModel.id)
            .where(
                ImportModel.file_sha256 == file_sha256,
                ImportModel.status.in_(_COMPLETED_STATUSES),
            )
            .order_by(ImportModel.id)
            .limit(1)
        )
        return self._session.scalar(stmt)

    def create_processing(self, filename: str, file_sha256: str, received_at: datetime) -> int:
        model = ImportModel(
            filename=filename,
            file_sha256=file_sha256,
            status=ImportStatus.PROCESSING.value,
            received_at=received_at,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def finish(
        self,
        import_id: int,
        status: ImportStatus,
        rows_read: int,
        imported_count: int,
        rejected_count: int,
        duplicate_count: int,
        rejections: Sequence[RowRejection],
    ) -> ImportRecord:
        model = self._session.get(ImportModel, import_id)
        if model is None:
            raise LookupError(f"Import {import_id} não encontrado")

        model.status = ImportStatus(status).value
        model.rows_read = rows_read
        model.imported_count = imported_count
        model.rejected_count = rejected_count
        model.duplicate_count = duplicate_count
        model.finished_at = func.now()
        self._session.add_all(
            ImportRejectionModel(import_id=import_id, line_number=r.line_number, reason=r.reason)
            for r in rejections
        )
        self._session.flush()

        return ImportRecord(
            id=model.id,
            filename=model.filename,
            status=ImportStatus(model.status),
            received_at=model.received_at,
            rows_read=model.rows_read,
            imported_count=model.imported_count,
            rejected_count=model.rejected_count,
            duplicate_count=model.duplicate_count,
            rejections=tuple(RowRejection(r.line_number, r.reason) for r in rejections),
        )

    def record_failure(
        self, filename: str, file_sha256: str, received_at: datetime, reason: str
    ) -> int:
        model = ImportModel(
            filename=filename,
            file_sha256=file_sha256,
            status=ImportStatus.FAILED.value,
            received_at=received_at,
            finished_at=func.now(),
            failure_reason=reason,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

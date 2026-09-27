"""Schemas de `POST /imports` (contrato 8.1).

`rejections[].reason` é o texto de apresentação "Linha N: motivo" (CT-12). O
motivo nunca carrega o valor da célula recusada (AS-3).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.csv_rows import format_rejection
from app.domain.entities import ImportRecord, RowRejection

ImportOutStatus = Literal["concluida", "concluida_com_rejeicoes"]


class RejectionOut(BaseModel):
    line: int
    reason: str

    @classmethod
    def from_entity(cls, rejection: RowRejection) -> "RejectionOut":
        return cls(line=rejection.line_number, reason=format_rejection(rejection))


class ImportOut(BaseModel):
    id: int
    filename: str
    status: ImportOutStatus
    received_at: datetime
    rows_read: int
    imported_count: int
    rejected_count: int
    duplicate_count: int
    rejections: list[RejectionOut]

    @classmethod
    def from_record(cls, record: ImportRecord) -> "ImportOut":
        # O serviço só devolve Import terminal com sucesso (SEA-45). Um status fora do
        # Literal falha a validação e cai no handler de 500, sem resposta incoerente.
        return cls.model_validate(
            {
                "id": record.id,
                "filename": record.filename,
                "status": record.status.value,
                "received_at": record.received_at,
                "rows_read": record.rows_read,
                "imported_count": record.imported_count,
                "rejected_count": record.rejected_count,
                "duplicate_count": record.duplicate_count,
                "rejections": [RejectionOut.from_entity(r) for r in record.rejections],
            }
        )

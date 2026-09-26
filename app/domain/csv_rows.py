"""Validação e normalização de uma linha do CSV (CT-12).

Regras: SEA-09, SEA-36 a SEA-39, SEA-41, SEA-110; premissas P-03, P-06, P-08.
Os motivos de rejeição são textos fixos e nunca incluem o conteúdo das
células (AS-3).
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from app.domain.currency import normalize_currency_code
from app.domain.entities import RowRejection, TransactionType
from app.domain.text import normalize_whitespace

REASON_DATE_MISSING: Final = "data ausente"
REASON_DATE_INVALID: Final = "data inválida"
REASON_DESCRIPTION_EMPTY: Final = "descrição vazia"
REASON_AMOUNT_MISSING: Final = "valor ausente"
REASON_AMOUNT_NOT_NUMERIC: Final = "valor não numérico"
REASON_AMOUNT_ZERO: Final = "valor igual a zero"
REASON_CURRENCY_INVALID: Final = "moeda fora da ISO 4217"
REASON_SEPARATOR: Final = "; "

# AAAA-MM-DD exato, só dígitos ASCII (date.fromisoformat aceita outras formas).
_DATE_RE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Sinal opcional, ponto decimal, sem milhar nem notação científica (P-03).
_AMOUNT_RE: Final = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")
_CENTS: Final = Decimal("0.01")
# Limite de NUMERIC(14,2): até 12 dígitos inteiros (LAC-22).
_AMOUNT_LIMIT: Final = Decimal(10) ** 12


@dataclass(frozen=True, slots=True)
class ParsedRow:
    line_number: int
    date: date
    description: str
    merchant: str
    amount: Decimal
    currency: str
    type: TransactionType


def _parse_date(raw: str) -> date | str:
    text = raw.strip()
    if not text:
        return REASON_DATE_MISSING
    if not _DATE_RE.fullmatch(text):
        return REASON_DATE_INVALID
    try:
        return date.fromisoformat(text)
    except ValueError:
        return REASON_DATE_INVALID


def _parse_amount(raw: str) -> Decimal | str:
    text = raw.strip()
    if not text:
        return REASON_AMOUNT_MISSING
    if not _AMOUNT_RE.fullmatch(text):
        return REASON_AMOUNT_NOT_NUMERIC
    try:
        amount = Decimal(text).quantize(_CENTS, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        # Excede a precisão do contexto decimal; tratado como não numérico.
        return REASON_AMOUNT_NOT_NUMERIC
    if amount.is_zero():
        return REASON_AMOUNT_ZERO
    if abs(amount) >= _AMOUNT_LIMIT:
        # Não cabe em NUMERIC(14,2); rejeita a linha em vez de falhar no banco (LAC-22).
        return REASON_AMOUNT_NOT_NUMERIC
    return amount


def _parse_currency(raw: str, default_currency: str) -> str | None:
    if not raw.strip():
        return default_currency
    return normalize_currency_code(raw)


def parse_row(
    line_number: int, values: Mapping[str, str], default_currency: str
) -> ParsedRow | RowRejection:
    """Valida uma linha e devolve a transação normalizada ou a rejeição com todos os motivos."""
    reasons: list[str] = []

    parsed_date = _parse_date(values.get("date", ""))
    if isinstance(parsed_date, str):
        reasons.append(parsed_date)

    description = normalize_whitespace(values.get("description", ""))
    if not description:
        reasons.append(REASON_DESCRIPTION_EMPTY)

    amount = _parse_amount(values.get("amount", ""))
    if isinstance(amount, str):
        reasons.append(amount)

    currency = _parse_currency(values.get("currency", ""), default_currency)
    if currency is None:
        reasons.append(REASON_CURRENCY_INVALID)

    if reasons or isinstance(parsed_date, str) or isinstance(amount, str) or currency is None:
        return RowRejection(line_number=line_number, reason=REASON_SEPARATOR.join(reasons))

    merchant = normalize_whitespace(values.get("merchant", "")) or description
    return ParsedRow(
        line_number=line_number,
        date=parsed_date,
        description=description,
        merchant=merchant,
        amount=amount,
        currency=currency,
        type=TransactionType.from_amount(amount),
    )


def dedup_key(date: date, amount: Decimal, description: str, currency: str) -> str:
    """SHA-256 hex de "data|valor com 2 casas|descrição|moeda" (DA-6, P-08)."""
    payload = f"{date.isoformat()}|{amount:.2f}|{description}|{currency}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def format_rejection(rejection: RowRejection) -> str:
    return f"Linha {rejection.line_number}: {rejection.reason}"

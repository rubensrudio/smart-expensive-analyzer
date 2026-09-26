import math
from datetime import date
from decimal import Decimal

import pytest

from app.domain.anomaly_detection import IQR_METHOD, detect_iqr_anomalies
from app.domain.entities import AnomalyCandidate, ExpenseRecord


def _expense(
    transaction_id: int,
    value: str,
    *,
    currency: str = "BRL",
    category_id: int = 1,
    category_name: str = "Alimentação",
) -> ExpenseRecord:
    return ExpenseRecord(
        transaction_id=transaction_id,
        date=date(2026, 1, 1),
        value=Decimal(value),
        currency=currency,
        category_id=category_id,
        category_name=category_name,
        merchant="Loja",
    )


def _sea28_records(currency: str = "BRL", start_id: int = 1) -> list[ExpenseRecord]:
    # 20 despesas de 40.00 a 59.00 (passo 1.00) + uma de 5000.00.
    records = [_expense(start_id + i, f"{40 + i}.00", currency=currency) for i in range(20)]
    records.append(_expense(start_id + 20, "5000.00", currency=currency))
    return records


def _moderate_records() -> list[ExpenseRecord]:
    # Q1=12.5, Q3=17.5, IQR=5; limite k=1.5 → 25.00; k=3.0 → 32.50.
    values = ["10", "11", "12", "13", "14", "15", "16", "17", "18", "26", "35"]
    return [_expense(i + 1, v) for i, v in enumerate(values)]


def test_iqr_method_constant() -> None:
    assert IQR_METHOD == "IQR"


def test_sea28_flags_only_the_outlier() -> None:
    result = detect_iqr_anomalies(_sea28_records(), k=1.5, min_sample=8)

    assert len(result) == 1
    candidate = result[0]
    assert candidate.transaction_id == 21
    assert candidate.method == "IQR"
    assert "5000.00" in candidate.reason


def test_reason_and_value_follow_contract_format() -> None:
    # Q1=45.00, Q3=55.00, IQR=10.00, limite=55+1.5*10=70.00
    result = detect_iqr_anomalies(_sea28_records(), k=1.5, min_sample=8)

    candidate = result[0]
    assert candidate.value == Decimal("70.00")
    assert candidate.value.as_tuple().exponent == -2
    assert candidate.reason == (
        "Valor 5000.00 BRL acima do limite IQR 70.00 (Q3 55.00 + 1.5 × IQR 10.00) "
        "na categoria Alimentação, grupo de 21 despesas."
    )


def test_sea59_group_below_min_sample_is_ignored() -> None:
    records = [_expense(i + 1, "50.00") for i in range(6)]
    records.append(_expense(7, "5000.00"))

    assert detect_iqr_anomalies(records, k=1.5, min_sample=8) == []


def test_group_exactly_at_min_sample_is_evaluated() -> None:
    records = [_expense(i + 1, f"{50 + i}.00") for i in range(7)]
    records.append(_expense(8, "5000.00"))

    result = detect_iqr_anomalies(records, k=1.5, min_sample=8)

    assert [c.transaction_id for c in result] == [8]


def test_sea96_empty_input_returns_empty_list() -> None:
    assert detect_iqr_anomalies([], k=1.5, min_sample=8) == []


def test_sea54_currencies_are_evaluated_separately() -> None:
    brl = _sea28_records("BRL", start_id=1)
    usd = _sea28_records("USD", start_id=101)

    result = detect_iqr_anomalies(brl + usd, k=1.5, min_sample=8)

    assert [c.transaction_id for c in result] == [21, 121]
    assert " BRL " in result[0].reason
    assert " USD " in result[1].reason


def test_sea54_currency_split_can_drop_group_below_min_sample() -> None:
    # 5 BRL + 5 USD na mesma categoria: juntas seriam 10 ≥ 8, separadas 5 < 8.
    records = [_expense(i + 1, "50.00", currency="BRL") for i in range(4)]
    records.append(_expense(5, "5000.00", currency="BRL"))
    records += [_expense(10 + i, "50.00", currency="USD") for i in range(5)]

    assert detect_iqr_anomalies(records, k=1.5, min_sample=8) == []


def test_categories_are_evaluated_separately() -> None:
    cheap = [_expense(i + 1, f"{10 + i}.00", category_id=1) for i in range(10)]
    expensive = [
        _expense(100 + i, f"{1000 + i}.00", category_id=2, category_name="Moradia")
        for i in range(10)
    ]

    # Juntas, as despesas de 1000+ seriam discrepantes; separadas, nenhuma é.
    assert detect_iqr_anomalies(cheap + expensive, k=1.5, min_sample=8) == []


def test_sea58_higher_k_flags_fewer() -> None:
    records = _moderate_records()

    lenient = detect_iqr_anomalies(records, k=1.5, min_sample=8)
    strict = detect_iqr_anomalies(records, k=3.0, min_sample=8)

    assert [c.transaction_id for c in lenient] == [10, 11]
    assert [c.transaction_id for c in strict] == [11]
    assert len(strict) < len(lenient)


@pytest.mark.parametrize(("top", "flagged"), [("31.00", False), ("31.01", True)])
def test_comparison_is_strictly_greater_than_limit(top: str, flagged: bool) -> None:
    # [10..22 passo 2] + top: Q1=13.5, Q3=20.5, IQR=7 → limite 31.00.
    values = ["10", "12", "14", "16", "18", "20", "22", top]
    records = [_expense(i + 1, v) for i, v in enumerate(values)]

    result = detect_iqr_anomalies(records, k=1.5, min_sample=8)

    assert [c.transaction_id for c in result] == ([8] if flagged else [])


def test_sea30_deterministic_output() -> None:
    records = _moderate_records() + _sea28_records("USD", start_id=200)

    first = detect_iqr_anomalies(records, k=1.5, min_sample=8)
    second = detect_iqr_anomalies(list(reversed(records)), k=1.5, min_sample=8)

    assert first == second
    assert [c.transaction_id for c in first] == sorted(c.transaction_id for c in first)
    assert all(isinstance(c, AnomalyCandidate) for c in first)


def test_sea29_detection_does_not_depend_on_sign_handling() -> None:
    # Entrada já vem em módulo (list_expenses). Nenhum valor baixo é marcado:
    # a regra só olha o lado de cima (value > Q3 + k·IQR).
    records = [_expense(i + 1, f"{50 + i}.00") for i in range(10)]
    records.append(_expense(11, "0.01"))

    assert detect_iqr_anomalies(records, k=1.5, min_sample=8) == []


@pytest.mark.parametrize("k", [0.0, -1.5, math.inf, -math.inf, math.nan])
def test_invalid_k_is_rejected(k: float) -> None:
    with pytest.raises(ValueError, match="k"):
        detect_iqr_anomalies(_sea28_records(), k=k, min_sample=8)


@pytest.mark.parametrize("min_sample", [0, -1])
def test_invalid_min_sample_is_rejected(min_sample: int) -> None:
    with pytest.raises(ValueError, match="min_sample"):
        detect_iqr_anomalies(_sea28_records(), k=1.5, min_sample=min_sample)

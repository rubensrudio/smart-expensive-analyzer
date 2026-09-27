"""Serviço de analytics contra PostgreSQL real (CT-21, TASK-023).

Requisitos: SEA-20..SEA-25, SEA-54..SEA-57, SEA-61, SEA-62, SEA-95, SEA-101.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.application.services.analytics_service import AnalyticsService
from app.domain.entities import ExpenseFilters, NewTransaction, Period, TransactionType
from app.domain.ports import UnitOfWork

UoWFactory = Callable[[], UnitOfWork]

RECEIVED_AT = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
DEFAULT_DAY = date(2026, 1, 10)


@dataclass(frozen=True)
class Row:
    amount: str
    currency: str = "BRL"
    merchant: str = "Loja"
    category: str | None = None  # None → categoria padrão
    day: date = DEFAULT_DAY


def _seed(uow_factory: UoWFactory, rows: Sequence[Row]) -> dict[str, int]:
    """Grava as linhas e devolve `nome da categoria -> id` (inclui a padrão)."""
    with uow_factory() as uow:
        import_id = uow.imports.create_processing("extrato.csv", "a" * 64, RECEIVED_AT)
        default = uow.categories.get_default()
        ids = {default.name: default.id}
        for name in sorted({r.category for r in rows if r.category is not None}):
            ids[name] = uow.categories.add(name).id
        items = []
        for idx, row in enumerate(rows):
            value = Decimal(row.amount)
            items.append(
                NewTransaction(
                    date=row.day,
                    description=f"COMPRA {idx}",
                    merchant=row.merchant,
                    amount=value,
                    currency=row.currency,
                    type=TransactionType.from_amount(value),
                    category_id=ids[row.category] if row.category else default.id,
                    import_id=import_id,
                    dedup_key=f"{idx:064d}",
                )
            )
        assert uow.transactions.insert_ignoring_duplicates(items) == len(items)
        uow.commit()
    return ids


def _d(value: str) -> Decimal:
    return Decimal(value)


# ---------------------------------------------------------------- summary


def test_summary_excludes_income_and_computes_stats_sea20_sea25(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """SEA-20, SEA-25, SEA-26: receita de 1000.00 fica fora de todos os cálculos."""
    _seed(uow_factory, [Row("-10.00"), Row("-20.00"), Row("-60.00"), Row("1000.00")])

    result = AnalyticsService(uow).summary(ExpenseFilters())

    assert [g.currency for g in result] == ["BRL"]
    stats = result[0].stats
    assert (stats.total, stats.mean, stats.median, stats.count) == (
        _d("90.00"),
        _d("30.00"),
        _d("20.00"),
        3,
    )


def test_summary_separates_currencies_alphabetically_sea54(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """SEA-54: BRL e USD em grupos próprios, em ordem alfabética, sem somar moedas."""
    _seed(
        uow_factory,
        [Row("-100.00", "USD"), Row("-10.00", "BRL"), Row("-30.00", "BRL"), Row("-5.00", "USD")],
    )

    result = AnalyticsService(uow).summary(ExpenseFilters())

    assert [g.currency for g in result] == ["BRL", "USD"]
    brl, usd = result
    assert (brl.stats.total, brl.stats.count) == (_d("40.00"), 2)
    assert (usd.stats.total, usd.stats.count) == (_d("105.00"), 2)
    assert sum(b.count for b in brl.histogram) == 2
    assert sum(b.count for b in usd.histogram) == 2
    assert [(m.merchant, m.total, m.count) for m in brl.by_merchant] == [("Loja", _d("40.00"), 2)]
    assert [(m.merchant, m.total, m.count) for m in usd.by_merchant] == [("Loja", _d("105.00"), 2)]


def test_summary_includes_merchants_and_four_histogram_buckets_sea22_sea56(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """SEA-22, SEA-56: by_merchant por total desc/merchant asc; histograma com 4 faixas."""
    _seed(
        uow_factory,
        [
            Row("-10.00", merchant="Padaria"),
            Row("-15.50", merchant="Padaria"),
            Row("-70.00", merchant="Mercado"),
            Row("-25.50", merchant="Bar"),
            Row("-25.50", merchant="Açougue"),
        ],
    )

    [group] = AnalyticsService(uow).summary(ExpenseFilters())

    assert [(m.merchant, m.total, m.count) for m in group.by_merchant] == [
        ("Mercado", _d("70.00"), 1),
        ("Açougue", _d("25.50"), 1),
        ("Bar", _d("25.50"), 1),
        ("Padaria", _d("25.50"), 2),
    ]
    assert [(b.range_start, b.range_end, b.count, b.total) for b in group.histogram] == [
        (_d("0"), _d("50"), 4, _d("76.50")),
        (_d("50"), _d("100"), 1, _d("70.00")),
        (_d("100"), _d("500"), 0, _d("0.00")),
        (_d("500"), None, 0, _d("0.00")),
    ]


def test_summary_applies_combined_filters_sea21(uow_factory: UoWFactory, uow: UnitOfWork) -> None:
    """SEA-21: período, categoria e estabelecimento combinados restringem o escopo."""
    ids = _seed(
        uow_factory,
        [
            Row("-10.00", merchant="Mercado", category="Alimentação", day=date(2026, 1, 5)),
            Row("-20.00", merchant="Mercado", category="Alimentação", day=date(2026, 1, 20)),
            Row("-40.00", merchant="Mercado", category="Alimentação", day=date(2026, 2, 5)),
            Row("-80.00", merchant="Padaria", category="Alimentação", day=date(2026, 1, 6)),
            Row("-160.00", merchant="Mercado", category="Casa", day=date(2026, 1, 7)),
        ],
    )
    filters = ExpenseFilters(
        period=Period(date(2026, 1, 1), date(2026, 1, 31)),
        category_id=ids["Alimentação"],
        merchant="mercado",
    )

    [group] = AnalyticsService(uow).summary(filters)

    assert (group.stats.total, group.stats.count) == (_d("30.00"), 2)
    assert [m.merchant for m in group.by_merchant] == ["Mercado"]


def test_summary_unknown_category_returns_empty_sea101(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """SEA-101: category_id inexistente → nenhuma moeda."""
    _seed(uow_factory, [Row("-10.00")])

    assert AnalyticsService(uow).summary(ExpenseFilters(category_id=999_999)) == []


def test_empty_scope_returns_empty_lists_sea95(uow: UnitOfWork) -> None:
    """SEA-95: sem despesas → [] em summary, categories e monthly."""
    service = AnalyticsService(uow)

    assert service.summary(ExpenseFilters()) == []
    assert service.categories(Period()) == []
    assert service.monthly(Period()) == []


def test_only_income_counts_as_empty_scope_sea25_sea95(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """SEA-25, SEA-95: só receitas no banco → nenhum grupo de moeda."""
    _seed(uow_factory, [Row("500.00"), Row("20.00", "USD")])
    service = AnalyticsService(uow)

    assert service.summary(ExpenseFilters()) == []
    assert service.categories(Period()) == []
    assert service.monthly(Period()) == []


# ------------------------------------------------------------- categories


def test_categories_percentages_sum_100_per_currency_sea23_sea55(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """SEA-23, SEA-54, SEA-55: percentuais pelo total da moeda, somando 100.00 em cada."""
    _seed(
        uow_factory,
        [
            Row("-10.00", category="Alimentação"),
            Row("-10.00", category="Casa"),
            Row("-10.00"),
            Row("-30.00", "USD", category="Casa"),
            Row("-10.00", "USD", category="Casa"),
            Row("-20.00", "USD", category="Lazer"),
            Row("999.00", category="Alimentação"),
        ],
    )

    result = AnalyticsService(uow).categories(Period())

    assert [g.currency for g in result] == ["BRL", "USD"]
    for group in result:
        assert sum(c.percentage for c in group.categories) == _d("100.00")
    brl, usd = result
    assert brl.total == _d("30.00")
    assert usd.total == _d("60.00")
    assert sorted(c.percentage for c in brl.categories) == [
        _d("33.33"),
        _d("33.33"),
        _d("33.34"),
    ]
    assert [
        (c.category_name, c.stats.total, c.stats.count, c.stats.mean, c.stats.median, c.percentage)
        for c in usd.categories
    ] == [
        ("Casa", _d("40.00"), 2, _d("20.00"), _d("20.00"), _d("66.67")),
        ("Lazer", _d("20.00"), 1, _d("20.00"), _d("20.00"), _d("33.33")),
    ]


def test_categories_ordered_by_total_desc_then_name_sea23(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """Categorias por total desc e nome asc; a padrão aparece como qualquer outra (SEA-52)."""
    ids = _seed(
        uow_factory,
        [
            Row("-5.00", category="Zoo"),
            Row("-5.00", category="Arte"),
            Row("-50.00", category="Casa"),
            Row("-1.00"),
        ],
    )
    default_name = next(name for name in ids if name not in {"Zoo", "Arte", "Casa"})

    [group] = AnalyticsService(uow).categories(Period())

    assert [(c.category_id, c.category_name) for c in group.categories] == [
        (ids["Casa"], "Casa"),
        (ids["Arte"], "Arte"),
        (ids["Zoo"], "Zoo"),
        (ids[default_name], default_name),
    ]


def test_categories_respects_closed_period_sea24_sea57(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """SEA-24: intervalo fechado; SEA-57: sem período = todo o histórico."""
    _seed(
        uow_factory,
        [
            Row("-10.00", day=date(2025, 12, 31)),
            Row("-20.00", day=date(2026, 1, 1)),
            Row("-40.00", day=date(2026, 1, 31)),
            Row("-80.00", day=date(2026, 2, 1)),
        ],
    )
    service = AnalyticsService(uow)

    [january] = service.categories(Period(date(2026, 1, 1), date(2026, 1, 31)))
    [everything] = service.categories(Period())

    assert january.total == _d("60.00")
    assert everything.total == _d("150.00")


# ---------------------------------------------------------------- monthly


def test_monthly_fills_gaps_per_currency_sea61_sea62(
    uow_factory: UoWFactory, uow: UnitOfWork
) -> None:
    """SEA-61, SEA-62, P-11: mesma faixa de meses para todas as moedas, sem somar."""
    _seed(
        uow_factory,
        [
            Row("-10.00", day=date(2026, 1, 10)),
            Row("-15.00", day=date(2026, 1, 20)),
            Row("-30.00", "USD", day=date(2026, 3, 5)),
            Row("100.00", day=date(2026, 4, 5)),
        ],
    )

    result = AnalyticsService(uow).monthly(Period())

    assert [s.currency for s in result] == ["BRL", "USD"]
    brl, usd = result
    assert [(m.month, m.total, m.count) for m in brl.months] == [
        ("2026-01", _d("25.00"), 2),
        ("2026-02", _d("0.00"), 0),
        ("2026-03", _d("0.00"), 0),
    ]
    assert [(m.month, m.total, m.count) for m in usd.months] == [
        ("2026-01", _d("0.00"), 0),
        ("2026-02", _d("0.00"), 0),
        ("2026-03", _d("30.00"), 1),
    ]


def test_monthly_uses_period_bounds(uow_factory: UoWFactory, uow: UnitOfWork) -> None:
    """SEA-61, P-11: com período, o intervalo de meses vem dele e exclui o que está fora."""
    _seed(
        uow_factory,
        [Row("-10.00", day=date(2026, 2, 10)), Row("-99.00", day=date(2026, 6, 10))],
    )

    [series] = AnalyticsService(uow).monthly(Period(date(2026, 1, 1), date(2026, 3, 31)))

    assert [(m.month, m.total) for m in series.months] == [
        ("2026-01", _d("0.00")),
        ("2026-02", _d("10.00")),
        ("2026-03", _d("0.00")),
    ]

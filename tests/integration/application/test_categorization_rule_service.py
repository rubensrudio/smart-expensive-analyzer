"""CategorizationRuleService (CT-18). Requisitos: SEA-18, SEA-48, SEA-49, SEA-50, SEA-64."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.application.services.categorization_rule_service import CategorizationRuleService
from app.core.errors import RuleCategoryNotFoundError, RuleNotFoundError
from app.domain.entities import CategorizationRule, NewTransaction, TransactionType
from app.domain.ports import UnitOfWork

MISSING_ID = 999_999


@pytest.fixture
def service(uow: UnitOfWork) -> CategorizationRuleService:
    return CategorizationRuleService(uow)


@pytest.fixture
def default_category_id(uow: UnitOfWork) -> int:
    return uow.categories.get_default().id


@pytest.fixture
def transport_id(uow: UnitOfWork) -> int:
    category = uow.categories.add("Transporte")
    uow.commit()
    return category.id


def _rules_in_fresh_uow(uow_factory: Callable[[], UnitOfWork]) -> list[CategorizationRule]:
    with uow_factory() as other:
        return other.rules.list_all()


# --- create -----------------------------------------------------------------------------


def test_create_persists_normalized_keyword_and_commits(
    service: CategorizationRuleService,
    transport_id: int,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    rule = service.create("  uber   trip ", transport_id, 10)

    assert rule.keyword == "uber trip"
    assert rule.category_id == transport_id
    assert rule.priority == 10
    assert rule.created_at is not None
    assert _rules_in_fresh_uow(uow_factory) == [rule]


def test_create_accepts_negative_priority(
    service: CategorizationRuleService, transport_id: int
) -> None:
    rule = service.create("uber", transport_id, -5)

    assert rule.priority == -5


def test_create_with_missing_category_raises_and_persists_nothing(
    service: CategorizationRuleService, uow_factory: Callable[[], UnitOfWork]
) -> None:
    with pytest.raises(RuleCategoryNotFoundError):
        service.create("uber", MISSING_ID, 1)

    assert _rules_in_fresh_uow(uow_factory) == []


@pytest.mark.parametrize("keyword", ["", "   ", "\t\n"])
def test_create_blank_keyword_raises_value_error(
    service: CategorizationRuleService,
    transport_id: int,
    uow_factory: Callable[[], UnitOfWork],
    keyword: str,
) -> None:
    with pytest.raises(ValueError):
        service.create(keyword, transport_id, 1)

    assert _rules_in_fresh_uow(uow_factory) == []


# --- get / list -------------------------------------------------------------------------


def test_get_returns_rule(service: CategorizationRuleService, transport_id: int) -> None:
    rule = service.create("uber", transport_id, 1)

    assert service.get(rule.id) == rule


def test_get_missing_raises_not_found(service: CategorizationRuleService) -> None:
    with pytest.raises(RuleNotFoundError):
        service.get(MISSING_ID)


def test_list_orders_by_priority_then_creation(
    service: CategorizationRuleService, transport_id: int, default_category_id: int
) -> None:
    second = service.create("b", transport_id, 5)
    first = service.create("a", default_category_id, 1)
    third = service.create("c", transport_id, 5)

    assert service.list() == [first, second, third]


# --- update -----------------------------------------------------------------------------


def test_update_replaces_fields_and_commits(
    service: CategorizationRuleService,
    transport_id: int,
    default_category_id: int,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    rule = service.create("uber", transport_id, 1)

    updated = service.update(rule.id, "  99   taxi ", default_category_id, -3)

    assert updated.id == rule.id
    assert updated.keyword == "99 taxi"
    assert updated.category_id == default_category_id
    assert updated.priority == -3
    assert _rules_in_fresh_uow(uow_factory) == [updated]


def test_update_missing_rule_raises_not_found(
    service: CategorizationRuleService, transport_id: int
) -> None:
    with pytest.raises(RuleNotFoundError):
        service.update(MISSING_ID, "uber", transport_id, 1)


def test_update_with_missing_category_raises_and_keeps_rule(
    service: CategorizationRuleService,
    transport_id: int,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    rule = service.create("uber", transport_id, 1)

    with pytest.raises(RuleCategoryNotFoundError):
        service.update(rule.id, "outro", MISSING_ID, 2)

    assert _rules_in_fresh_uow(uow_factory) == [rule]


def test_update_blank_keyword_raises_value_error_and_keeps_rule(
    service: CategorizationRuleService,
    transport_id: int,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    rule = service.create("uber", transport_id, 1)

    with pytest.raises(ValueError):
        service.update(rule.id, "   ", transport_id, 2)

    assert _rules_in_fresh_uow(uow_factory) == [rule]


# --- delete -----------------------------------------------------------------------------


def test_delete_removes_rule_and_commits(
    service: CategorizationRuleService,
    transport_id: int,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    rule = service.create("uber", transport_id, 1)

    service.delete(rule.id)

    assert _rules_in_fresh_uow(uow_factory) == []
    with pytest.raises(RuleNotFoundError):
        service.get(rule.id)


def test_delete_missing_raises_not_found(service: CategorizationRuleService) -> None:
    with pytest.raises(RuleNotFoundError):
        service.delete(MISSING_ID)


# --- SEA-64 -----------------------------------------------------------------------------


def _seed_transactions(uow: UnitOfWork, category_id: int) -> dict[int, int]:
    import_id = uow.imports.create_processing("t.csv", "a" * 64, datetime.now(UTC))
    items = [
        NewTransaction(
            date=date(2026, 1, day),
            description=f"UBER TRIP {day}",
            merchant="Uber",
            amount=Decimal("-20.00"),
            currency="BRL",
            type=TransactionType.EXPENSE,
            category_id=category_id,
            import_id=import_id,
            dedup_key=f"{day:064d}",
        )
        for day in (1, 2, 3)
    ]
    assert uow.transactions.insert_ignoring_duplicates(items) == 3
    uow.commit()
    return {t.id: t.category_id for t in uow.transactions.list_all_for_categorization()}


def _categories_in_fresh_uow(uow_factory: Callable[[], UnitOfWork]) -> dict[int, int]:
    with uow_factory() as other:
        return {t.id: t.category_id for t in other.transactions.list_all_for_categorization()}


def test_rule_writes_do_not_change_persisted_transactions(
    uow: UnitOfWork,
    service: CategorizationRuleService,
    transport_id: int,
    default_category_id: int,
    uow_factory: Callable[[], UnitOfWork],
) -> None:
    before = _seed_transactions(uow, default_category_id)
    assert set(before.values()) == {default_category_id}

    rule = service.create("uber", transport_id, 1)
    assert _categories_in_fresh_uow(uow_factory) == before

    service.update(rule.id, "uber trip", transport_id, 0)
    assert _categories_in_fresh_uow(uow_factory) == before

    service.delete(rule.id)
    assert _categories_in_fresh_uow(uow_factory) == before

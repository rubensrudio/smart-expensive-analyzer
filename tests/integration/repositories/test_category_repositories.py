"""Repositórios SQLAlchemy de Category e CategorizationRule (CT-8).

Requisitos: SEA-47, SEA-48, SEA-51, SEA-53.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.domain.entities import CategorizationRule, Category
from app.infrastructure.db.models import CategorizationRuleModel, CategoryModel
from app.infrastructure.db.repositories.categories import SqlAlchemyCategoryRepository
from app.infrastructure.db.repositories.categorization_rules import (
    SqlAlchemyCategorizationRuleRepository,
)

DEFAULT_NAME = "Não categorizada"
MISSING_ID = 999_999


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s
        s.rollback()


@pytest.fixture
def categories(session: Session) -> SqlAlchemyCategoryRepository:
    return SqlAlchemyCategoryRepository(session)


@pytest.fixture
def rules(session: Session) -> SqlAlchemyCategorizationRuleRepository:
    return SqlAlchemyCategorizationRuleRepository(session)


# --- Category -------------------------------------------------------------------------


def test_get_default_returns_seeded_category(categories: SqlAlchemyCategoryRepository) -> None:
    default = categories.get_default()

    assert isinstance(default, Category)
    assert default.name == DEFAULT_NAME
    assert default.is_default is True


def test_get_by_name_ci_ignores_case_and_surrounding_spaces(
    categories: SqlAlchemyCategoryRepository,
) -> None:
    found = categories.get_by_name_ci("  não CATEGORIZADA ")

    assert found is not None
    assert found == categories.get_default()


def test_get_by_name_ci_returns_none_when_absent(
    categories: SqlAlchemyCategoryRepository,
) -> None:
    assert categories.get_by_name_ci("Inexistente") is None


def test_add_returns_entity_and_get_finds_it(categories: SqlAlchemyCategoryRepository) -> None:
    created = categories.add("Mercado")

    assert created.id > 0
    assert created.name == "Mercado"
    assert created.is_default is False
    assert categories.get(created.id) == created


def test_get_returns_none_for_missing_id(categories: SqlAlchemyCategoryRepository) -> None:
    assert categories.get(MISSING_ID) is None


def test_list_all_orders_by_name(categories: SqlAlchemyCategoryRepository) -> None:
    categories.add("Transporte")
    categories.add("Alimentação")

    names = [c.name for c in categories.list_all()]

    assert names == ["Alimentação", DEFAULT_NAME, "Transporte"]


def test_add_duplicate_name_case_insensitive_propagates_integrity_error(
    categories: SqlAlchemyCategoryRepository,
) -> None:
    categories.add("Lazer")

    with pytest.raises(IntegrityError):
        categories.add("LAZER")


def test_category_repository_does_not_commit(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as s:
        SqlAlchemyCategoryRepository(s).add("Sem commit")
        s.rollback()

    with session_factory() as other:
        count = other.scalar(
            select(func.count())
            .select_from(CategoryModel)
            .where(CategoryModel.name == "Sem commit")
        )
    assert count == 0


# --- CategorizationRule ---------------------------------------------------------------


def test_rule_add_returns_entity_and_get_finds_it(
    categories: SqlAlchemyCategoryRepository, rules: SqlAlchemyCategorizationRuleRepository
) -> None:
    category = categories.add("Streaming")

    created = rules.add("netflix", category.id, 1)

    assert isinstance(created, CategorizationRule)
    assert created.id > 0
    assert (created.keyword, created.category_id, created.priority) == ("netflix", category.id, 1)
    assert created.created_at is not None
    assert rules.get(created.id) == created


def test_rule_get_returns_none_for_missing_id(
    rules: SqlAlchemyCategorizationRuleRepository,
) -> None:
    assert rules.get(MISSING_ID) is None


def test_rule_list_all_orders_by_priority_then_created_at_then_id(
    session_factory: sessionmaker[Session],
) -> None:
    # Cada regra em sua transação: `created_at` (now()) fica distinto e crescente.
    ids: list[int] = []
    with session_factory() as s:
        default_id = SqlAlchemyCategoryRepository(s).get_default().id
    for priority in (2, 1, 1):
        with session_factory() as s:
            ids.append(SqlAlchemyCategorizationRuleRepository(s).add("kw", default_id, priority).id)
            s.commit()
    p2, p1_first, p1_second = ids

    with session_factory() as s:
        listed = [r.id for r in SqlAlchemyCategorizationRuleRepository(s).list_all()]

    assert listed == [p1_first, p1_second, p2]


def test_rule_list_all_breaks_created_at_tie_by_id(
    categories: SqlAlchemyCategoryRepository, rules: SqlAlchemyCategorizationRuleRepository
) -> None:
    # Mesma transação: now() é igual para todas, o desempate é o id.
    default_id = categories.get_default().id
    first = rules.add("a", default_id, 5)
    second = rules.add("b", default_id, 5)

    assert [r.id for r in rules.list_all()] == [first.id, second.id]


def test_rule_update_changes_fields(
    categories: SqlAlchemyCategoryRepository, rules: SqlAlchemyCategorizationRuleRepository
) -> None:
    default_id = categories.get_default().id
    other = categories.add("Saúde")
    created = rules.add("farmacia", default_id, 3)

    updated = rules.update(created.id, "drogaria", other.id, 1)

    assert updated is not None
    assert (updated.id, updated.keyword, updated.category_id, updated.priority) == (
        created.id,
        "drogaria",
        other.id,
        1,
    )
    assert updated.created_at == created.created_at
    assert rules.get(created.id) == updated


def test_rule_update_missing_id_returns_none(
    categories: SqlAlchemyCategoryRepository, rules: SqlAlchemyCategorizationRuleRepository
) -> None:
    assert rules.update(MISSING_ID, "x", categories.get_default().id, 1) is None


def test_rule_delete_removes_and_returns_true(
    categories: SqlAlchemyCategoryRepository, rules: SqlAlchemyCategorizationRuleRepository
) -> None:
    created = rules.add("uber", categories.get_default().id, 1)

    assert rules.delete(created.id) is True
    assert rules.get(created.id) is None


def test_rule_delete_missing_id_returns_false(
    rules: SqlAlchemyCategorizationRuleRepository,
) -> None:
    assert rules.delete(MISSING_ID) is False


def test_rule_repository_does_not_commit(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as s:
        default_id = SqlAlchemyCategoryRepository(s).get_default().id
        SqlAlchemyCategorizationRuleRepository(s).add("sem-commit", default_id, 1)
        s.rollback()

    with session_factory() as other:
        count = other.scalar(select(func.count()).select_from(CategorizationRuleModel))
    assert count == 0

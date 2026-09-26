"""CategoryService (CT-18). Requisitos: SEA-15, SEA-16, SEA-51, SEA-53."""

from collections.abc import Callable

import pytest

from app.application.services.category_service import CategoryService
from app.core.errors import CategoryAlreadyExistsError, CategoryNameRequiredError
from app.domain.entities import Category
from app.domain.ports import UnitOfWork

DEFAULT_NAME = "Não categorizada"


@pytest.fixture
def service(uow: UnitOfWork) -> CategoryService:
    return CategoryService(uow)


def _names_in_fresh_uow(uow_factory: Callable[[], UnitOfWork]) -> list[str]:
    with uow_factory() as other:
        return [c.name for c in other.categories.list_all()]


def test_create_persists_and_commits(
    service: CategoryService, uow_factory: Callable[[], UnitOfWork]
) -> None:
    created = service.create("Transporte")

    assert isinstance(created, Category)
    assert created.name == "Transporte"
    assert created.is_default is False
    # Visível em outra sessão: houve commit.
    assert "Transporte" in _names_in_fresh_uow(uow_factory)


def test_create_normalizes_whitespace(service: CategoryService) -> None:
    created = service.create("  Casa   e \t Moradia  ")

    assert created.name == "Casa e Moradia"


@pytest.mark.parametrize("name", [None, "", "   ", "\t\n "])
def test_create_blank_or_missing_name_raises_required(
    service: CategoryService, uow_factory: Callable[[], UnitOfWork], name: str | None
) -> None:
    with pytest.raises(CategoryNameRequiredError):
        service.create(name)

    assert _names_in_fresh_uow(uow_factory) == [DEFAULT_NAME]


def test_create_default_name_case_insensitive_raises_already_exists(
    service: CategoryService,
) -> None:
    with pytest.raises(CategoryAlreadyExistsError):
        service.create("não categorizada")


def test_create_same_name_twice_raises_already_exists(
    service: CategoryService, uow_factory: Callable[[], UnitOfWork]
) -> None:
    service.create("Transporte")

    with pytest.raises(CategoryAlreadyExistsError):
        service.create("Transporte")

    assert _names_in_fresh_uow(uow_factory).count("Transporte") == 1


def test_create_duplicate_ignores_case_and_edge_spaces(service: CategoryService) -> None:
    service.create("Transporte")

    with pytest.raises(CategoryAlreadyExistsError):
        service.create("  TRANSPORTE ")


def test_create_race_integrity_error_translated_and_uow_reusable(
    uow: UnitOfWork,
    service: CategoryService,
    uow_factory: Callable[[], UnitOfWork],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service.create("Mercado")
    # Simula a corrida: a checagem prévia não vê a linha concorrente.
    monkeypatch.setattr(uow.categories, "get_by_name_ci", lambda name: None)

    with pytest.raises(CategoryAlreadyExistsError):
        service.create("MERCADO")

    # A sessão foi desfeita e continua utilizável.
    created = service.create("Lazer")
    assert created.name == "Lazer"
    assert sorted(_names_in_fresh_uow(uow_factory)) == sorted([DEFAULT_NAME, "Mercado", "Lazer"])


def test_list_includes_default_category(service: CategoryService) -> None:
    service.create("Transporte")

    categories = service.list()

    names = [c.name for c in categories]
    assert DEFAULT_NAME in names
    assert "Transporte" in names
    assert names == sorted(names)

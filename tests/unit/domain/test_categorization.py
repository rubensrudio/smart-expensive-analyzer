from datetime import UTC, datetime, timedelta

from app.domain.categorization import RuleMatcher
from app.domain.entities import CategorizationRule

DEFAULT_CATEGORY_ID = 1
BASE_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _rule(
    rule_id: int,
    keyword: str,
    category_id: int,
    priority: int = 10,
    created_offset_s: int = 0,
) -> CategorizationRule:
    return CategorizationRule(
        id=rule_id,
        keyword=keyword,
        category_id=category_id,
        priority=priority,
        created_at=BASE_TIME + timedelta(seconds=created_offset_s),
    )


def test_keyword_without_accent_matches_accented_description() -> None:
    matcher = RuleMatcher([_rule(1, "acai", 20)], DEFAULT_CATEGORY_ID)
    assert matcher.match("AÇAÍ DA PRAIA", "") == 20


def test_keyword_matches_merchant_ignoring_case() -> None:
    matcher = RuleMatcher([_rule(1, "uber", 30)], DEFAULT_CATEGORY_ID)
    assert matcher.match("PAGAMENTO 123", "Uber Trip") == 30


def test_accented_keyword_matches_unaccented_description() -> None:
    matcher = RuleMatcher([_rule(1, "Padaria São", 40)], DEFAULT_CATEGORY_ID)
    assert matcher.match("padaria sao joao", "") == 40


def test_lowest_priority_number_wins() -> None:
    rules = [_rule(1, "uber", 50, priority=5), _rule(2, "trip", 60, priority=1)]
    matcher = RuleMatcher(rules, DEFAULT_CATEGORY_ID)
    assert matcher.match("UBER TRIP", "") == 60


def test_same_priority_earliest_created_at_wins() -> None:
    rules = [
        _rule(1, "uber", 50, priority=3, created_offset_s=100),
        _rule(2, "trip", 60, priority=3, created_offset_s=0),
    ]
    matcher = RuleMatcher(rules, DEFAULT_CATEGORY_ID)
    assert matcher.match("UBER TRIP", "") == 60


def test_same_priority_and_created_at_lowest_id_wins() -> None:
    rules = [_rule(9, "uber", 50, priority=3), _rule(4, "trip", 60, priority=3)]
    matcher = RuleMatcher(rules, DEFAULT_CATEGORY_ID)
    assert matcher.match("UBER TRIP", "") == 60


def test_winner_does_not_depend_on_input_order() -> None:
    rules = [
        _rule(1, "uber", 50, priority=5),
        _rule(2, "trip", 60, priority=1),
        _rule(3, "u", 70, priority=2),
    ]
    forward = RuleMatcher(rules, DEFAULT_CATEGORY_ID)
    backward = RuleMatcher(list(reversed(rules)), DEFAULT_CATEGORY_ID)
    assert forward.match("UBER TRIP", "") == backward.match("UBER TRIP", "") == 60


def test_no_matching_rule_returns_default_category() -> None:
    matcher = RuleMatcher([_rule(1, "uber", 30)], DEFAULT_CATEGORY_ID)
    assert matcher.match("PADARIA", "Padaria São João") == DEFAULT_CATEGORY_ID


def test_empty_rule_set_returns_default_category() -> None:
    matcher = RuleMatcher([], DEFAULT_CATEGORY_ID)
    assert matcher.match("UBER TRIP", "Uber") == DEFAULT_CATEGORY_ID


def test_same_input_twice_gives_same_result() -> None:
    rules = [_rule(1, "uber", 30, priority=2), _rule(2, "padaria", 40, priority=1)]
    matcher = RuleMatcher(rules, DEFAULT_CATEGORY_ID)
    first = [matcher.match("UBER TRIP", ""), matcher.match("CINEMA", "")]
    second = [matcher.match("UBER TRIP", ""), matcher.match("CINEMA", "")]
    assert first == second == [30, DEFAULT_CATEGORY_ID]


def test_blank_keyword_never_matches() -> None:
    matcher = RuleMatcher([_rule(1, "   ", 30), _rule(2, "", 31)], DEFAULT_CATEGORY_ID)
    assert matcher.match("QUALQUER COISA", "Loja") == DEFAULT_CATEGORY_ID


def test_matcher_does_not_mutate_input_rules() -> None:
    rules = [_rule(1, "uber", 50, priority=5), _rule(2, "trip", 60, priority=1)]
    snapshot = list(rules)
    RuleMatcher(rules, DEFAULT_CATEGORY_ID)
    assert rules == snapshot

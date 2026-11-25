"""Input schemas of the discount rules: what a caller may send, and the 422 per field of what it may not.

Coherence between fields that an edit may send alone (a rule's type and its value, a scope and its
target, a range of days) is the service's (``schemas.rules.rule_problems``, tested here as a pure function).
"""

import datetime as dt
import uuid
from decimal import Decimal

from apps.pricing.schemas.rules import RuleIn, RuleListIn, RulePatchIn, RuleRefIn, rule_problems

from .test_schemas_fields import errors


def test_a_rule_needs_code_name_and_type():
    rule = RuleIn(code="TEN", name="Ten off", rule_type="percent", percent="10")
    assert (rule.applies_to, rule.priority, rule.tiers, rule.percent) == ("all", 100, [], Decimal("10"))
    assert set(errors(RuleIn, code="", name="")) == {"code", "name", "rule_type"}
    assert "rule_type" in errors(RuleIn, code="c", name="n", rule_type="coupon")
    assert "percent" in errors(RuleIn, code="c", name="n", rule_type="percent", percent="100.5")
    assert "percent" in errors(RuleIn, code="c", name="n", rule_type="percent", percent="0")
    assert "amount" in errors(RuleIn, code="c", name="n", rule_type="fixed", amount=0)
    assert "buy_quantity" in errors(RuleIn, code="c", name="n", rule_type="buy_x_get_y", buy_quantity=0)
    assert "tiers" in errors(RuleIn, code="c", name="n", rule_type="tiered", tiers=[{"min_quantity": "1", "percent": "5"}] * 11)
    assert "tiers.0.percent" in errors(RuleIn, code="c", name="n", rule_type="tiered", tiers=[{"min_quantity": "1", "percent": "0"}])
    assert "applies_to" in errors(RuleIn, code="c", name="n", rule_type="percent", percent="5", applies_to="customer_segment")


def test_a_rule_is_named_by_id_code_or_name():
    assert RuleRefIn(rule=" 2x1 ").rule == "2x1"
    assert errors(RuleRefIn) == {"rule": "value_error"}
    assert RulePatchIn(rule="2x1", priority=5).model_fields_set == {"rule", "priority"}


def test_the_rules_are_active_by_name_by_default():
    params = RuleListIn()
    assert (params.status, params.sort, params.dir) == ("active", "name", "asc")
    assert "sort" in errors(RuleListIn, sort="value")


def test_rule_problems_ask_for_the_value_of_each_type_and_refuse_another_types():
    assert rule_problems({"rule_type": "percent", "percent": Decimal("10"), "applies_to": "all"}) == {}
    assert set(rule_problems({"rule_type": "percent", "applies_to": "all"})) == {"percent"}
    assert set(rule_problems({"rule_type": "fixed", "applies_to": "all"})) == {"amount"}
    assert set(rule_problems({"rule_type": "buy_x_get_y", "buy_quantity": 2, "applies_to": "all"})) == {"get_quantity"}
    assert set(rule_problems({"rule_type": "tiered", "tiers": [], "applies_to": "all"})) == {"tiers"}
    # A value of another type was sent on purpose: said, never silently dropped.
    assert set(rule_problems({"rule_type": "percent", "percent": Decimal("5"), "amount": 50, "applies_to": "all"})) == {
        "amount"
    }


def test_rule_problems_want_tiers_rising():
    tiers = [{"min_quantity": Decimal("6"), "percent": Decimal("15")}, {"min_quantity": Decimal("3"), "percent": Decimal("10")}]
    assert set(rule_problems({"rule_type": "tiered", "tiers": tiers, "applies_to": "all"})) == {"tiers"}
    same = [{"min_quantity": Decimal("3"), "percent": Decimal("10")}, {"min_quantity": Decimal("3"), "percent": Decimal("15")}]
    assert set(rule_problems({"rule_type": "tiered", "tiers": same, "applies_to": "all"})) == {"tiers"}


def test_rule_problems_want_the_target_of_the_scope_and_no_other():
    base = {"rule_type": "percent", "percent": Decimal("5")}
    assert set(rule_problems({**base, "applies_to": "category"})) == {"category"}
    assert set(rule_problems({**base, "applies_to": "product"})) == {"product"}
    assert set(rule_problems({**base, "applies_to": "service"})) == {"service"}
    assert rule_problems({**base, "applies_to": "product", "product_id": uuid.uuid7()}) == {}
    assert set(rule_problems({**base, "applies_to": "all", "product_id": uuid.uuid7()})) == {"product"}


def test_rule_problems_want_the_days_in_order():
    base = {"rule_type": "percent", "percent": Decimal("5"), "applies_to": "all"}
    assert set(rule_problems({**base, "valid_from": dt.date(2026, 7, 2), "valid_until": dt.date(2026, 7, 1)})) == {
        "valid_until"
    }

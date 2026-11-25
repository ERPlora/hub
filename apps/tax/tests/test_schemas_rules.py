"""The tax rules: a new one, several at once, which one is named, and the list's filters and sort."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.utils import translation

from apps.tax.schemas.rules import RuleBulkIn, RuleEndIn, RuleIn, RuleListIn, RuleRefIn, RuleStatusIn

from .schema_checks import RULE, invalid_fields, message

ID = uuid.uuid7()


def test_rule_defaults():
    assert RuleIn(**RULE).model_dump() == {
        "country_code": "ES",
        "region_code": None,
        "tax_category_key": "product.generic",
        "operation_class": "subject",
        "rate_pct": Decimal("21"),
        # No family: the one of the rule's territory (TAX-F11), VAT for the whole of Spain.
        "tax_type": None,
        "exempt_reason": None,
        "regime_key": None,
        "valid_from": None,
        "valid_to": None,
        "parent_id": None,
        "component_label": None,
    }


@pytest.mark.parametrize("rate", ["-0.01", "100.01", "500", "5.205"])
def test_the_rate_is_0_to_100_with_two_decimals(rate):
    assert invalid_fields(RuleIn, **{**RULE, "rate_pct": rate}) == {"rate_pct"}


@pytest.mark.parametrize("rate", ["0", "5.2", "100"])
def test_valid_rates(rate):
    assert RuleIn(**{**RULE, "rate_pct": rate}).rate_pct == Decimal(rate)


@pytest.mark.parametrize(
    "operation_class",
    ["subject_reverse", "exempt", "not_subject", "not_subject_location"],
)
def test_a_class_that_charges_no_tax_carries_no_rate(operation_class):
    # The till would charge it and the invoice would refuse to seal the sale.
    with translation.override("en"):
        assert message(RuleIn, **{**RULE, "operation_class": operation_class}) == (
            "This operation charges no tax: its rate must be 0 %."
        )
    assert (
        RuleIn(**{**RULE, "operation_class": operation_class, "rate_pct": "0"}).rate_pct
        == 0
    )


def test_the_qualification_is_a_closed_list():
    # A free value would reach the tax agency as a qualification that does not exist.
    assert invalid_fields(RuleIn, **{**RULE, "operation_class": "casi_exento"}) == {
        "operation_class"
    }
    assert invalid_fields(RuleIn, **{**RULE, "tax_type": "gst"}) == {"tax_type"}


def test_the_validity_range_runs_forwards():
    with translation.override("en"):
        assert message(
            RuleIn, **RULE, valid_from="2026-02-01", valid_to="2026-01-31"
        ) == ("The last day cannot be before the first one.")
    same_day = RuleIn(**RULE, valid_from="2026-01-31", valid_to="2026-01-31")
    assert same_day.valid_from == same_day.valid_to == date(2026, 1, 31)


def test_codes_of_the_jurisdiction_are_short_and_in_capitals():
    rule = RuleIn(
        **{**RULE, "rate_pct": "0", "operation_class": "exempt"},
        exempt_reason=" e1 ",
        regime_key="01",
    )
    assert (rule.exempt_reason, rule.regime_key) == ("E1", "01")
    assert invalid_fields(RuleIn, **RULE, exempt_reason="x" * 11) == {"exempt_reason"}
    assert invalid_fields(RuleIn, **RULE, component_label="x" * 121) == {
        "component_label"
    }


def test_bulk_takes_1_to_100_root_rules():
    assert len(RuleBulkIn(rules=[RULE] * 100).rules) == 100
    assert invalid_fields(RuleBulkIn, rules=[]) == {"rules"}
    assert invalid_fields(RuleBulkIn, rules=[RULE] * 101) == {"rules"}


def test_a_bulk_row_is_checked_like_a_single_rule_and_names_its_position():
    rows = [RULE, {**RULE, "operation_class": "exempt"}, {**RULE, "country_code": "ZZ"}]
    assert invalid_fields(RuleBulkIn, rules=rows) == {
        "rules.1.rate_pct",
        "rules.2.country_code",
    }


def test_a_bulk_row_cannot_be_a_component():
    # Components are created one by one: they need their root already saved.
    assert invalid_fields(RuleBulkIn, rules=[{**RULE, "parent_id": str(ID)}]) == {
        "rules.0.parent_id"
    }


def test_a_rule_is_named_by_its_id_or_by_its_slot():
    assert RuleRefIn(id=str(ID)).id == ID
    by_slot = RuleRefIn(
        country_code="es", tax_category_key="comida", region_code="ES-CN"
    )
    assert (
        by_slot.id,
        by_slot.country_code,
        by_slot.region_code,
        by_slot.tax_category_key,
    ) == (
        None,
        "ES",
        "ES-CN",
        "comida",
    )
    with translation.override("en"):
        assert (
            message(RuleRefIn)
            == "Say which rule: its id, or its country and its category."
        )
        assert (
            message(RuleRefIn, country_code="ES")
            == "Say which rule: its id, or its country and its category."
        )
    assert invalid_fields(RuleRefIn, id="nope") == {"id"}


def test_rule_end():
    assert RuleEndIn(id=str(ID), valid_to="2026-12-31").valid_to == date(2026, 12, 31)
    assert (
        RuleEndIn(
            country_code="ES", tax_category_key="product.generic", valid_to="2026-12-31"
        ).id
        is None
    )
    assert invalid_fields(RuleEndIn, id=str(ID)) == {"valid_to"}


def test_rule_list_filters_and_sort():
    assert RuleListIn().model_dump() == {
        "limit": 50,
        "offset": 0,
        "search": None,
        "country_code": None,
        "region_code": None,
        "tax_category_key": None,
        "tax_type": None,
        "operation_class": None,
        "regime_key": None,
        "parent_id": None,
        "rate_min": None,
        "rate_max": None,
        "status": "active",
        "sort": "tax_category_key",
        "dir": "asc",
    }
    assert RuleListIn(status="all", country_code="pt").country_code == "PT"
    assert invalid_fields(RuleListIn, status="archived") == {"status"}
    assert invalid_fields(RuleListIn, sort="created_at") == {"sort"}
    assert invalid_fields(RuleListIn, dir="up") == {"dir"}
    assert RuleListIn(
        sort="rate_pct", dir="desc", rate_min="4", rate_max="10"
    ).rate_max == Decimal("10")


def test_rule_status_takes_an_optional_country():
    assert RuleStatusIn().country_code is None
    assert RuleStatusIn(country_code="pt").country_code == "PT"

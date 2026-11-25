"""What the tips app's inputs refuse before any operation runs: a 422 by field."""

import pydantic
import pytest

from apps.tip.schemas import SettingsPatchIn, TipAddIn, TipPatchIn

METHOD = "0190f0f0-0000-7000-8000-00000000000c"


@pytest.mark.parametrize(
    "data",
    [
        {"amount": 100, "method": "card"},
        {"amount": 100, "pool": True, "sale": "20261114-0007"},
        {"amount": 100, "pool": True, "method": "card"},
        {"amount": 100, "sale": "20261114-0007"},
        {"amount": 0, "pool": True},
        {"amount": -5, "pool": True},
    ],
)
def test_a_tip_names_its_sale_and_its_payment_method_or_goes_to_the_pool_in_cash_with_a_positive_amount(data):
    with pytest.raises(pydantic.ValidationError):
        TipAddIn.model_validate(data)


def test_a_change_needs_its_reason_and_something_to_change():
    tip = "0190f0f0-0000-7000-8000-000000000000"
    for data in ({"id": tip, "amount": 100, "reason": "  "}, {"id": tip, "reason": "typo"}, {"amount": 100, "reason": "typo"}):
        with pytest.raises(pydantic.ValidationError):
            TipPatchIn.model_validate(data)


@pytest.mark.parametrize(
    "suggestions",
    [
        [{"kind": "percent", "value": 0}, {"kind": "percent", "value": 5}, {"kind": "percent", "value": 10}],
        [{"kind": "percent", "value": 101}, {"kind": "percent", "value": 5}, {"kind": "percent", "value": 10}],
        [{"kind": "amount", "value": -100}, {"kind": "percent", "value": 5}, {"kind": "percent", "value": 10}],
        [{"kind": "percent", "value": 5}, {"kind": "percent", "value": 10}],
    ],
)
def test_a_suggestion_empty_zero_negative_or_over_100_percent_is_refused(suggestions):
    with pytest.raises(pydantic.ValidationError):
        SettingsPatchIn.model_validate({"methods": [{"method_id": METHOD, "suggestions": suggestions}]})


def test_the_same_suggestion_twice_in_a_method_is_said_on_its_field():
    twice = [{"kind": "percent", "value": 5}, {"kind": "percent", "value": 5}, {"kind": "percent", "value": 10}]
    with pytest.raises(pydantic.ValidationError) as refused:
        SettingsPatchIn.model_validate({"methods": [{"method_id": METHOD, "suggestions": twice}]})
    assert "That suggestion is already there." in str(refused.value)



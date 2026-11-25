"""The tip settings (TIP-F01): off from the factory, three suggestions per payment method of Sales (3 %, 5 % and 10 % by
default, each a percentage or an amount), which one comes chosen and whether another amount is allowed."""

import pydantic
import pytest
from live.errors import PermissionDenied
from live.models import OutboxEvent

from apps.sale.models import PaymentMethod
from apps.tip.schemas import SettingsPatchIn

from .conftest import HUB_DB, ctx_for, run

pytestmark = HUB_DB

FACTORY = [{"kind": "percent", "value": 3}, {"kind": "percent", "value": 5}, {"kind": "percent", "value": 10}]


def settings(ctx=None):
    return run("tip.settings.get", {}, ctx)


def by_method(read) -> dict[str, list[dict]]:
    return {row.method_name: [s.model_dump() for s in row.suggestions] for row in read.methods}


def card():
    return PaymentMethod.objects.get(type="card", is_active=True)


def test_from_the_factory_tips_are_off_with_3_5_and_10_percent_for_every_active_payment_method():
    read = settings()
    assert (read.enabled, read.allow_custom, read.preselected) == (False, True, 0)
    active = list(PaymentMethod.objects.filter(is_active=True).order_by("sort_order", "name", "id"))
    assert [(row.method_id, row.method_type) for row in read.methods] == [(m.id, m.type) for m in active]
    assert all(suggestions == FACTORY for suggestions in by_method(read).values())


def test_saving_turns_them_on_and_sets_the_suggestions_of_a_method():
    mine = [{"kind": "amount", "value": 100}, {"kind": "percent", "value": 5}, {"kind": "percent", "value": 10}]
    saved = run(
        "tip.settings.update",
        {
            "enabled": True,
            "allow_custom": False,
            "preselected": 2,
            "methods": [{"method_id": str(card().id), "suggestions": mine}],
        },
    )
    assert (saved.enabled, saved.allow_custom, saved.preselected) == (True, False, 2)
    assert by_method(saved)["Card"] == mine
    assert by_method(saved)["Cash"] == FACTORY
    assert settings() == saved
    event = OutboxEvent.objects.get(name="tip.settings.updated")
    assert event.payload == {"changed": ["allow_custom", "enabled", "methods", "preselected"]}


def test_saving_the_same_records_nothing():
    run("tip.settings.update", {"enabled": False, "methods": [{"method_id": str(card().id), "suggestions": FACTORY}]})
    assert not OutboxEvent.objects.filter(name="tip.settings.updated").exists()


def test_a_method_left_out_keeps_its_suggestions():
    mine = [{"kind": "amount", "value": 100}, {"kind": "amount", "value": 200}, {"kind": "amount", "value": 500}]
    run("tip.settings.update", {"methods": [{"method_id": str(card().id), "suggestions": mine}]})
    run("tip.settings.update", {"enabled": True})
    assert by_method(settings())["Card"] == mine


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
        SettingsPatchIn.model_validate({"methods": [{"method_id": str(card().id), "suggestions": suggestions}]})


def test_the_same_suggestion_twice_in_a_method_is_said_on_its_field():
    twice = [{"kind": "percent", "value": 5}, {"kind": "percent", "value": 5}, {"kind": "percent", "value": 10}]
    with pytest.raises(pydantic.ValidationError) as refused:
        SettingsPatchIn.model_validate({"methods": [{"method_id": str(card().id), "suggestions": twice}]})
    assert "That suggestion is already there." in str(refused.value)


def test_a_payment_method_that_is_not_available_is_refused():
    from live.errors import Conflict

    with pytest.raises(Conflict) as refused:
        run(
            "tip.settings.update",
            {"methods": [{"method_id": "0190f0f0-0000-7000-8000-000000000000", "suggestions": FACTORY}]},
        )
    assert refused.value.code == "sale.payment_method_not_available"


def test_everyone_reads_them_and_only_the_owner_and_the_admin_change_them():
    assert settings(ctx_for("hub_employee")).enabled is False
    for role in ("hub_manager", "hub_employee"):
        with pytest.raises(PermissionDenied):
            run("tip.settings.update", {"enabled": True}, ctx_for(role))
    assert run("tip.settings.update", {"enabled": True}, ctx_for("hub_owner")).enabled is True

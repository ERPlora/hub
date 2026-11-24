"""``sale.checkout.steps``: the steps the apps on in a business add to its charge, which the charge sheet mounts between
the amount and the tenders without knowing those apps (SALE-F39). The reference app stands for one that declares a
step, as Tips does with its tip."""

import pytest
from django.apps import apps
from live.context import OperationContext
from live.errors import PermissionDenied
from live.meta import CheckoutStep

from apps.sale.tests.conftest import DECLARED_STEP, HUB_DB, A, B, ctx_for, run
from base import activation
from base.tenancy.context import use_hub

pytestmark = HUB_DB


def steps(ctx: OperationContext | None = None) -> list[dict]:
    return run("sale.checkout.steps", {}, ctx).model_dump()["steps"]


def declare(monkeypatch, *declared: CheckoutStep) -> None:
    monkeypatch.setattr(apps.get_app_config("demo"), "checkout", list(declared))


def test_the_charge_has_no_step_while_no_app_on_adds_one():
    assert steps() == []


def test_the_step_an_app_on_declares_names_its_app_and_the_component_that_paints_it(a_step_at_the_charge):
    assert steps() == [DECLARED_STEP]


def test_the_steps_of_an_app_come_in_the_order_it_declares_them(monkeypatch):
    declare(monkeypatch, CheckoutStep(key="tip", component="TipStep"), CheckoutStep(key="round_up", component="RoundUp"))
    assert [step["key"] for step in steps()] == ["demo.tip", "demo.round_up"]


def test_an_app_turned_off_takes_its_step_away(a_step_at_the_charge, monkeypatch):
    monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"demo"}))
    assert steps() == []


def test_a_step_shows_only_to_whoever_has_its_permission(monkeypatch):
    declare(monkeypatch, CheckoutStep(key="tip", component="TipStep", permission="demo.manage"))
    assert steps(ctx_for("hub_admin")) == [DECLARED_STEP]
    assert steps(ctx_for("hub_employee")) == []


def test_only_whoever_charges_reads_the_steps_of_the_charge():
    with pytest.raises(PermissionDenied):
        steps(OperationContext(scope=A, actor="viewer", permissions=frozenset({"sale.view_sale"})))


def test_each_business_has_the_steps_of_its_own_apps(a_step_at_the_charge, monkeypatch, hub_b):
    monkeypatch.setattr(activation, "off_apps", lambda scope: frozenset({"demo"}) if scope == B else frozenset())
    assert steps() == [DECLARED_STEP]
    with use_hub(hub_b):
        assert steps(ctx_for(scope=B)) == []

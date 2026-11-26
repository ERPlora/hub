"""Live queries of the tips app: which events re-run which query, and a write in one business is announced to it
alone, after its COMMIT."""

from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for

from apps.flow.tests.test_relay import heard, listen
from base.tenancy.context import use_hub

from .conftest import HUB_DB_COMMITTED, A, B, ctx_for, run, with_cash

__all__ = ["listen"]

TIPS = ["tip.tip.added", "tip.tip.adjusted", "tip.tip.voided"]


def tip_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("tip.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_query_and_its_events():
    assert tip_queries() == {
        "tip.tip.list": TIPS,
        "tip.tip.get": TIPS,
        # Its payment methods are Sales': a new one or one switched off changes what can be set.
        "tip.settings.get": ["tip.settings.updated", "sale.payment_method.created", "sale.settings.updated"],
        # What the charge proposes is the settings' suggestions of a payment method.
        "tip.suggestion.get": ["tip.settings.updated", "sale.payment_method.created", "sale.settings.updated"],
    }


def test_every_live_query_has_a_permission():
    for name in tip_queries():
        assert get(name).permission, name


@HUB_DB_COMMITTED
def test_a_tip_recorded_in_business_b_is_announced_to_b_only(listen, hub_b):
    # Committed data of another test may have left a business without its cash method: each one is ready on its own.
    with_cash()
    with use_hub(hub_b):
        with_cash(ctx_for(scope=B))
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        run("cash_register.settings.update", {"enable_cash_register": False}, ctx_for(scope=B))
        heard(on_b)
        run("tip.tip.add", {"amount": 500, "pool": True}, ctx_for(scope=B))
    assert heard(on_b) == {"tip.tip.added"}
    assert heard(on_a, timeout=0.3) == set()
    # Positive control: the same listener of A does hear a tip recorded in A.
    run("cash_register.settings.update", {"enable_cash_register": False})
    run("tip.tip.add", {"amount": 300, "pool": True})
    assert "tip.tip.added" in heard(on_a)
    assert channel_for(A) != channel_for(B)

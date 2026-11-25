"""The tips app's events and its reactions to Sales' events: the worker's relay hands each delivered event to
``events.react``, which runs the operation that reacts to it as the system."""

from apps.tip import events

from .conftest import A


def test_its_events():
    assert events.ALL == ["tip.settings.updated", "tip.tip.added", "tip.tip.adjusted", "tip.tip.voided"]
    assert events.AMOUNTS == {"amount", "before.amount", "after.amount"}


def test_tips_react_to_a_void_and_to_a_refund_of_sales():
    assert events.REACTIONS == {"sale.sale.voided": "tip.sale.void", "sale.sale.refunded": "tip.sale.refund"}


def test_another_event_of_sales_is_none_of_tips():
    assert events.react(A, "sale.sale.completed", {"sale_id": "x"}) is None



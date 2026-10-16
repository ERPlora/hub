"""Live queries of the payment app: which events re-run which query after the COMMIT.

The old screen re-read its list on each of the five payment events; here the server re-runs the
subscribed query and sends the result. A payment shows its method's name, so renaming a method
re-runs the payments too.
"""

from pathlib import Path

from live.live_registry import live_registry

from apps.payment import events

EVENTS_SOURCE = Path(events.__file__).read_text()
PAYMENT = [
    "payment.payment.created",
    "payment.payment.approved",
    "payment.payment.sent",
    "payment.payment.completed",
    "payment.payment.cancelled",
]
METHOD = [
    "payment.method.created",
    "payment.method.updated",
    "payment.method.deactivated",
    "payment.method.activated",
]


def payment_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("payment.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    assert payment_queries() == {
        "payment.payment.list": [*PAYMENT, "payment.method.updated"],
        "payment.payment.get": [*PAYMENT, "payment.method.updated"],
        "payment.method.list": METHOD,
        "payment.method.get": METHOD,
    }


def test_every_event_is_a_literal_of_events_py():
    for on in payment_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event


def test_a_new_method_does_not_re_run_the_payments():
    affected = {
        name
        for name in live_registry.affected([events.METHOD_CREATED])
        if name.startswith("payment.")
    }
    assert affected == {"payment.method.list", "payment.method.get"}


def test_completing_a_payment_re_runs_the_payments_only():
    affected = {
        name
        for name in live_registry.affected([events.PAYMENT_COMPLETED])
        if name.startswith("payment.")
    }
    assert affected == {"payment.payment.list", "payment.payment.get"}

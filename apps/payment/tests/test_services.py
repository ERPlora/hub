"""What the tests of the payment app's writes share: how an operation is run, the events in the outbox, the method a
test starts from and the business's day the references are numbered on; the declaration of every write; and the
notification after the COMMIT, on the channel of the command's scope only. Each module of ``services/`` has its own
tests, in ``test_services_<module>.py``.
"""

import datetime as dt
import json

import pytest
from django.utils import timezone
from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, ctx_for, make_method, make_payment

pytestmark = HUB_DB

TODAY = dt.date(2026, 10, 14)
WAIT = 1.0
QUIET = 0.3


def run(name, data: dict, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), op.input.model_validate(data))


def events() -> list[str]:
    return list(OutboxEvent.objects.order_by("id").values_list("name", flat=True))


def payload(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).latest("id").payload


@pytest.fixture(autouse=True)
def business_today(monkeypatch):
    """The business's day the references are numbered on."""
    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: TODAY)


@pytest.fixture
def bank():
    return make_method("BBVA account")


@pytest.mark.parametrize(
    ("name", "permission"),
    [
        ("payment.method.create", "payment.add_payment"),
        ("payment.method.update", "payment.add_payment"),
        ("payment.method.deactivate", "payment.add_payment"),
        ("payment.method.activate", "payment.add_payment"),
        ("payment.payment.create", "payment.add_payment"),
        ("payment.payment.approve", "payment.approve_payment"),
        ("payment.payment.mark_sent", "payment.add_payment"),
        ("payment.payment.mark_completed", "payment.add_payment"),
        ("payment.payment.cancel", "payment.approve_payment"),
    ],
)
def test_declarations(name, permission):
    op = get(name)
    assert (op.kind, op.permission, op.expose_api) == ("command", permission, True)


# ── Notifications: after the COMMIT, on the channel of the command's scope only ───────────────


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@HUB_DB_COMMITTED
def test_a_payment_recorded_in_b_notifies_the_channel_of_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        method = make_method()
        run(
            "payment.payment.create",
            {
                "method_id": str(method.id),
                "payment_date": "2026-10-10",
                "amount": 100,
                "beneficiary_name": "Proveedor",
            },
            scope=B,
        )

    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": ["payment.payment.created"]})
    ]
    assert received(on_a, timeout=QUIET) == []
    # The channel is the command's scope; the rows of the outbox carry theirs, and B's database holds them all.
    with use_hub(hub_b):
        assert set(OutboxEvent.objects.values_list("scope_kind", "scope_key")) == {(B.kind, B.key)}
    assert not OutboxEvent.objects.exists()


@HUB_DB_COMMITTED
def test_a_refused_step_notifies_nobody(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        payment = make_payment(make_method(), status="completed")
        with pytest.raises(Conflict):
            run("payment.payment.approve", {"id": str(payment.id)}, scope=B)
        assert not OutboxEvent.objects.exists()
    assert received(on_b, timeout=QUIET) == []
    assert received(on_a, timeout=QUIET) == []

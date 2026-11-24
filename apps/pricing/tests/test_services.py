"""What the tests of the pricing app's writes share: how an operation is run, the events in the outbox and a
refusal; and the notification after the COMMIT, on the channel of the command's scope only. Each module of
``services/`` has its own tests, in ``test_services_<module>.py``."""

import json

import pytest
from live.models import OutboxEvent
from live.operations import get

from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, ctx_for

pytestmark = HUB_DB


def run(name, data, role="hub_admin", actor="tester"):
    op = get(name)
    return op(ctx_for(role, actor=actor), op.input.model_validate(data))


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")]


def no_events() -> bool:
    return not OutboxEvent.objects.filter(name__startswith="pricing.").exists()


def refused(error, name, data, role="hub_admin"):
    with pytest.raises(error) as caught:
        run(name, data, role)
    return caught.value


# Notifications: after the COMMIT, on the channel of the command's scope only


def received(session, timeout=1.0, stop_after=None):
    return [json.loads(note.payload) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


@HUB_DB_COMMITTED
def test_a_write_in_scope_b_notifies_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    op = get("pricing.price_list.create")
    with use_hub(hub_b):
        op(ctx_for("hub_admin", B), op.input.model_validate({"code": "VIP", "name": "VIP", "is_default": True}))
    assert received(on_b, stop_after=1) == [{"events": ["pricing.price_list.created", "pricing.price_list.default_changed"]}]
    assert received(on_a, timeout=0.3) == []
    # The channel is the command's scope; the rows of the outbox carry theirs, and B's database holds them all.
    with use_hub(hub_b):
        assert set(OutboxEvent.objects.values_list("scope_kind", "scope_key")) == {(B.kind, B.key)}
    assert not OutboxEvent.objects.exists()

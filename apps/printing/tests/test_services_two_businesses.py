"""Printing in business B, beside business A, each in its own database: what B writes is told on B's channel only,
after the COMMIT, and never reaches A (``listen``, in conftest.py)."""

import dataclasses

from live.models import OutboxEvent
from live.outbox import channel_for

from apps.printing.tests.conftest import A, B, HUB_DB, HUB_DB_COMMITTED, RECEIPT, ctx_for, received, run
from apps.printing.tests.test_services import EMPLOYEE, MANAGER, TILL_ID, on_device
from base.tenancy.context import use_hub


def till_of_b():
    """Business B's till, set up from the device ``TILL_ID``; run inside hub B."""
    till = run("printing.printer.create", {"name": "Till", "kind": "network", "address": "10.0.0.1", "usage": "receipt"}, ctx_for(scope=B))
    device = run("printing.device.register", {"name": "Till", "printers": [str(till.id)]}, ctx=dataclasses.replace(on_device(TILL_ID), scope=B))
    return till, device


def device_events() -> list[tuple[str, str]]:
    return sorted(OutboxEvent.objects.filter(name__startswith="printing.device.").values_list("name", "scope_key"))


@HUB_DB
def test_a_device_set_up_in_a_hub_is_told_on_that_hubs_channel_only(hub_b):
    # Writing in hub B never tells hub A: the device's events travel on the scope of whoever set it up.
    with use_hub(hub_b):
        _till, device = till_of_b()
        run("printing.device.retire", {"device_id": str(device.id)}, ctx=dataclasses.replace(ctx_for(MANAGER), scope=B))
        in_b = device_events()
    assert in_b == [("printing.device.registered", B.key), ("printing.device.retired", B.key)]
    assert device_events() == []


@HUB_DB_COMMITTED
def test_a_job_queued_in_b_wakes_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        run("printing.job.create", {"document_type": "receipt", "document": RECEIPT}, ctx_for(scope=B))
        assert OutboxEvent.objects.get(name="printing.job.queued").scope_key == B.key
    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": ["printing.job.queued"]})]
    assert received(on_a, timeout=0.3) == []


@HUB_DB_COMMITTED
def test_a_device_seen_in_b_tells_neither_b_nor_a(listen, hub_b):
    with use_hub(hub_b):
        till_of_b()
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        assert run("printing.device.seen", {"device": TILL_ID}, ctx=ctx_for(EMPLOYEE, scope=B)).seen is True
    assert received(on_b, timeout=0.3) == []
    assert received(on_a, timeout=0.3) == []

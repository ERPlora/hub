"""The wake of ``/ws/print``: a job queued after the COMMIT wakes the device of its hub and not another hub's, and a
device is not woken by what it did to the queue itself."""

import asyncio
from collections import defaultdict
from collections.abc import Callable

import pytest

from base import ws_print
from base.tenancy.tests.business import A, B, HUB_DB_COMMITTED, in_business_a
from base.tests.businesses import in_each, inside, scopes_of
from base.tests.print_socket import (
    HUB_HOST,
    OTHER_HOST,
    QUIET,
    WAIT,
    db,
    enqueue,
    fresh_live,
    printer,
    ready_socket,
    ready_with_a_job,
    run,
    session,
    sockets,
)

__all__ = ["fresh_live", "in_business_a", "session", "sockets"]
pytestmark = HUB_DB_COMMITTED


@pytest.fixture
def handled(monkeypatch):
    """The wake results each socket handled, in order, by its device: the ids of the waiting jobs each one shows. A
    test waits for the result that follows a change and then reads what the socket sent, instead of waiting for a
    silence a loaded runner may not keep (the live re-run is grouped 150 ms, hub#135)."""
    results: defaultdict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
    handle = ws_print.PrintSocket._on_stream

    async def recorded(self, item):
        try:
            return await handle(self, item)
        finally:
            event, data = ws_print._decode_frame(item)
            if event == "result":
                results[self.device.device_id].put_nowait({row["id"] for row in data["data"]["rows"]})

    monkeypatch.setattr(ws_print.PrintSocket, "_on_stream", recorded)
    return results


async def handled_until(results: asyncio.Queue, check: Callable[[set[str]], bool]) -> None:
    """Wait until the socket handled a wake result whose waiting jobs pass ``check``."""
    while not check(await asyncio.wait_for(results.get(), WAIT)):
        pass


async def test_a_job_queued_after_the_commit_wakes_the_device_of_its_hub_and_no_other(sockets, session, hub_b):
    cookie_a, cookie_b = await db(session, "ana"), await db(session, "bea", host=B.key)
    till_a = await db(printer, "Till A", scope=A)
    till_b = await db(inside, hub_b, printer, "Till B", scope=B)
    in_a = await ready_socket(sockets, cookie_a, [till_a], HUB_HOST)
    in_b = await ready_socket(sockets, cookie_b, [till_b], OTHER_HOST, device_id="till-b")

    await db(enqueue, till_a, scope=A)

    assert await in_a.receive() == {"type": "wake", "role": "receipt"}
    assert await in_b.silent(), "a job of hub A woke a device of hub B"

    await db(inside, hub_b, enqueue, till_b, scope=B)
    assert await in_b.receive() == {"type": "wake", "role": "receipt"}
    assert await in_a.silent(), "a job of hub B woke a device of hub A"
    assert await db(in_each, lambda _: scopes_of("printing.job.queued"), hub_b) == ([(A.kind, A.key)], [(B.kind, B.key)])


async def test_a_claim_that_empties_the_queue_wakes_nobody(sockets, session):
    """The wake says a job is waiting (the old hub's: «a job was just queued for a role you host»); the queue
    changing because this device took its last job is no wake, or every job would end in a claim → idle."""
    socket, till, queued = await ready_with_a_job(sockets, session)

    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(queued.id)
    assert await socket.silent(QUIET), "a wake with nothing waiting (the claim emptied the queue)"

    await socket.send({"type": "done", "jobId": str(queued.id)})
    assert (await socket.receive())["type"] == "ack"
    assert await socket.silent(QUIET), "a wake with nothing waiting (after the confirmation)"

    await db(enqueue, till)
    assert await socket.receive() == {"type": "wake", "role": "receipt"}, "a job queued still wakes the device"


async def test_its_own_claim_does_not_wake_the_device_while_other_jobs_wait(sockets, session, handled):
    """A claim of this device changes the queue while other jobs of the role still wait (here one of a printer it
    does not reach): that queues nothing, so it is no wake. The live re-run is grouped, and such a wake came late,
    between a later claim and its ``idle`` (hub#135, ``test_claim_hands_the_oldest_job…``)."""
    cookie = await db(session)
    till = await db(printer, "Till")
    other = await db(printer, "Front desk")
    first = await db(enqueue, till)
    await db(enqueue, other)
    second = await db(enqueue, till)
    socket = await ready_socket(sockets, cookie, [till])

    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(first.id)
    await handled_until(handled["till-1"], lambda waiting: str(first.id) not in waiting)
    assert socket.outbox.empty(), "a wake for this device's own claim"

    await socket.send({"type": "done", "jobId": str(first.id)})
    assert (await socket.receive())["type"] == "ack"
    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(second.id)
    await handled_until(handled["till-1"], lambda waiting: str(second.id) not in waiting)
    assert socket.outbox.empty(), "a wake for this device's own claim"

    await db(enqueue, till)
    assert await socket.receive() == {"type": "wake", "role": "receipt"}, "a job queued still wakes the device"


async def test_a_job_queued_behind_a_backlog_of_its_function_still_wakes_the_device(sockets, session):
    """The wake watches the newest waiting jobs of the function: a job just queued is among them however many jobs of
    a printer nobody drains wait before it."""
    cookie = await db(session)
    till = await db(printer, "Till")
    unattended = await db(printer, "Front desk")
    for _ in range(ws_print.WAKE_WINDOW):
        await db(enqueue, unattended)
    socket = await ready_socket(sockets, cookie, [till])

    await db(enqueue, till)

    assert await socket.receive() == {"type": "wake", "role": "receipt"}


async def test_the_job_it_sent_back_does_not_wake_the_device_until_somebody_retries_it(sockets, session, handled):
    """A device that could not print a job sends it back and stops pulling that role, or an empty roll would burn
    the job's five hand-outs in a second (the old print host): the job waiting again is no news to it. Somebody
    retrying it is (they changed the roll)."""
    socket, _, queued = await ready_with_a_job(sockets, session)
    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(queued.id)
    await handled_until(handled["till-1"], lambda waiting: str(queued.id) not in waiting)

    await socket.send({"type": "failed", "jobId": str(queued.id), "error": "out of paper"})
    assert (await socket.receive())["requeued"] is True
    await handled_until(handled["till-1"], lambda waiting: str(queued.id) in waiting)
    assert socket.outbox.empty(), "a wake for the job this device sent back itself"

    await db(run, "printing.job.retry", {"job_id": str(queued.id)})
    assert await socket.receive() == {"type": "wake", "role": "receipt"}, "a retry is news"


async def test_a_job_another_device_sent_back_wakes_this_one(sockets, session, handled):
    """Sent back, the job waits for any device that prints it (the old print host's «the hub puts the ticket back
    for another host»): the other device is woken, the one that failed it is not."""
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    holder = await ready_socket(sockets, cookie, [till], device_id="till-1")
    other = await ready_socket(sockets, cookie, [till], device_id="till-2")
    await holder.send({"type": "claim", "role": "receipt"})
    assert (await holder.receive())["jobId"] == str(queued.id)
    for device in ("till-1", "till-2"):
        await handled_until(handled[device], lambda waiting: str(queued.id) not in waiting)

    await holder.send({"type": "failed", "jobId": str(queued.id), "error": "out of paper"})
    assert (await holder.receive())["requeued"] is True

    assert await other.receive() == {"type": "wake", "role": "receipt"}
    await handled_until(handled["till-1"], lambda waiting: str(queued.id) in waiting)
    assert holder.outbox.empty(), "a wake for the job this device sent back itself"


async def test_the_wake_never_carries_the_document(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    socket = await ready_socket(sockets, cookie, [till])

    await db(enqueue, till)

    assert set(await socket.receive()) == {"type", "role"}

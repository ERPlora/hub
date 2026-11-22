"""Draining through ``/ws/print``: ``claim`` hands the oldest job of the device's printers, ``done``/``failed`` close
it, and a beat counts the printers the device still reaches."""

from base import ws_print
from base.tenancy.tests.business import HUB_DB_COMMITTED, in_business_a
from base.tests.print_socket import db, enqueue, fresh_live, printer, ready_socket, run, session, sockets, status_of

__all__ = ["fresh_live", "in_business_a", "session", "sockets"]
pytestmark = HUB_DB_COMMITTED


async def test_claim_hands_the_oldest_job_of_its_printers_and_done_closes_it(sockets, session):
    cookie = await db(session)
    till = await db(printer, "Till")
    other = await db(printer, "Front desk")
    first = await db(enqueue, till)
    elsewhere = await db(enqueue, other)
    second = await db(enqueue, till)
    socket = await ready_socket(sockets, cookie, [till])

    await socket.send({"type": "claim", "role": "receipt"})
    job = await socket.receive()

    assert job["type"] == "job"
    assert job["jobId"] == str(first.id)
    assert job["role"] == "receipt"
    assert job["documentType"] == "receipt"
    assert job["document"]["receipt_id"] == "T-000123"
    assert job["format"] == "receipt"
    assert job["attempts"] == 1
    assert job["kind"] == "document"
    assert job["printerId"] == till
    assert job["target"] == "network:192.168.1.50:9100"
    assert job["copies"] == 1
    assert {"paperWidth", "copyDocument", "openDrawer", "html"} <= job.keys()

    await socket.send({"type": "done", "jobId": job["jobId"]})
    assert await socket.receive() == {"type": "ack", "jobId": str(first.id), "confirmed": True}
    assert await db(status_of, first.id) == "done"

    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["jobId"] == str(second.id)
    await socket.send({"type": "done", "jobId": str(second.id)})
    await socket.receive()
    await socket.send({"type": "claim", "role": "receipt"})
    assert await socket.receive() == {"type": "idle", "role": "receipt"}
    assert await db(status_of, elsewhere.id) == "pending", "a printer this device does not reach"


async def test_a_reported_failure_puts_the_job_back_in_the_queue(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    socket = await ready_socket(sockets, cookie, [till])
    await socket.send({"type": "claim", "role": "receipt"})
    await socket.receive()

    await socket.send({"type": "failed", "jobId": str(queued.id), "error": "out of paper"})

    assert await socket.receive() == {"type": "ack", "jobId": str(queued.id), "requeued": True}
    assert await db(status_of, queued.id) == "pending"


async def test_a_confirmation_resent_after_a_reconnect_is_taken(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    before = await ready_socket(sockets, cookie, [till])
    await before.send({"type": "claim", "role": "receipt"})
    await before.receive()
    await before.disconnect()

    after = await ready_socket(sockets, cookie, [till])
    await after.send({"type": "done", "jobId": str(queued.id)})

    assert await after.receive() == {"type": "ack", "jobId": str(queued.id), "confirmed": True}
    assert await db(status_of, queued.id) == "done"


async def test_another_devices_job_is_not_confirmed_by_this_one(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    queued = await db(enqueue, till)
    holder = await ready_socket(sockets, cookie, [till], device_id="till-1")
    await holder.send({"type": "claim", "role": "receipt"})
    await holder.receive()

    stranger = await ready_socket(sockets, cookie, [till], device_id="till-2")
    await stranger.send({"type": "done", "jobId": str(queued.id)})

    assert await stranger.receive() == {"type": "ack", "jobId": str(queued.id), "confirmed": False}
    assert await db(status_of, queued.id) == "sent"


async def test_a_role_the_device_does_not_print_is_refused_and_the_socket_stays(sockets, session):
    cookie = await db(session)
    till = await db(printer)
    await db(enqueue, usage="kitchen", document_type="kitchen_order", document={"items": []})
    socket = await ready_socket(sockets, cookie, [till])

    await socket.send({"type": "claim", "role": "kitchen"})

    frame = await socket.receive()
    assert frame["code"] == "print.role_not_hosted"
    await socket.send({"type": "claim", "role": "receipt"})
    assert (await socket.receive())["type"] == "idle", "it is still the receipt's printing device"


async def test_a_beat_counts_the_printers_the_device_still_reaches(sockets, session):
    cookie = await db(session)
    till = await db(printer, "Till")
    kitchen = await db(printer, "Kitchen", "kitchen")
    socket = await ready_socket(sockets, cookie, [till, kitchen])

    await socket.send({"type": "beat"})
    assert await socket.receive() == {"type": "beat", "refreshed": 2, "heartbeatSeconds": ws_print.HEARTBEAT_SECONDS}

    for printer_id in (till, kitchen):
        await db(run, "printing.printer.update", {"printer_id": printer_id, "is_active": False})
    await socket.send({"type": "beat"})
    assert (await socket.receive())["refreshed"] == 0

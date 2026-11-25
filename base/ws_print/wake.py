"""The wake of the print channel: one live subscription per role to its newest waiting jobs, whose results say that
a job was queued for the device."""

import json

from live.broker import broker
from live.executor import Stream, Subscription, executor

from base.ws_print.printing import JOB_LIST, _operation

#: Waiting jobs of each role the wake watches, newest first: a job just queued is always among them, and 20 of the
#: longest rows printing lists (about 170 KiB) stay under a live result's cap (``live.sse.MAX_RESULT_BYTES``).
WAKE_WINDOW = 20


class WakeMixin:
    """The live subscriptions of a ``PrintSocket`` (``base.ws_print.protocol``), kept on its device."""

    async def _follow(self) -> None:
        """Subscribe the device's roles to the live broker: one subscription per role, its newest waiting jobs."""
        device = self.device
        if not device.roles:
            return
        stream = Stream(device.ctx)
        op = _operation(JOB_LIST)
        for role in device.roles:
            params = {"status": "pending", "usage": role, "limit": WAKE_WINDOW, "sort": "created_at", "dir": "desc"}
            stream.subs[role] = Subscription(id=role, op=op, params=op.input.model_validate(params))
        device.stream = stream
        # Listening before the first run: no COMMIT after ``ready`` is missed (live.broker.Broker.register).
        await broker.register(stream)
        await executor.run_all(stream)

    def _unfollow(self) -> None:
        device = self.device
        if device is None or device.stream is None:
            return
        stream, device.stream = device.stream, None
        stream.closed = True
        broker.unregister(stream)
        executor.forget(stream)


def _waiting(job: dict) -> tuple:
    """A waiting job as the wake tells it apart: the job and its last retry, so somebody retrying a job that was
    already waiting is news too."""
    return job["id"], job.get("retried_at")


def _decode_frame(item: bytes) -> tuple[str, dict]:
    """The event and the data of one frame of a live stream (``live.sse.frame``)."""
    event, data = "", {}
    for line in item.decode().splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = json.loads(line.removeprefix("data: "))
    return event, data

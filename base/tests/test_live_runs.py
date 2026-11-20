"""A live run already in its thread reads on after its stream has gone; ending the live runs waits for it, so the
business database it reads is not emptied under it."""

import asyncio
import threading
import time
from types import SimpleNamespace

from django.db import transaction
from live.context import OperationContext
from live.executor import Stream, Subscription, executor

from apps.printing.models import PrintJob
from base.tenancy.context import current_alias, use_hub
from base.tenancy.tests.business import A, HUB_DB_COMMITTED, in_business_a
from base.tests.live_runs import end_the_live_runs

__all__ = ["in_business_a"]
pytestmark = HUB_DB_COMMITTED


class ReadingQuery:
    """A live query that reads business A's print jobs as printing's list does, pausing in its transaction between the
    count and the jobs with their printers: the order of locks that deadlocked with the ``TRUNCATE`` emptying the
    database after a committed test."""

    name = "printing.job.list"
    kind = "query"
    permission = None

    def __init__(self, hub, pause: float) -> None:
        self.hub, self.pause = hub, pause
        self.reading, self.done = threading.Event(), threading.Event()

    def __call__(self, ctx, params):
        with use_hub(self.hub), transaction.atomic(using=current_alias()):
            PrintJob.objects.count()
            self.reading.set()
            time.sleep(self.pause)
            list(PrintJob.objects.select_related("printer"))
        self.done.set()
        return SimpleNamespace(model_dump=lambda mode: {"rows": []})


class PlainBuilder:
    """A context builder that enters nothing: the query enters its business itself."""

    def refresh(self, ctx):
        return ctx


async def test_a_run_still_reading_after_its_stream_has_gone_has_ended_once_the_live_runs_end(settings, in_business_a):
    settings.LIVE = {**settings.LIVE, "context_builder": "base.tests.test_live_runs.PlainBuilder"}
    query = ReadingQuery(in_business_a, pause=0.3)
    stream = Stream(OperationContext(scope=A, actor="ana", permissions=frozenset({"*"}), language="en"))
    stream.subs["jobs"] = Subscription(id="jobs", op=query, params=None)
    executor.reset()
    running = asyncio.ensure_future(executor.run_all(stream))
    assert await asyncio.to_thread(query.reading.wait, 5)
    # What a socket that goes away does: its stream closes and is forgotten, while its run reads on in its thread.
    stream.closed = True
    executor.forget(stream)
    running.cancel()

    end_the_live_runs()

    assert query.done.is_set(), "the live runs ended while one was still reading business A"

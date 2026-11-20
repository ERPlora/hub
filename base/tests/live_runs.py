"""The live executor's runs, ended after a test: a run already in its thread reads on after its stream has gone, and a
committed test's business database is emptied after it with a ``TRUNCATE`` that deadlocks with a reader still there."""

import threading
import time

from live.executor import executor

#: The name the live executor gives its threads (``live.executor``).
THREAD_PREFIX = "live-query"


def end_the_live_runs(wait: float = 5.0) -> None:
    """Stop the live executor's threads and wait for each one to finish the run it is in, or fail naming it."""
    executor.shutdown()
    deadline = time.monotonic() + wait
    for thread in threading.enumerate():
        if thread.name.startswith(THREAD_PREFIX):
            thread.join(max(0.0, deadline - time.monotonic()))
    left = [thread.name for thread in threading.enumerate() if thread.name.startswith(THREAD_PREFIX)]
    assert not left, f"still running a live query after {wait:g} s: {left}"

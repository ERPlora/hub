"""Slow I/O after the COMMIT, off the loop that committed (PLAN-HUB «Eventos entre módulos»; FIX-HUB-BASE-RELAY-BLOCKED-BY-SLOW-REACTION-CALLS).

The worker relays the outbox of every hub and runs the scheduled tasks in one loop, one transaction each, and Django
runs what a transaction leaves for after its COMMIT right there, in that loop: a reaction that called another system
(a «Call another system» step, up to 30 s; «Ask the assistant», minutes) held every other delivery, of every hub,
until it answered, and a call the tick sent again held the scheduled tasks. ``after_commit(fn, *args)`` is the one way
an app makes such I/O: after the COMMIT of the running operation (never after a rollback), ``fn(*args)`` goes to a
few threads of the process's own, in the database context of the operation that asked (its ``use_hub``, or phase 1's
shared database), and the loop goes on at once.

- **Recovered by its app**: a job may be lost (its queue is full, the worker stops, the process dies), so ``fn`` is
  only work its app finds again by itself: a claim with a lease, and a sweep that sends again what nobody claimed or
  whose lease ran out (``flow.run.claim_call``: every attempt with the same idempotency key). The relay's «exactly
  once» stays the relay's: a delivery and its mark commit together; what the reaction leaves here is a job of its own.
- **Bounded**: ``THREADS`` jobs at once and ``QUEUED`` waiting; past that a job is dropped with a warning. The same
  ``fn`` with the same arguments already waiting is not queued twice (a sweep sends again, every minute, what still
  waits); one that already runs may be (the next step of its run may need it: its claim says whether it goes).
- **Connections**: a job's thread gives its connections back when the job ends, and ``release()`` gives them back
  before the job waits on the network: no thread idles holding one (``close_old_connections``, as the loop does: every
  alias has ``CONN_MAX_AGE`` 0; the loop's and these fit in the default alias's pool of 8, ``config/settings.py``).
- **Stop**: ``stop(grace)``, the worker on its way out (SIGTERM on a deploy): what waits is dropped; what runs gets
  ``grace`` seconds, and what still runs then is left behind (daemon threads end with the process): its lease sends
  it again.
- **Failures**: a job that raises is logged with its traceback, its function and its arguments (ids, never a
  secret), and the others go on.

The tests run each job at once, in the thread that committed (``conftest.py``): a test's transaction is invisible to
another thread's connection. A test marked ``outbound_threads`` gets the real pool.
"""

import logging
import queue
import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from functools import partial
from typing import Any

from django.db import close_old_connections
from live.operations import current_operation, on_commit

from base.tenancy import context

logger = logging.getLogger(__name__)

#: Jobs at once: with the worker's loop, five of the default alias's pool of 8 connections.
THREADS = 4
#: Jobs waiting at most; past it a job is dropped (its app's sweep sends it again).
QUEUED = 1000

#: Whether the running thread is one of a pool's (``release`` closes nothing anywhere else).
_thread = threading.local()


@dataclass(frozen=True, eq=False)
class Job:
    """``fn(*args)`` in ``database``: the context of the operation that asked."""

    fn: Callable[..., Any]
    args: tuple[Hashable, ...]
    database: context.DatabaseContext

    @property
    def key(self) -> tuple:
        """Which job it is: the same function with the same arguments is the same job."""
        return (self.fn, self.args)

    def run(self) -> None:
        with context.use_again(self.database):
            self.fn(*self.args)

    def __str__(self) -> str:
        name = f"{getattr(self.fn, '__module__', '?')}.{getattr(self.fn, '__qualname__', repr(self.fn))}"
        return f"{name}{self.args!r}"


class Pool:
    """The threads of the process that run the jobs: ``threads`` at once, at most ``queued`` waiting."""

    def __init__(self, *, threads: int = THREADS, queued: int = QUEUED) -> None:
        self._size = threads
        self._limit = queued
        self._jobs: queue.SimpleQueue[Job | None] = queue.SimpleQueue()
        self._lock = threading.Lock()
        #: The keys of the jobs that wait: a job already waiting is not queued twice.
        self._waiting: set[tuple] = set()
        self._threads: list[threading.Thread] = []
        self._stopped = False

    def submit(self, job: Job) -> bool:
        """Queue ``job``; ``False`` when the same one already waits, the queue is full or the pool stopped."""
        with self._lock:
            if self._stopped:
                logger.warning("outbound: %s dropped: the worker is stopping; its app sends it again.", job)
                return False
            if job.key in self._waiting:
                return False
            if len(self._waiting) >= self._limit:
                logger.warning(
                    "outbound: %s dropped: %d jobs wait already; its app sends it again.", job, len(self._waiting)
                )
                return False
            self._waiting.add(job.key)
            self._jobs.put(job)
            if len(self._threads) < self._size:
                thread = threading.Thread(target=self._work, name=f"outbound-{len(self._threads) + 1}", daemon=True)
                self._threads.append(thread)
                thread.start()
        return True

    def stop(self, grace: float) -> bool:
        """Drop what waits and give what runs ``grace`` seconds; ``True`` when nothing runs any more. A stopped pool
        takes nothing more."""
        with self._lock:
            self._stopped = True
            dropped = 0
            while True:
                try:
                    job = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if job is not None:
                    dropped += 1
            self._waiting.clear()
            threads = [thread for thread in self._threads if thread.is_alive()]
            for _ in threads:
                self._jobs.put(None)  # each thread ends once its job, if any, is done
        if dropped:
            logger.warning("outbound: stopping: %d job(s) that waited were dropped; their apps send them again.", dropped)
        deadline = time.monotonic() + grace
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        running = sum(thread.is_alive() for thread in threads)
        if running:
            logger.warning("outbound: stopped with %d job(s) still running: their lease sends them again.", running)
        return not running

    def _work(self) -> None:
        _thread.in_pool = True
        while True:
            job = self._jobs.get()
            if job is None:
                return
            with self._lock:
                self._waiting.discard(job.key)
            try:
                job.run()
            except Exception:
                logger.exception("outbound: %s failed; its app sends it again (its lease, its sweep).", job)
            finally:
                close_old_connections()


_pool: Pool | None = None
_pool_lock = threading.Lock()


def _the_pool() -> Pool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = Pool()
        return _pool


def after_commit(fn: Callable[..., Any], *args: Hashable) -> None:
    """Run ``fn(*args)`` after the COMMIT of the running operation, in a thread of the pool and in this operation's
    database context; nothing after a rollback. ``args`` say which job it is (ids: hashable, logged on a failure)."""
    job = Job(fn, args, context.current())
    hash(job.key)
    on_commit(partial(_submit, job), robust=True)


def _submit(job: Job) -> None:
    _the_pool().submit(job)


def release() -> None:
    """Give the connections of this job's thread back before it waits on the network, between two operations (an app
    opens a transaction only in one); outside a thread of the pool, nothing: a request's or a test's transaction is
    never closed under it."""
    if not getattr(_thread, "in_pool", False):
        return
    if current_operation.get() is not None:
        raise RuntimeError("outbound.release() inside an operation, whose transaction is open: it goes between two.")
    close_old_connections()


def stop(grace: float) -> bool:
    """The worker on its way out: what waits is dropped and what runs gets ``grace`` seconds (``Pool.stop``)."""
    with _pool_lock:
        pool = _pool
    return True if pool is None else pool.stop(grace)

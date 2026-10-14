"""The Hub's worker (CLAUDE.md «Procesos»; aws-next README, «Contrato app ↔ infra»).

``manage.py run_worker`` runs it in the ``worker`` task, one per deploy. It first registers the
Hub's modules in the SaaS's registry (round 16, PLAN §21.1.1): without its apps registered there is
no release, so it does no work before that. Two cases (first production deploy, 2026-10-14):

- the SaaS has not migrated the ``shared`` schema yet (``SharedSchemaNotReady``: its tables do not
  exist): transient, so it warns and retries after 5, 10, 20, 40 and then every 60 s, running and
  without working, so ECS sees a stable task; a stop request during the wait exits 0;
- any other failure, a missing column included (a contract gap, spec §3.5): fatal, 1, and ECS's
  ``task_failed`` rule reports it.

Then it waits until asked to stop. Phase 1 has nothing else to do; phase 2 adds, in this loop, the
outbox relay, the scheduled tasks, the fiscal sending, the hubs' provisioning and purge
(``hub_due``) and the demo reaper, each claiming its work with ``SKIP LOCKED``.
"""

import logging
import threading
from collections.abc import Callable

from django.db import close_old_connections

from base import catalog

logger = logging.getLogger(__name__)

#: How often the loop looks for work; a stop request wakes it up at once.
TICK_SECONDS = 5.0
#: The waits while the SaaS has not migrated ``shared`` yet: they double, 5 s first, 60 s at most.
RETRY_FIRST_SECONDS = 5
RETRY_MAX_SECONDS = 60


def run(
    stop: threading.Event,
    *,
    tick_seconds: float = TICK_SECONDS,
    wait: Callable[[float], object] | None = None,
) -> int:
    """Register the apps, then loop until ``stop`` is set; return the process's exit code.

    ``wait(seconds)`` sleeps until the time is up or a stop is requested: ``stop.wait`` unless a
    test replaces it. ``stop`` alone says whether to stop.
    """
    wait = stop.wait if wait is None else wait
    delay = RETRY_FIRST_SECONDS
    while True:
        try:
            result = catalog.register_apps()
            break
        except catalog.SharedSchemaNotReady as error:
            logger.warning(
                "worker: shared schema not migrated yet; retrying in %d s (%s).",
                delay,
                error,
            )
        except Exception:
            logger.exception(
                "worker: register_apps failed; the worker stops (no release without its apps)."
            )
            return 1
        # The SaaS's database is not held open while it waits.
        close_old_connections()
        wait(delay)
        if stop.is_set():
            logger.info("worker: stopped before registering its apps.")
            return 0
        delay = min(delay * 2, RETRY_MAX_SECONDS)
    # register_apps' connection (the SaaS's database) is not kept open while the worker idles.
    close_old_connections()
    if result.skipped:
        registered = "a newer release had already registered its apps"
    else:
        registered = f"{result.written} app(s) registered: {', '.join(result.apps)}"
    logger.info("worker: waiting for work (%s).", registered)
    while not stop.is_set():
        # Phase 1: nothing to do yet.
        wait(tick_seconds)
    logger.info("worker: stopped.")
    return 0

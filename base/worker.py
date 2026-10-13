"""The Hub's worker (CLAUDE.md «Procesos»; aws-next README, «Contrato app ↔ infra»).

``manage.py run_worker`` runs it in the ``worker`` task, one per deploy. It first registers the
Hub's modules in the SaaS's registry (round 16, PLAN §21.1.1): without its apps registered there is
no release, so any failure there is fatal (1, and ECS's ``task_failed`` rule reports it). Then it
waits until asked to stop. Phase 1 has nothing else to do; phase 2 adds, in this loop, the outbox
relay, the scheduled tasks, the fiscal sending, the hubs' provisioning and purge (``hub_due``) and
the demo reaper, each claiming its work with ``SKIP LOCKED``.
"""

import logging
import threading

from django.db import close_old_connections

from base import catalog

logger = logging.getLogger(__name__)

#: How often the loop looks for work; a stop request wakes it up at once.
TICK_SECONDS = 5.0


def run(stop: threading.Event, *, tick_seconds: float = TICK_SECONDS) -> int:
    """Register the apps, then loop until ``stop`` is set; return the process's exit code."""
    try:
        result = catalog.register_apps()
    except Exception:
        logger.exception(
            "worker: register_apps failed; the worker stops (no release without its apps)."
        )
        return 1
    # register_apps' connection (the SaaS's database) is not kept open while the worker idles.
    close_old_connections()
    if result.skipped:
        registered = "a newer release had already registered its apps"
    else:
        registered = f"{result.written} app(s) registered: {', '.join(result.apps)}"
    logger.info("worker: waiting for work (%s).", registered)
    while not stop.is_set():
        # Phase 1: nothing to do yet.
        stop.wait(tick_seconds)
    logger.info("worker: stopped.")
    return 0

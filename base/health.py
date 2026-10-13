"""``/healthz`` and ``/readyz``: the process is up; the process can serve.

``/healthz`` never touches the database: the load balancer and the container probe it, and an
Aurora failover must not drain every target. The ALB probes each task by its IP, a Host that
``ALLOWED_HOSTS`` rejects, so the answer comes from a middleware placed before anything that
validates the Host (``CommonMiddleware``, ``CsrfViewMiddleware``…).

``/readyz`` is the deploy pipeline's gate and Route 53's probe (PLAN-AWS §5): 200 with the control
database reachable and every migration of this code applied, 503 otherwise. It is a route
(``config/urls.py``) on the real hosts (a hub's, the platform host ``hubs.erplora.com`` and the private
name), and the host gates of ``base.middleware`` leave it alone. Cheap: one connection from the pool
and the read of ``django_migrations``; the reason of a 503 is logged, never sent. Route 53 probes it
about 30 times a minute, so its answer, 200 or 503, is kept ``READYZ_KEEP_SECONDS`` in the process
(``time.monotonic``), as saas-next's: never in Valkey, so a Valkey outage never takes ``/readyz`` down
with it. The Host is still validated on every request (the answer is kept in the view, after the
middleware).
"""

import logging
from time import monotonic

from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)

HEALTHZ_PATH = "/healthz"
READYZ_PATH = "/readyz"


def healthz(request: HttpRequest) -> HttpResponse:
    return JsonResponse({"status": "ok"})


#: Seconds a /readyz answer is kept before the control database is read again.
READYZ_KEEP_SECONDS = 10.0

# (until, status, body) of the last answer, or None. One per process; a race between two threads only
# reads the database twice.
_kept: tuple[float, int, dict[str, str]] | None = None


@never_cache
@require_safe
def readyz(request: HttpRequest) -> HttpResponse:
    global _kept
    now = monotonic()
    if _kept is None or now >= _kept[0]:
        status, body = _readiness()
        _kept = (now + READYZ_KEEP_SECONDS, status, body)
    _until, status, body = _kept
    return JsonResponse(body, status=status)


def forget_readiness() -> None:
    """Drop the kept answer: the next /readyz reads the control database."""
    global _kept
    _kept = None


def _readiness() -> tuple[int, dict[str, str]]:
    try:
        pending = _pending_migrations()
    except DatabaseError as exc:
        logger.warning("/readyz: the control database is unreachable (%s).", exc)
        return _unavailable("database")
    if pending:
        logger.warning(
            "/readyz: %d migration(s) not applied, the first %s.",
            len(pending),
            pending[0],
        )
        return _unavailable("migrations")
    return 200, {"status": "ok"}


def _pending_migrations() -> list[str]:
    """The migrations of this code not applied on the control database, as ``app.name``."""
    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def _unavailable(reason: str) -> tuple[int, dict[str, str]]:
    return 503, {"status": "unavailable", "reason": reason}


class HealthCheckMiddleware(MiddlewareMixin):
    """Answer ``/healthz`` on any Host, before the rest of the middleware runs."""

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        if request.path == HEALTHZ_PATH:
            return healthz(request)
        return None

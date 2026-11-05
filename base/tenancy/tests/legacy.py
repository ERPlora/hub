"""The suite's tests written before the tenancy: where they keep their businesses' rows without a context of their own.

Production has no such place: since S5 every business has its own database, and a hub's model or operation without
``use_hub`` fails (``HubContextMissing``); a business without one is never entered (``HubWithoutDatabase``). The tests
of phase 1 call operations and the ORM directly, for the local hubs ``a`` and ``b`` and the businesses they make
(``db_name=""``), so the session keeps a place for them: control's test database also holds the tables of the hubs'
apps (:class:`LegacyTablesRouter`, in ``config/settings_pytest.py`` only), and :data:`LEGACY` is the fallback the root
``conftest.py`` sets (``context._test_fallback``), under which such a business is entered there. The tests of the
tenancy turn it off (``no_test_fallback``) and run as production does; the tests of the cut write with
:func:`use_legacy` what phase 1 left in control's tables. The worker's loop serves only the hubs with their own
database: for the tests that run it on the suite's businesses, :func:`worker_pass` stands in for its pass over
control's outbox (``conftest.py``, ``legacy_worker``).
"""

import logging

from django.db import DEFAULT_DB_ALIAS, close_old_connections
from live.context import Scope

from base.tenancy import context, inventory

logger = logging.getLogger("base.worker")

#: The fallback of the suite's tests written before the tenancy: control's test database, every business's rows in it.
LEGACY = context.DatabaseContext(kind="legacy", alias=DEFAULT_DB_ALIAS)
#: Whose the tasks of :func:`worker_pass` are: the suite's business ``a``. Every business's rows share control's test
#: database and none says whose it is, so a pass runs each task once, on one scope; a run of two businesses going out
#: each as its own takes two databases (``apps/flow/tests/test_worker_parked_runs.py``).
BUSINESS = Scope("host", "a")


def use_legacy():
    """Work on control's test database as phase 1 did, every business's rows in it, until the block ends."""
    return context._entered(LEGACY)


class LegacyTablesRouter:
    """First of the tests' ``DATABASE_ROUTERS``: control's test database gets the tables of the hubs' apps too, for the
    suite's tests written before the tenancy. Says nothing of anything else (the ``TenantRouter`` decides)."""

    def allow_migrate(self, db: str, app_label: str, model_name: str | None = None, **hints) -> bool | None:
        if db != DEFAULT_DB_ALIAS:
            return None
        if model_name is None:
            database_class = inventory.APP_CLASSES.get(app_label) or inventory.classify_label(app_label, "")
        else:
            database_class = inventory.classify_label(app_label, model_name)
        return True if database_class == inventory.HUB else None


def worker_pass(now) -> None:
    """The tick of the suite's businesses on control's test database, in place of the worker's pass over control's
    outbox (``base.worker._relay``): the apps' tasks due (their schedule written first, idempotent) on the business's
    scope, as ``base.worker._serve_hub`` runs them (the operation of an app off there refuses to run), and the relay of
    every event, each pass failing alone, logged."""
    from base import relay, scheduler

    try:
        with use_legacy():
            scheduler.sync(now)
            scheduler.run_due(now, scope=BUSINESS)
    except Exception:
        logger.exception("worker: the scheduled tasks could not run; the next tick tries again.")
        close_old_connections()
    try:
        with use_legacy():
            relay.run(now)
    except Exception:
        logger.exception("worker: the outbox relay failed; the next tick tries again.")
        close_old_connections()

"""The worker's pass making the tables of the apps the hubs turned on (``base.worker``)."""

import datetime as dt
import logging
import time
from functools import cache

from django.db import close_old_connections

from live.context import OperationContext, Scope
from live.operations import get as get_operation

from base import activation, queries, schemas, services
from base.tenancy import migrator
from base.tenancy.connections import close_hub_aliases
from base.tenancy.context import use_control, use_hub

logger = logging.getLogger("base.worker")  # logged as the worker, whose passes these are

#: How long the pass making the tables of the apps turned on may go on in a tick; a hub it started is always finished,
#: and the next tick goes on after it.
ACTIVATION_PASS_SECONDS = 10.0
#: How long it waits for a hub's schema another run holds before putting the app off (``SchemaLocked``).
ACTIVATION_LOCK_WAIT = 1.0


def _activations(now: dt.datetime) -> bool:
    """Make the tables of the apps due in the hubs rung (their ``hub_due`` came: an app turned on or tried again, a
    retry's time, a ring of the sweep), for :data:`ACTIVATION_PASS_SECONDS` at most; a hub that fails is logged and the
    others are served. Whether it served one, or failed to read them (the next tick tries again)."""
    try:
        with use_control():
            rung = services.activation.activation_hubs(now)
    except Exception:
        logger.exception("worker: the hubs with apps to set up could not be read; the next tick tries again.")
        close_old_connections()
        return True
    started = time.monotonic()
    for hub in rung:
        _activate(hub, now)
        if time.monotonic() - started > ACTIVATION_PASS_SECONDS:
            break
    return bool(rung)


def _activate(hub, now: dt.datetime) -> None:
    """The apps due in ``hub`` set up (:func:`_activate_in`); a failure is logged, its connections released either way."""
    try:
        _activate_in(hub, now)
    except Exception:
        logger.exception("worker: the apps of %s could not be set up; the next pass tries again.", hub.slug)
    finally:
        close_hub_aliases(hub)
        close_old_connections()


def _activate_in(hub, now: dt.datetime) -> None:
    """Read what is due in ``hub``'s database; make its tables, unless the request or the database is of a newer code
    than this worker's; settle the rows with how it went."""
    with use_hub(hub):
        due = queries.apps.activations_due(now)
        if not due:
            # Rung for nothing due now (a retry still to come, or nothing left): its ring moves to what is next, or ends.
            services.activation.activations_rung_at(hub.pk, queries.apps.activation_next_at())
            return
    apps, error = sorted(due), ""
    code = _code()
    newer = sorted(label for label, target in due.items() if target and (label, target) not in code.nodes)
    # Only what it makes counts: the platform or another app of a later code (a rollback) never holds it back, as the
    # migrator ignores what it does not know.
    making = set(apps) | activation.needs(apps, activation.module_graph())
    ahead = sorted(
        label
        for label, name in (hub.schema_apps or {}).items()
        if label in making and label in code.leaves and (label, name) not in code.nodes
    )
    if newer or ahead:
        outcome = "newer_code"
        logger.warning(
            "base.app.activation_newer_code hub=%s apps=%s: asked by (%s) or a database at (%s) a newer code than this "
            "worker's; left to a worker of that code.",
            hub.slug, ",".join(apps), ",".join(newer) or "-", ",".join(ahead) or "-",
        )
    else:
        try:
            migrator.ensure_schema(hub, add=apps, lock_wait=ACTIVATION_LOCK_WAIT)
            outcome = "created"
        except migrator.SchemaLocked:
            outcome = "locked"
        except Exception as failure:
            outcome, error = "failed", f"{type(failure).__name__}: {failure}"
            logger.exception("worker: the tables of %s could not be made in %s.", ",".join(apps), hub.slug)
    ctx = OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}), language="en")
    with use_control():
        hub = services.provisioning.registry_row(hub.pk)
    with use_hub(hub):
        get_operation("base.app.activation_settle")(ctx, schemas.apps.AppActivationSettleIn(apps=apps, outcome=outcome, error=error))


@cache
def _code() -> migrator.CodeMigrations:
    """This code's migration graph (its leaves and nodes): it never changes while the process runs."""
    return migrator.code_migrations()

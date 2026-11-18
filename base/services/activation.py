"""The worker's side of the apps being set up: the hubs it looks into, their ring and
``base.app.activation_settle``.
"""

import datetime as dt
import logging
from functools import partial
from uuid import UUID

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict
from live.operations import INTERNAL, operation
from live.operations import on_commit as after_commit
from live.outbox import record_event

from base import activation, events, queries, registry
from base.activation import CREATING, FAILED, ON
from base.models import AppActivation, Hub
from base.registry import internal_only
from base.schemas.apps import AppActivationSettleIn, AppActivationSettleOut
from base.services.apps import _business_hub, _locked_states, _write_states, apps_created
from base.services.blueprints import _load_what_waited
from base.services.photo import _sync_photo_blocks
from base.services.provisioning import LAST_ERROR_MAX, _control_transaction, offboarding_due
from base.services.reset import has_own_database
from control.models import HubDue, HubVisit

logger = logging.getLogger(__name__)


#: The waits before the worker makes the tables of an app that failed again: 1 min, 5 min, 15 min, then every hour (as a
#: hub's preparation).
ACTIVATION_RETRY_SECONDS = (60, 300, 900, 3600)
#: How long an app waits when another run holds its hub's schema: the activation is queued again.
ACTIVATION_LOCKED_SECONDS = 30
#: How long an app asked by a newer code waits for a worker of that code: any other worker queues it again.
ACTIVATION_NEWER_CODE_SECONDS = 60
#: How long an app waits for a worker of its code before it fails as ``code_behind`` (the
#: alarm's threshold, ``activation.STUCK_AFTER``): after a rollback none is coming, and the business tries again, asked
#: by the code that runs now.
ACTIVATION_CODE_BEHIND_AFTER = activation.STUCK_AFTER


def activation_hubs(now: dt.datetime) -> list[Hub]:
    """The hubs whose apps the worker sets up now: ready, with their own database, whose ``hub_due`` came and
    nobody holds. Never one being made, dropped or gone, a demo whose time is up, nor one moving to another cluster or
    being restored (``registry.copying``: tables made while its database is copied would stay behind; its ring waits
    for the copy). By id."""
    return list(
        Hub.objects.filter(status=Hub.Status.READY)
        .exclude(registry.copying())
        .exclude(db_name="")
        .exclude(is_demo=True, expires_at__lte=now)
        .filter(due__due_at__lte=now)
        .filter(Q(due__lease_until__isnull=True) | Q(due__lease_until__lte=now))
        .select_related("cluster")
        .order_by("id")
    )


def ring_activations(hub: Hub, at: dt.datetime) -> None:
    """``hub`` has apps to set up by ``at``: due in ``hub_due`` then, or earlier if it already is (the sweep's ring)."""
    with _control_transaction():
        HubDue.mark_due(hub, at)


def activations_rung_at(hub_id: UUID, at: dt.datetime | None) -> None:
    """After the worker looked into a ready hub's apps: its ring moves to ``at`` (the next of them to set up: a retry,
    one put off), or ends with ``None``, unless the hub has other work due (a reset, the copy of a business that left)
    or another worker holds its row. The pass over the hubs due leaves a ready hub's ring alone (``claim_next_due_hub``),
    so its time is kept."""
    now = timezone.now()
    with _control_transaction():
        hub = Hub.objects.filter(pk=hub_id).first()
        due = HubDue.objects.select_for_update().filter(pk=hub_id).first()
        if hub is None or (due is not None and due.lease_until is not None and due.lease_until > now):
            return
        if at is not None:
            if due is None:
                HubDue.mark_due(hub, at)
            else:
                HubDue.objects.filter(pk=hub_id).update(due_at=at)
        elif due is not None and hub.reset_requested_at is None and not offboarding_due(hub):
            due.delete()


def hubs_visited_since(day: dt.date) -> frozenset[str]:
    """The hubs (by slug) someone had activity in since ``day`` (a login, or anything done in a session that stayed open:
    ``base.meter``): the active ones, which the sweep looks into more often."""
    return frozenset(HubVisit.objects.filter(day__gte=day).values_list("host", flat=True).distinct())


def _activation_retry_delay(attempts: int) -> dt.timedelta:
    """How long an app whose tables failed ``attempts`` times in a row waits before the next try."""
    return dt.timedelta(seconds=ACTIVATION_RETRY_SECONDS[min(attempts, len(ACTIVATION_RETRY_SECONDS)) - 1])


# Not an assistant tool: the worker's step after making a hub's tables, no person.
@operation(
    "base.app.activation_settle",
    kind="command",
    permission=None,
    input=AppActivationSettleIn,
    output=AppActivationSettleOut,
    ai=INTERNAL,
)
def app_activation_settle(ctx: OperationContext, data: AppActivationSettleIn) -> dict:
    """The worker's step after ``ensure_schema`` in a hub's own database (``base.worker``), as the platform.

    Of the apps it took that are still waiting (``creating``, or ``failed``: one turned off meanwhile stays off, its
    tables made): ``created`` turns on those whose tables the hub now has (``base.app.enabled``, one per app the business
    chose, with what came along; then their photo's blocks, as an app turned on at once) and leaves the rest ``failed``;
    ``failed`` leaves them ``failed`` with ``attempts`` + 1, the error and the next try (1, 5, 15 min, then every hour;
    ``base.app.activation_failed``); ``locked`` and ``newer_code`` put them off (30 s, 60 s), still ``creating``. Never
    on a shared database (409 ``base.app_shared_database``); only the platform runs it, anyone else refused
    before anything is read (as ``base.hub.reset_apply``)."""
    internal_only(ctx)
    host = ctx.scope.key
    hub = _business_hub(ctx)
    if not has_own_database(hub):
        raise Conflict(
            gettext("This business shares its database: its apps are turned on at once."),
            code="base.app_shared_database",
        )
    with activation.changing(host):
        graph = activation.module_graph()
        current = _locked_states(ctx, graph)
        now = timezone.now()
        asked = [label for label in dict.fromkeys(data.apps) if label in current and current[label].state in (CREATING, FAILED)]
        after_commit(partial(activation.forget, host))
        after_commit(partial(_ring_next, hub, host))
        behind: list[str] = []
        if data.outcome == "newer_code":
            # Waited for a worker of its code since it was asked for (``changed_at``): after a rollback none is coming.
            since = dict(AppActivation.objects.filter(host=host, app__in=asked).values_list("app", "changed_at"))
            behind = [label for label in asked if since[label] <= now - ACTIVATION_CODE_BEHIND_AFTER]
        if data.outcome == "locked" or (data.outcome == "newer_code" and not behind):
            wait = ACTIVATION_LOCKED_SECONDS if data.outcome == "locked" else ACTIVATION_NEWER_CODE_SECONDS
            AppActivation.objects.filter(host=host, app__in=asked).update(next_attempt_at=now + dt.timedelta(seconds=wait))
            return {"on": [], "failed": [], "waiting": asked}
        created = apps_created(hub)
        made = [label for label in asked if data.outcome == "created" and (created is None or label in created)]
        failed = behind or [label for label in asked if label not in made]
        if made:
            _write_states(host, {label: activation.Activation(ON, current[label].chosen) for label in made})
            if hub is not None and not hub.is_demo:
                _sync_photo_blocks(hub, made)
            _record_enabled(ctx, made, current, graph)
            _load_what_waited(ctx, made)
        if failed:
            kind = {"failed": "schema_failed", "newer_code": "code_behind"}.get(data.outcome, "not_created")
            error = {
                "schema_failed": data.error,
                "code_behind": "code_behind: asked by a code no worker runs any more (a rollback): turn it on again.",
                "not_created": "not_created: the migrator ended without its tables.",
            }[kind]
            for label in failed:
                attempts = AppActivation.objects.get(host=host, app=label).attempts + 1
                AppActivation.objects.filter(host=host, app=label).update(
                    state=FAILED,
                    attempts=attempts,
                    last_error=error[:LAST_ERROR_MAX],
                    next_attempt_at=now + _activation_retry_delay(attempts),
                    changed_at=now,
                )
            record_event(ctx, events.APP_ACTIVATION_FAILED, {"apps": failed, "error": kind})
            logger.warning("base.app.activation_failed hub=%s apps=%s: %s", host, ",".join(failed), error[:300])
        return {"on": made, "failed": failed, "waiting": []}


def _ring_next(hub: Hub, host: str) -> None:
    """After the COMMIT of a settle (inside the hub's database): its ring moves to the next app to set up, or ends."""
    activations_rung_at(hub.pk, queries.apps.activation_next_at(host))


def _record_enabled(
    ctx: OperationContext, made: list[str], current: dict[str, activation.Activation], graph: dict
) -> None:
    """``base.app.enabled`` for each app the business chose that went on, with what came along with it; one that came
    along with none of them (its chooser on already) gets its own."""
    chosen = [label for label in made if current[label].chosen]
    along_any: set[str] = set()
    for label in chosen:
        along = sorted(other for other in made if other not in chosen and other in activation.needs([label], graph))
        along_any.update(along)
        record_event(ctx, events.APP_ENABLED, {"app": label, "along": along})
    for label in made:
        if label not in chosen and label not in along_any:
            record_event(ctx, events.APP_ENABLED, {"app": label, "along": []})

"""The reset of a business: ``base.hub.reset`` and ``base.hub.reset_apply`` (only with the hub's own database).

Asked by who runs it (``base.hub.reset``), done by the worker (``base.worker``, the data pass): a copy of its database
first (``base.tenancy.dumps``, ``reset``) and, only if it was kept, the sections emptied in its database
(``base.hub.reset_apply``), the event ``base.hub.data_reset`` recorded there. ``Hub.reset_requested_at`` is set while
it is to do; ``Hub.reset_sections`` keeps what was asked and how it went, for Settings › Data (``base.hub.dumps``):
``state`` copying → emptying → done, or failed with its ``error`` (``dumps_unavailable``, ``dump_failed``,
``emptying_failed``, ``hub_not_ready``) and nothing emptied. Each step is told to the hub's live queries after its
COMMIT in control (``base.hub.reset_progressed``).
"""

import datetime as dt
import unicodedata
from functools import partial
from uuid import UUID

from django.utils import timezone, translation
from django.utils.translation import gettext
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload, OperationError
from live.operations import AI, INTERNAL, on_commit, operation
from live.outbox import notify, record_event

from base import blueprint, events
from base.models import Hub
from base.permissions import ADMINISTER_HUB
from base.registry import internal_only
from base.schemas import HubResetApplyIn, HubResetApplyOut, HubResetIn, HubResetOut
from base.services.blueprints import _stop_waiting, _waiting_loads, _who
from base.services.provisioning import LEASE_OWNER, ProvisioningStopped, _control_transaction, _leased
from control.models import HubDue


def same_name(typed: str, name: str) -> bool:
    """The name typed is the business's: spaces around and inside collapsed, case ignored, accents kept — what the
    confirmation dialog of the screen (``ConfirmDialog`` of ``@erplora/ui``) already asked."""

    def tidy(text: str) -> str:
        return " ".join(unicodedata.normalize("NFC", text).split()).casefold()

    return tidy(typed) == tidy(name)


def has_own_database(hub: Hub | None) -> bool:
    """The hub keeps its business in its own database: emptying it touches no other hub.

    Every business served has one (``base.tenancy.cut``); one without it (one that shared a database, before its cut)
    is never served, and only the suite's tests written before the tenancy still run one (``base/tenancy/tests/legacy.py``),
    where an app's rows are everyone's: a reset would empty them for all, so these refusals stay.
    """
    return bool(hub is not None and hub.db_name)


@operation(
    "base.hub.reset",
    kind="command",
    permission=ADMINISTER_HUB,
    input=HubResetIn,
    output=HubResetOut,
    ai=AI(
        description=(
            "With dry_run, says what each app of this business would lose if emptied and what name must be typed to "
            "confirm. Without it, given the business's name typed exactly, copies all of the business's data and then "
            "empties the apps chosen for good, in the background: Settings › Data shows when it is done and keeps the "
            "copy."
        ),
        risk="high",
        # Only for live.E020 (it checks the whole app): base.assistant.tools.NOT_FROM_CHAT keeps this out of the chat
        # (pinned by base/tests/test_assistant.py).
        asks={
            "en": ("wipe all the data and start over", "empty the business, I want to start from scratch"),
            "es": ("borra todos los datos y empezamos de cero", "vacía el negocio, quiero empezar de nuevo"),
        },
    ),
)
def hub_reset(ctx: OperationContext, data: HubResetIn) -> dict:
    """The plan of what each app would lose, or the reset of the apps chosen asked, with the business's name typed:
    a copy of its database first, by the worker, and only then the sections emptied («The reset of a business»,
    below).

    Without the business's own database the reset is refused before anything of it is read; without a
    bucket for its copy it is unavailable (503); while one runs, a second one waits for it (409)."""
    from base.tenancy import dumps

    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        available = has_own_database(hub)
        if not data.dry_run and not available:
            raise Conflict(
                gettext(
                    "Resetting the business is not available yet. Undo a load instead, or remove what you want "
                    "from each app."
                ),
                code="base.reset_shared_database",
            )
        confirm_with = hub.name.strip() if hub and hub.name.strip() else ctx.scope.key
        sections = blueprint.reset_plan(ctx)
        answer = {
            "dry_run": data.dry_run,
            "confirm_with": confirm_with,
            "available": available,
            "sections": sections,
            "apps": [],
            "status": "planned",
        }
        if data.dry_run:
            return answer
        chosen = list(dict.fromkeys(data.apps))
        offered = {section["id"] for section in sections}
        if not chosen or not set(chosen) <= offered:
            raise InvalidPayload(
                gettext("Choose what to empty."),
                fields={"apps": gettext("Choose at least one section of the list, one that has rows.")},
            )
        if not same_name(data.confirm, confirm_with):
            raise InvalidPayload(
                gettext("The name does not match."),
                fields={"confirm": gettext("Type the business's name exactly as it is shown.")},
            )
        if not dumps.configured():
            raise _dumps_unavailable()
        reset_requested(hub.id, chosen, language=ctx.language, requested_by=_who(ctx), now=timezone.now())
        on_commit(partial(reset_progressed, hub.slug))
        return {**answer, "status": "copying"}



#: The states of a reset; a failed one is asked again from the screen («Try again»).
RESET_STATES = ("copying", "emptying", "done", "failed")


def _dumps_unavailable() -> OperationError:
    return OperationError(
        gettext("The copy of the data cannot be made right now, so nothing was emptied. Try again later."),
        code="base.dumps_unavailable",
        status=503,
    )


def reset_progressed(slug: str) -> None:
    """Tell the hub's live queries that its reset moved on (after the COMMIT that moved it)."""
    notify(Scope("host", slug), [events.HUB_RESET_PROGRESSED])


def reset_requested(hub_id: UUID, apps: list[str], *, language: str, requested_by: str, now: dt.datetime) -> None:
    """Ask for the reset of ``apps`` on ``hub_id``: due for the worker now. ``base.reset_in_progress`` while another
    one is to do."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        if hub.reset_requested_at is not None:
            raise Conflict(
                gettext("The business is already being reset. Wait for it to finish."), code="base.reset_in_progress"
            )
        hub.reset_requested_at = now
        hub.reset_sections = {
            "apps": list(apps),
            "language": language,
            "requested_by": requested_by,
            "state": "copying",
            "error": "",
            "removed": [],
            "dump": None,
            "finished_at": None,
        }
        hub.save(update_fields=["reset_requested_at", "reset_sections", "updated_at"])
        HubDue.mark_due(hub, now)


def reset_moved(hub_id: UUID, *, state: str, owner: str = LEASE_OWNER, **changes) -> Hub:
    """Note that the reset of ``hub_id`` moved to ``state`` (with ``changes``: its ``error``, ``dump``, ``removed``),
    under ``owner``'s lease (``ProvisioningStopped`` when another worker holds it now); a done or failed one is no
    longer to do. Its live queries hear it after the COMMIT."""
    if state not in RESET_STATES:
        raise ValueError(f"No such state of a reset: {state!r}.")
    now = timezone.now()
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        _holds(hub_id, owner, now)
        sections = {**(hub.reset_sections or {}), **changes, "state": state}
        if state in ("done", "failed"):
            sections["finished_at"] = now.isoformat()
            hub.reset_requested_at = None
        hub.reset_sections = sections
        hub.save(update_fields=["reset_requested_at", "reset_sections", "updated_at"])
    reset_progressed(hub.slug)
    return hub


def _holds(hub_id: UUID, owner: str, now: dt.datetime) -> None:
    """``ProvisioningStopped`` unless ``owner`` holds the lease of ``hub_id`` now: what another worker took over is
    left to it."""
    if not HubDue.objects.filter(pk=hub_id, lease_owner=owner, lease_until__gt=now).exists():
        raise ProvisioningStopped(f"the lease of {hub_id} is no longer {owner}'s: another worker holds it now.")


def renew_lease(hub_id: UUID, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> None:
    """Renew ``owner``'s lease of ``hub_id`` for ``lease`` from now (a long copy's heartbeat);
    ``ProvisioningStopped`` when another worker holds it now."""
    with _control_transaction():
        _leased(hub_id, timezone.now(), lease, owner)


# Not an assistant tool: the worker's step of a reset it already copied, no person.
@operation(
    "base.hub.reset_apply",
    kind="command",
    permission=None,
    input=HubResetApplyIn,
    output=HubResetApplyOut,
    ai=INTERNAL,
)
def hub_reset_apply(ctx: OperationContext, data: HubResetApplyIn) -> dict:
    """Empty the sections of a reset whose copy was kept (``base.worker``), in the hub's own database, in one
    transaction: every row of them goes, or none (a failure rolls back the rows already removed). Never on a
    shared database; only the platform runs it, refused to anyone else first."""
    internal_only(ctx)
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    if not has_own_database(hub):
        raise Conflict(
            gettext("Resetting the business is not available yet. Undo a load instead, or remove what you want from each app."),
            code="base.reset_shared_database",
        )
    chosen = list(dict.fromkeys(data.apps))
    with translation.override(ctx.language):
        removed = blueprint.reset(ctx, chosen)
    _stop_waiting(ctx, _waiting_loads(), None, blueprint.STOPPED_RESET)
    record_event(ctx, events.HUB_DATA_RESET, {"apps": chosen})
    return {"apps": removed["apps"]}

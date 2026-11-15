"""Writes of base. The control plane has modules of its own, which this package imports so their operations are
registered: the sessions the SaaS opens (``sessions``), the scheduled tasks' clock and the outbox relay
(``relay_runs``), the registry of hubs (``hub_registry``), the worker's provisioning and its leases
(``provisioning``), the demos (``demos``) and the SaaS's photo applied in a business's database (``photo``).

Settings › Data: ``base.blueprint.import`` loads a template or a file and keeps
it as an ``ImportBatch``, ``base.import.undo`` removes exactly what one load created and ``base.hub.reset`` empties the
apps chosen (only with the hub's own database); the rules are ``base.blueprint``'s.
"""

import base64
import binascii
import datetime as dt
import hashlib
import io
import json
import logging
import secrets
import time
import unicodedata
from collections.abc import Collection, Iterable, Mapping
from functools import partial
from urllib.parse import urlencode
from uuid import UUID

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import F, PositiveIntegerField, Q, Value
from django.db.models.functions import Greatest
from django.http import HttpRequest
from django.utils import timezone, translation
from django.utils.translation import gettext, ngettext
from live.context import OperationContext, Scope
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied, Unauthorized
from live.operations import get as get_operation
from live.operations import AI, INTERNAL, atomic, operation
from live.operations import on_commit
from live.outbox import notify, record_event
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from base import access, auth, blueprint, events, files, queries, registry, signing, system
from base.access import CREDENTIAL_SESSION_KEY
from base import assistant
from base.registry import hub_answer, internal_only
from base.middleware import session_host
from base.models import (
    AccessSettings,
    Credential,
    EventDelivery,
    Hub,
    ImportBatch,
    Membership,
    Profile,
    SessionOwner,
    TrustedDevice,
)
from base.media import AVATARS_FOLDER
from base.operations import hub_id
from base.storage import hub_prefix
from base.permissions import ADMINISTER_HUB, OPEN_MANAGEMENT, VIEW_HOME
from base import people as people_rules
from base.schemas import (
    ApiKeyCreateIn,
    ApiKeyIdIn,
    ApiKeyRevokeOut,
    ApiKeyTokenOut,
    BadgeSetIn,
    PersonDetailOut,
    PersonIn,
)
from base import api_keys
from base.models import ApiKey
from base.throttle import client_key
from control.models import HubActivityDaily, HubDue, HubDump, HubUsageDaily, HubVisit, UsageRun
from django.db.models import Exists, OuterRef
from base.schemas import (
    BlueprintImportIn,
    BlueprintSourceIn,
    BlueprintSummaryOut,
    FailedEventCountOut,
    FailedEventDiscardIn,
    FailedEventIn,
    FailedEventOutId,
    FailedEventRetryAllIn,
    FileDeletedOut,
    FileDeleteIn,
    FileFolderCreateIn,
    FileMoveIn,
    FilePathOut,
    FileRenameIn,
    FileSavedOut,
    FileUploadIn,
    HubGetIn,
    HubOut,
    HubResetApplyIn,
    HubResetApplyOut,
    HubResetIn,
    HubResetOut,
    ImportOut,
    ImportUndoIn,
    ImportUndoOut,
    AccessSettingsIn,
    AccessSettingsOut,
    AccessSettingsUpdateIn,
    AvatarIn,
    AvatarOut,
    AvatarRemoveIn,
    DeviceByIdIn,
    DeviceCurrentOut,
    DeviceModeIn,
    DevicePruneIn,
    DevicePruneOut,
    DeviceRemoveOut,
    DeviceRenameIn,
    PinSetIn,
    PinSetOut,
    PreferencesIn,
    PreferencesOut,
    ProfileIn,
    ProfileOut,
    ProfileUpdateIn,
)

from . import demos as demos, relay_runs as relay_runs
from .hub_registry import LEFT_STATUSES, _locked_hub
from .photo import _sync_photo_blocks
from .provisioning import (
    LAST_ERROR_MAX,
    LEASE_OWNER,
    ProvisioningStopped,
    SERVED_STATUSES,
    _control_transaction,
    _free,
    _leased,
    _take,
    claim_hub,
    offboarding_due,
    retry_delay,
)
from .sessions import SAAS_USERNAME_PREFIX, _end_other_devices, _end_sessions, _entered, _log_in, ensure_hub_user

logger = logging.getLogger(__name__)


# ── Data: blueprints, imports and reset ───────────────


def _who(ctx: OperationContext) -> str:
    actor = ctx.actor
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.get_username())[:150]
    return str(actor)[:150]


@operation(
    "base.blueprint.inspect",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=BlueprintSourceIn,
    output=BlueprintSummaryOut,
    ai=AI(
        description="Says what a template of the catalogue brings, app by app, before loading it; it writes nothing.",
        asks={
            "en": ("what does the hair salon template bring?", "before loading it, what's inside the bar template?"),
            "es": (
                "antes de cargarla, ¿qué incluye la plantilla de bar?",
                "¿qué viene en la plantilla de restaurante?",
            ),
        },
    ),
)
def blueprint_inspect(ctx: OperationContext, data: BlueprintSourceIn) -> dict:
    """What a template or an uploaded file brings and what of it would load here.

    It writes nothing: a command only because its input is a file, which no query string carries (a query is served
    by GET), like the rehearsal (``dry_run``) of the apps' imports.
    """
    with translation.override(ctx.language):
        bundle, seed = blueprint.open_source(data.template, data.file_base64)
        return blueprint.summary(ctx, bundle, seed=seed)


@operation(
    "base.blueprint.import",
    kind="command",
    permission=ADMINISTER_HUB,
    input=BlueprintImportIn,
    output=ImportOut,
    ai=AI(
        description=(
            "Loads a template of the catalogue (a restaurant, a hair salon…) into this business: turns on its apps "
            "that are off (with the apps they need, within the plan's limit of apps), then loads its menu or services, "
            "its tables and the rest of its apps' data, app by app; what is already there is left as it was. An app "
            "still being set up («waiting») brings its data by itself when it is ready: nothing to do but say so. "
            "Returns the report of what went in, with why an app could not be turned on. Never brings people, PINs or "
            "fiscal data. Use this, not blueprint.list or blueprint.inspect, when asked to load, import or apply one."
        ),
        risk="high",
        asks={
            "en": (
                "load the restaurant template",
                "set me up like a hair salon",
                "fill the business with the café starter menu",
                "import the restaurant template",
            ),
            "es": (
                "carga la plantilla de restaurante",
                "quiero empezar con la plantilla de bar",
                "importa la plantilla de restaurante",
            ),
        },
    ),
)
def blueprint_import(ctx: OperationContext, data: BlueprintImportIn) -> dict:
    """Load a template, a file or what a load left out and keep its report and the rows it created.

    First it turns on the apps the blueprint lists that are off (a hub is born with every app off),
    each through ``base.app.enable`` and in this transaction; one refused (the plan's limit, no right to it) stays
    off, loads nothing and its report says why. A backup turns on the apps it lists too. One whose tables its hub's
    database is still making (``creating``) is waited for: a template's part of it loads when the worker turns it on
    (``_load_what_waited``); a file is not kept, so its report says to upload it again."""
    with translation.override(ctx.language):
        retried = None
        if data.retry_of is not None:
            retried = ImportBatch.objects.select_for_update().filter(pk=data.retry_of).first()
            if retried is None:
                raise NotFound(gettext("This load is not there any more."), code="base.import_not_found")
            blocked = blueprint.retry_state(ctx, retried)
            if blocked:
                code, message = blueprint.RETRY_BLOCKED[blocked]
                raise Conflict(str(message), code=code)
            bundle, seed = blueprint.open_source(retried.template_key, "")
            apps = list(retried.apps)
            # What it still waited for (an app whose setup failed) is this load's now: one report, one load of it.
            _stop_waiting(ctx, [retried], None, blueprint.STOPPED_RETRIED)
        else:
            bundle, seed = blueprint.open_source(data.template, data.file_base64)
            apps = list(dict.fromkeys(data.apps)) if data.apps is not None else []
        # A hub is born with every app off. The apps the blueprint lists are turned on first, and
        # what loads reads its rows, never the cache of the apps off kept before this change.
        with activation.changing(ctx.scope.key):
            refused = _turn_on_listed(ctx, bundle.manifest["apps"], set(apps))
            waiting = _being_set_up(ctx, bundle.manifest["apps"], set(apps)) - refused.keys()
            if seed is None:
                refused |= dict.fromkeys(waiting, str(blueprint.FILE_BEING_SET_UP))
                waiting = set()
            applied = blueprint.apply(ctx, bundle, apps=set(apps) if apps else None, refused=refused, waiting=waiting)
        load = ImportBatch.objects.create(
            name=bundle.manifest["name"],
            source=ImportBatch.Source.CATALOG if seed else ImportBatch.Source.FILE,
            template_key=seed.key if seed else "",
            template_version=seed.version if seed else "",
            purpose=bundle.manifest["purpose"],
            apps=apps,
            status=applied.report["status"],
            report=applied.report,
            created_rows=applied.created,
            created_by=_who(ctx),
            retry_of=retried,
        )
        record_event(ctx, events.BLUEPRINT_IMPORTED, {"id": str(load.pk), "status": load.status})
        return blueprint.describe_load(ctx, load)


@operation(
    "base.import.undo",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ImportUndoIn,
    output=ImportUndoOut,
    ai=AI(
        description=(
            "Undoes one load of a template or a file: removes exactly the rows it brought; what was made afterwards "
            "stays."
        ),
        risk="high",
        asks={
            "en": ("undo the template I just loaded", "take back that import, it was the wrong file"),
            "es": ("deshaz la plantilla que acabo de cargar", "echa atrás esa importación, era el archivo equivocado"),
        },
    ),
)
def import_undo(ctx: OperationContext, data: ImportUndoIn) -> dict:
    """Remove exactly the rows one load created, once."""
    with translation.override(ctx.language):
        load = ImportBatch.objects.select_for_update().filter(pk=data.id).first()
        if load is None:
            raise NotFound(gettext("This load is not there any more."), code="base.import_not_found")
        if load.undone_at is not None:
            raise Conflict(gettext("This load was undone already."), code="base.import_undone")
        removed = blueprint.undo(ctx, load.created_rows)
        _stop_waiting(ctx, [load], None, blueprint.STOPPED_UNDONE)
        load.undone_at = timezone.now()
        load.save(update_fields=["undone_at"])
        record_event(ctx, events.IMPORT_UNDONE, {"id": str(load.pk)})
        return {"id": load.pk, "apps": removed["apps"]}


# ── The nightly use of each business (base.usage) ──────────────────────────────────────────────────────────────────


def usage_run_claim(day: dt.date, now: dt.datetime, takeover: dt.timedelta) -> bool:
    """Claim the measurement of ``day``: whether this worker measures it (no run yet, or one left unfinished for
    ``takeover``); a finished night is never measured again."""
    with _control_transaction():
        run = UsageRun.objects.select_for_update().filter(day=day).first()
        if run is None:
            UsageRun.objects.create(day=day, started_at=now)
            return True
        if run.finished_at is not None or run.started_at > now - takeover:
            return False
        run.started_at = now
        run.save(update_fields=["started_at"])
        return True


def usage_run_finished(day: dt.date, hubs: int, now: dt.datetime) -> None:
    with _control_transaction():
        UsageRun.objects.filter(day=day).update(finished_at=now, hubs=hubs)


def usage_ready(day: dt.date) -> bool:
    """Whether the night of ``day`` was measured to its end."""
    return UsageRun.objects.filter(day=day, finished_at__isnull=False).exists()


def hubs_to_measure() -> tuple[list[Hub], int]:
    """The hubs with their own database whose use is measured (a ready one, a business that left with its database
    finished; never a demo, nor one being made, dropped or gone), and how many hubs still share control's."""
    with_own = (
        Hub.objects.exclude(db_name="")
        .filter(Q(status=Hub.Status.READY) | Q(status__in=SERVED_STATUSES, ready_at__isnull=False))
        .filter(is_demo=False)
        .select_related("cluster")
        .order_by("id")
    )
    shared = Hub.objects.filter(db_name="", is_demo=False, status__in=SERVED_STATUSES).count()
    return list(with_own), shared


def active_people(host: str, day: dt.date, window_days: int) -> tuple[int, int]:
    """The people with activity in ``host`` on ``day``, and in the ``window_days`` that end it."""
    visits = HubVisit.objects.filter(host=host)
    on_day = visits.filter(day=day).values("saas_user_id").distinct().count()
    in_window = (
        visits.filter(day__gt=day - dt.timedelta(days=window_days), day__lte=day)
        .values("saas_user_id")
        .distinct()
        .count()
    )
    return on_day, in_window


def usage_recorded(  # noqa: PLR0913
    hub_id: UUID,
    day: dt.date,
    *,
    db_bytes: int,
    s3_bytes: int,
    active_users_1d: int,
    active_users_30d: int,
    now: dt.datetime,
) -> None:
    """Keep what ``hub_id`` used on ``day`` (measured again, its figures replace the day's); its live queries hear it
    after the COMMIT."""
    with _control_transaction():
        HubUsageDaily.objects.update_or_create(
            hub_id=hub_id,
            day=day,
            defaults={
                "db_bytes": db_bytes,
                "s3_bytes": s3_bytes,
                "active_users_1d": active_users_1d,
                "active_users_30d": max(active_users_30d, active_users_1d),
                "measured_at": now,
            },
        )
        slug = Hub.objects.filter(pk=hub_id).values_list("slug", flat=True).first()
    if slug:
        notify(Scope("host", slug), [events.HUB_USAGE_MEASURED])


def activity_recorded(hub_id: UUID, day: dt.date, *, requests: int = 0, peak: int = 0, busy: int = 0) -> bool:
    """Add what a process counted of ``hub_id`` on ``day`` (``base.meter``) to its row, made if it is the first; several
    tasks write at once, so it is added in the database, never read first. ``False``: the hub is gone, nothing to keep."""

    def add() -> int:
        return HubActivityDaily.objects.filter(hub_id=hub_id, day=day).update(
            requests=F("requests") + requests,
            peak_connections=Greatest(F("peak_connections"), Value(peak), output_field=PositiveIntegerField()),
            busy_requests=F("busy_requests") + busy,
        )

    with _control_transaction():
        if add():
            return True
        if not Hub.objects.filter(pk=hub_id).exists():
            return False
        _, created = HubActivityDaily.objects.get_or_create(
            hub_id=hub_id,
            day=day,
            defaults={"requests": requests, "peak_connections": peak, "busy_requests": busy},
        )
        if not created:  # another task made it meanwhile
            add()
    return True


def people_seen(host: str, day: dt.date, last_seen: Mapping[str, dt.datetime]) -> None:
    """Note who had activity in ``host`` on ``day`` and when last (``base.meter``): their visit of the day, made if it is
    the first. Two tasks may write out of order by up to a pass: a moment against a window of minutes, which it does not
    change, so one upsert is enough."""
    with _control_transaction():
        HubVisit.objects.bulk_create(
            [
                HubVisit(host=host, day=day, saas_user_id=person, last_seen_at=moment)
                for person, moment in last_seen.items()
            ],
            update_conflicts=True,
            unique_fields=["host", "day", "saas_user_id"],
            update_fields=["last_seen_at"],
        )


def expired_dumps_forgotten(*, before: dt.datetime) -> int:
    """Forget the copies made before ``before``: the bucket's lifecycle rule deleted them (90 days)."""
    with _control_transaction():
        forgotten, _ = HubDump.objects.filter(created_at__lt=before).delete()
    return forgotten


def visits_forgotten(*, before: dt.date) -> int:
    """Forget the visits older than ``before``: no window counts them any more."""
    with _control_transaction():
        forgotten, _ = HubVisit.objects.filter(day__lt=before).delete()
    return forgotten


# ── The copies of a hub's data (base.tenancy.dumps) ──────────────────────────────────────────────────────────────────


def dump_key_taken(key: str) -> bool:
    """Whether a copy is already kept at ``key`` (two copies of a hub in the same second get the next second)."""
    from base.tenancy.context import use_control

    with use_control():
        return HubDump.objects.filter(key=key).exists()


def dump_recorded(  # noqa: PLR0913
    hub_id: UUID, *, kind: str, key: str, size: int, created_at: dt.datetime, requested_by: str = ""
) -> HubDump:
    """Keep in control the copy of ``hub_id`` just uploaded to ``key``."""
    with _control_transaction():
        return HubDump.objects.create(
            hub_id=hub_id, kind=kind, key=key, bytes=size, created_at=created_at, requested_by=requested_by[:150]
        )


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
        # Only for live.E020 (it checks the whole app): base.assistant.NOT_FROM_CHAT keeps this out of the chat
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


# ── The reset of a business ─────────────────────────────────────────────────────────────────────────────────────────
# Asked by who runs it (``base.hub.reset``), done by the worker (``base.worker``, the data pass): a copy of its database
# first (``base.tenancy.dumps``, ``reset``) and, only if it was kept, the sections emptied in its database
# (``base.hub.reset_apply``), the event ``base.hub.data_reset`` recorded there. ``Hub.reset_requested_at`` is set while
# it is to do; ``Hub.reset_sections`` keeps what was asked and how it went, for Settings › Data (``base.hub.dumps``):
# ``state`` copying → emptying → done, or failed with its ``error`` (``dumps_unavailable``, ``dump_failed``,
# ``emptying_failed``, ``hub_not_ready``) and nothing emptied. Each step is told to the hub's live queries after its
# COMMIT in control (``base.hub.reset_progressed``).

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


# ── A business that leaves: its copy ───────────────────────────────────────────────────────────────────────────────
# ``base.hub.cancel`` makes a business with a finished database of its own due; the worker copies it once
# (``offboarding``) and the database stays (its 90 days; ``restore`` brings it back). A copy that fails is tried again
# at ``next_attempt_at`` (1 min, 5 min, 15 min, then every hour), with ``attempts`` and ``last_error`` on the row.
# After its 90 days (``base.tenancy.offboarding``) ``archiving`` makes its final copy,
# ``dropping`` drops its database and ``base.hub.purge`` leaves the row as a tombstone.

#: How long a business that left keeps its database.
OFFBOARDING_RETENTION = dt.timedelta(days=90)
#: How long a business kept for its fiscal documents waits before it is looked at again.
FISCAL_HOLD_RECHECK = dt.timedelta(days=1)


def _offboarding_copied(hub_ref, cancelled_at) -> Exists:
    return Exists(
        HubDump.objects.filter(hub_id=hub_ref, kind=HubDump.Kind.OFFBOARDING, created_at__gte=cancelled_at)
    )


def past_retention(hub: Hub, now: dt.datetime) -> bool:
    """Whether ``hub`` is a business on its way out after its 90 days, ``now``: left that long ago, or already
    ``archiving`` or ``dropping``. Never a demo (their own way out: ``base.tenancy.provision``), the platform's hub, nor
    one moving to another cluster or being restored (its database is being copied). Its ``next_attempt_at`` says when,
    not whether."""
    if hub.is_demo or hub.is_platform or registry.is_copying(hub):
        return False
    if hub.status in (Hub.Status.ARCHIVING, Hub.Status.DROPPING):
        return True
    return (
        hub.status == Hub.Status.CANCELLED
        and hub.cancelled_at is not None
        and hub.cancelled_at <= now - OFFBOARDING_RETENTION
    )


def _next_past_retention(now: dt.datetime) -> UUID | None:
    """The business longest past its 90 days whose next attempt came and whose lease nobody holds: :func:`past_retention`,
    as a query, on the registry. They have no ``hub_due`` row until one is taken: due all at once, the pass over
    ``hub_due`` would take them too, only to give them back."""
    return (
        Hub.objects.filter(
            Q(status=Hub.Status.CANCELLED, cancelled_at__lte=now - OFFBOARDING_RETENTION)
            | Q(status__in=(Hub.Status.ARCHIVING, Hub.Status.DROPPING)),
            Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now),
            is_demo=False,
            is_platform=False,
        )
        .exclude(registry.copying())
        .exclude(Exists(HubDue.objects.filter(pk=OuterRef("pk"), lease_until__gt=now)))
        .order_by("cancelled_at", "id")
        .values_list("id", flat=True)
        .first()
    )


def claim_next_data_hub(now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> UUID | None:
    """Take for ``owner`` the lease of the hub due longest by ``now``, that nobody holds, with data work to do: a reset
    asked, or the copy of a business that left; with none, a business past its 90 days."""
    leaving = (
        Q(hub__status=Hub.Status.CANCELLED, hub__ready_at__isnull=False, hub__cancelled_at__isnull=False)
        & ~Q(hub__db_name="")
        & ~_offboarding_copied(OuterRef("hub_id"), OuterRef("hub__cancelled_at"))
    )
    with _control_transaction():
        due = (
            HubDue.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(_free(now), due_at__lte=now)
            .filter(Q(hub__reset_requested_at__isnull=False) | leaving)
            .order_by("due_at")
            .values_list("hub_id", flat=True)
            .first()
        )
        if due is not None:
            _take(due, now, lease, owner)
            return due
        leaving_for_good = _next_past_retention(now)
    if leaving_for_good is None or claim_hub(leaving_for_good, now, lease, owner=owner) is None:
        return None
    return leaving_for_good


def offboarding_copy_failed(hub_id: UUID, now: dt.datetime, error: str, *, owner: str = LEASE_OWNER) -> None:
    """The copy (or, after its 90 days, the drop) of a business that left failed: tried again at its next attempt.
    One that came back meanwhile has nothing to note."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        _holds(hub_id, owner, timezone.now())
        if hub.status not in (*LEFT_STATUSES, Hub.Status.DROPPING):
            return
        hub.attempts += 1
        hub.last_error = error[:2000]
        hub.next_attempt_at = now + retry_delay(hub.attempts)
        hub.save(update_fields=["attempts", "last_error", "next_attempt_at", "updated_at"])


def offboarding_copied(hub_id: UUID) -> None:
    """The copy of a business that left was kept: nothing more to try."""
    with _control_transaction():
        Hub.objects.filter(pk=hub_id).update(attempts=0, last_error="", next_attempt_at=None, updated_at=timezone.now())


def _next_step_out(
    hub_id: UUID, status: str, now: dt.datetime, lease: dt.timedelta, owner: str
) -> Hub | None:
    """``hub_id``, past its 90 days, moves to ``status`` (its lease renewed, its counters from zero when it changes);
    ``None`` when it is no longer on its way out: it came back, or moved."""
    with _control_transaction():
        hub = Hub.objects.select_for_update(of=("self",)).select_related("cluster").filter(pk=hub_id).first()
        if hub is None or not past_retention(hub, now):
            return None
        _leased(hub_id, now, lease, owner)
        if hub.status != status:
            hub.status = status
            hub.attempts, hub.last_error, hub.next_attempt_at = 0, "", None
            hub.save(update_fields=["status", "attempts", "last_error", "next_attempt_at", "updated_at"])
    return hub


def offboarding_archiving(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> Hub | None:
    """The final copy of the business ``hub_id`` is being made (``archiving``: it can still come back)."""
    return _next_step_out(hub_id, Hub.Status.ARCHIVING, now, lease, owner)


def offboarding_dropping(hub_id: UUID, now: dt.datetime, lease: dt.timedelta, *, owner: str = LEASE_OWNER) -> Hub | None:
    """The database of the business ``hub_id`` is going (``dropping``: from here it never comes back)."""
    return _next_step_out(hub_id, Hub.Status.DROPPING, now, lease, owner)


def offboarding_held(hub_id: UUID, now: dt.datetime, apps: Iterable[str], *, owner: str = LEASE_OWNER) -> None:
    """The business ``hub_id`` keeps fiscal documents (``apps``' own) that nothing archives yet: its database stays and
    it stays ``cancelled``, looked at again after :data:`FISCAL_HOLD_RECHECK`. Its 90 days are not counted again."""
    with _control_transaction():
        hub = Hub.objects.select_for_update().get(pk=hub_id)
        _holds(hub_id, owner, timezone.now())
        if hub.status not in LEFT_STATUSES:
            return
        hub.status = Hub.Status.CANCELLED
        hub.attempts = 0
        hub.last_error = f"fiscal_archive_missing: {', '.join(apps)}"[:LAST_ERROR_MAX]
        hub.next_attempt_at = now + FISCAL_HOLD_RECHECK
        hub.save(update_fields=["status", "attempts", "last_error", "next_attempt_at", "updated_at"])


def final_copy_kept(hub: Hub) -> bool:
    """Whether the copy of ``hub`` made after its 90 days is already kept (a drop that failed needs no second one)."""
    return HubDump.objects.filter(
        hub_id=hub.pk, kind=HubDump.Kind.OFFBOARDING, created_at__gte=hub.cancelled_at + OFFBOARDING_RETENTION
    ).exists()


# Not an assistant tool: the worker's last step of a business past its 90 days, no person.
@operation("base.hub.purge", kind="command", permission=None, input=HubGetIn, output=HubOut, ai=INTERNAL)
def hub_purge(ctx: OperationContext, data: HubGetIn) -> dict:
    """The database and the files of the business ``data.id`` went (``base.tenancy.offboarding``): its people lose their
    way in and the row stays ``purged`` as a tombstone (its host answers 410, forever), with nothing of the business on
    it: no name, no photo. Its cluster is let go, or a tombstone would keep that cluster from ever being deleted.

    Rows only, in one transaction of control. One that is not ``dropping`` is ``base.hub_not_dropping`` (a demo has
    ``base.demo.purge``); one already purged stays as it is."""
    internal_only(ctx)
    hub = _locked_hub(data.id)
    if hub.status == Hub.Status.PURGED:
        return hub_answer(hub)
    if hub.is_demo or hub.status != Hub.Status.DROPPING:
        raise Conflict(gettext("This business is not being dropped."), code="base.hub_not_dropping")
    Membership.objects.filter(host=hub.slug).delete()
    _end_sessions(SessionOwner.objects.filter(host=hub.slug))
    hub.status, hub.purged_at = Hub.Status.PURGED, timezone.now()
    hub.name, hub.state, hub.reset_sections, hub.cluster = "", {}, None, None
    hub.attempts, hub.last_error, hub.next_attempt_at = 0, "", None
    hub.save(
        update_fields=[
            "status",
            "purged_at",
            "name",
            "state",
            "reset_sections",
            "cluster",
            "attempts",
            "last_error",
            "next_attempt_at",
            "updated_at",
        ]
    )
    record_event(ctx, events.HUB_PURGED, {"id": str(hub.id), "slug": hub.slug})
    return hub_answer(hub)


# ── System: the failed events ──────────────────────────────────────────────────────────────────────────────────────
# Resend one, resend all and discard one, for who runs the business. A failed event is a delivery the relay gave up
# on (``dead``): resending puts it back in the queue for the app that had failed only; discarding closes it for good
# and keeps the row. One hub never touches another's.


@operation(
    "base.failed_event.retry",
    kind="command",
    permission=ADMINISTER_HUB,
    input=FailedEventIn,
    output=FailedEventOutId,
    ai=AI(
        description=(
            "Resends one failed event of this hub (by its id, from the list of failed events) once its cause is fixed: "
            "it goes back to the queue with its attempts at zero, for the app that could not take it only. Refused "
            "when that app is no longer on in this business."
        ),
        asks={
            "en": ("retry that failed event", "send the stuck invoicing event again"),
            "es": ("reintenta ese evento caído", "vuelve a mandar el evento de facturación que se quedó atascado"),
        },
    ),
)
def failed_event_retry(ctx: OperationContext, data: FailedEventIn) -> dict:
    """``pending`` again, due now, attempts at zero; the relay takes it on its next tick."""
    from base import relay  # base.relay imports this module

    delivery = _failed_event(ctx, data.id)
    if delivery.app_label not in relay.active_apps(ctx.scope):
        raise Conflict(
            gettext("%(app)s is not on in this business: turn it on, then resend the event.")
            % {"app": system.app_name(delivery.app_label)},
            code="base.failed_event_app_off",
        )
    _requeue([delivery.pk])
    record_event(ctx, events.FAILED_EVENT_RETRIED, {"id": str(delivery.pk), "count": 1})
    return {"id": delivery.pk}


@operation(
    "base.failed_event.retry_all",
    kind="command",
    permission=ADMINISTER_HUB,
    input=FailedEventRetryAllIn,
    output=FailedEventCountOut,
    ai=AI(
        description=(
            "Resends every failed event of this hub that can be resent (also those beyond the first page of the list), "
            "once the cause of a passing failure is fixed. Those for an app that is no longer on stay. Says how many "
            "went back to the queue."
        ),
        asks={
            "en": ("retry all the failed events", "the printer is back, resend everything that failed"),
            "es": ("reintenta todos los eventos caídos", "vuelve a mandar todos los eventos que fallaron"),
        },
    ),
)
def failed_event_retry_all(ctx: OperationContext, data: FailedEventRetryAllIn) -> dict:
    """Every ``dead`` delivery of the hub whose app is on; another worker's rows wait (``SKIP LOCKED``)."""
    from base import relay  # base.relay imports this module

    ids = list(
        EventDelivery.objects.select_for_update(skip_locked=True, of=("self",))
        .filter(
            status=EventDelivery.Status.DEAD,
            event__scope_kind=ctx.scope.kind,
            event__scope_key=ctx.scope.key,
            app_label__in=relay.active_apps(ctx.scope),
        )
        .values_list("pk", flat=True)
    )
    if ids:
        _requeue(ids)
        record_event(ctx, events.FAILED_EVENT_RETRIED, {"count": len(ids)})
    return {"count": len(ids)}


@operation(
    "base.failed_event.discard",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=FailedEventDiscardIn,
    output=FailedEventOutId,
    ai=AI(
        description=(
            "Discards one failed event of this hub for good (by its id), with an optional reason: it is never "
            "delivered again and is kept with who discarded it, when and why. Only when it must not be delivered (a "
            "duplicate, already done by hand): discarding a sale's event for Invoicing leaves that sale without its "
            "invoice."
        ),
        risk="high",
        asks={
            "en": ("discard that failed event, I already did it by hand", "drop the duplicate event that failed"),
            "es": ("descarta ese evento caído, ya lo hice a mano", "olvídate del evento duplicado que falló"),
        },
    ),
)
def failed_event_discard(ctx: OperationContext, data: FailedEventDiscardIn) -> dict:
    """Closed as ``discarded`` with who, when and why; the row and its last error stay for the audit."""
    delivery = _failed_event(ctx, data.id)
    delivery.status = EventDelivery.Status.DISCARDED
    delivery.closed_at = timezone.now()
    delivery.closed_by = str(ctx.actor)[: EventDelivery._meta.get_field("closed_by").max_length]
    delivery.close_reason = data.reason.strip()
    delivery.save(update_fields=["status", "closed_at", "closed_by", "close_reason"])
    record_event(ctx, events.FAILED_EVENT_DISCARDED, {"id": str(delivery.pk)})
    return {"id": delivery.pk}


def _failed_event(ctx: OperationContext, delivery_id: UUID) -> EventDelivery:
    """The failed event ``delivery_id`` of the hub of ``ctx``, locked; not found if it is another hub's, or no longer
    failed (resent, discarded, or delivered in the meantime)."""
    delivery = (
        EventDelivery.objects.select_for_update(of=("self",))
        .filter(
            pk=delivery_id,
            status=EventDelivery.Status.DEAD,
            event__scope_kind=ctx.scope.kind,
            event__scope_key=ctx.scope.key,
        )
        .first()
    )
    if delivery is None:
        raise NotFound(gettext("That failed event is no longer in the queue: refresh the list."))
    return delivery


def _requeue(ids: list[UUID]) -> None:
    """Back to the queue, due now, with their attempts at zero and no error."""
    EventDelivery.objects.filter(pk__in=ids).update(
        status=EventDelivery.Status.PENDING, attempts=0, next_attempt_at=timezone.now(), last_error=""
    )


# ── The way in: devices, PIN, badge, the business's dial and the person's profile ────────────────────────────────

@transaction.atomic  # control's: the new session and the other devices' ones it ends
@atomic  # the hub's: the device, locked, the person (base.HubUser) and the ones it ends
def open_session_on_device(request: HttpRequest, user, device: TrustedDevice, credential: str) -> None:
    """Log ``user`` in on the hub's ``device`` with its PIN or its badge, for a shift (or what the
    device and the business allow). Over someone else's session («Switch user») ``login`` ends that one only now, once
    the new one is being opened in this transaction: a refused PIN never reaches here and changes nothing."""
    device = TrustedDevice.objects.select_for_update().get(pk=device.pk)
    _entered(device, user, timezone.now())
    ensure_hub_user(user)
    _log_in(request, user, saas_user_id_of(user), device=device, credential=credential)
    _end_other_devices(session_host(request) or "", device)


def saas_user_id_of(user) -> str:
    """The SaaS account a customer copy stands for (``saas:<id>`` → ``<id>``; :func:`username_for`)."""
    return user.get_username().removeprefix(SAAS_USERNAME_PREFIX)


@operation(
    "base.pin.set",
    kind="command",
    permission=VIEW_HOME,
    input=PinSetIn,
    output=PinSetOut,
    ai={
        "description": "Not an assistant tool (a PIN is typed on the PIN pad, never said aloud or written in a chat): "
        "the person chooses or changes their own PIN.",
        "risk": "high",
    },
)
def pin_set(ctx: OperationContext, data: PinSetIn) -> dict:
    """Choose or change one's own PIN: the business's length, digits only, not guessable, with the
    current one when there is one, and not the PIN of another active person of this hub. Every try counts against
    the person's budget (``access.PIN_CHANGE_LIMIT``), the accepted ones too: «already taken» tells something."""
    if ctx.actor is None or not hasattr(ctx.actor, "get_username"):
        raise Unauthorized(gettext("Sign in to choose your PIN."), code="base.sign_in_required")
    username = ctx.actor.get_username()
    wait = access.PIN_CHANGE_LIMIT.wait(ctx.scope.key, username)
    if wait:
        raise OperationError(
            too_many_message(wait, gettext("Too many tries to change the PIN.")), code="base.too_many_pin_changes", status=429
        )
    access.PIN_CHANGE_LIMIT.failed(ctx.scope.key, username)
    length = queries.access_settings().pin_length
    problem = access.pin_problem(data.pin, length)
    if problem is not None:
        raise InvalidPayload(_PIN_PROBLEMS[problem](length), code=f"base.pin_{problem}", fields={"pin": problem})
    credential = Credential.objects.select_for_update().filter(username=username).first()
    if credential is not None and credential.pin_hash and not check_password(data.current, credential.pin_hash):
        raise PermissionDenied(
            gettext("That is not your current PIN. Type it right to set a new one."), code="base.pin_current_wrong"
        )
    if any(check_password(data.pin, other.pin_hash) for other, _ in queries.pin_people(ctx.scope.key, exclude=username)):
        raise Conflict(
            gettext("Another active person already has that PIN: choose a different one."), code="base.pin_taken"
        )
    if credential is None:
        credential = Credential(username=username)
    credential.pin_hash, credential.pin_set_at = make_password(data.pin, hasher=PIN_HASHER), timezone.now()
    credential.save()
    record_event(ctx, events.PIN_SET, {})
    return {"set": True}


#: argon2id, as the old Hub (``crates/runtime/src/identity.rs``): a PIN is short, so its hash must be slow.
PIN_HASHER = "argon2"

_PIN_PROBLEMS = {
    access.PIN_LENGTH: lambda length: gettext("The PIN must have %(length)s digits.") % {"length": length},
    access.PIN_DIGITS: lambda length: gettext("The PIN takes digits only."),
    access.PIN_GUESSABLE: lambda length: gettext(
        "That PIN is too easy to guess: avoid repeated digits (1111) and runs (1234)."
    ),
}


def too_many_message(wait: int, lead: str) -> str:
    """«<lead> Wait N minutes and try again.», the minutes rounded up."""
    minutes = max(1, -(-wait // 60))
    return f"{lead} " + ngettext(
        "Wait %(minutes)s minute and try again.", "Wait %(minutes)s minutes and try again.", minutes
    ) % {"minutes": minutes}


def badge_key() -> bytes:
    """The hub's key of the badges' digests (``access.badge_digest``): made once, with the system's randomness, and
    kept in the business's row of ``AccessSettings``, never readable by any route. Two first uses at once end with
    the same key: the row is locked while it is made."""
    with atomic():
        row = AccessSettings.objects.select_for_update().first()
        if row is None:
            try:
                with atomic():
                    row = AccessSettings.objects.create(badge_key=secrets.token_hex(32))
            except IntegrityError:
                row = AccessSettings.objects.select_for_update().get()
        if not row.badge_key:
            row.badge_key = secrets.token_hex(32)
            row.save(update_fields=["badge_key"])
        return bytes.fromhex(row.badge_key)


def badge_owner(slug: str, raw: str):
    """The active person of ``slug`` whose card ``raw`` is, else ``None``; the card's digest, for its brake."""
    card = access.clean_badge(raw)
    if card is None:
        return None, access.token_digest(raw[:64])
    digest = access.badge_digest(card, key=badge_key())
    credential = Credential.objects.filter(badge_digest=digest).first()
    if credential is None:
        return None, digest
    membership = (
        Membership.objects.filter(host=slug, user__username=credential.username, user__is_active=True)
        .select_related("user")
        .first()
    )
    return (membership.user if membership is not None else None), digest


def _actor_label(ctx: OperationContext) -> str:
    return queries.person_label(ctx.actor)[:150] if hasattr(ctx.actor, "get_username") else str(ctx.actor)[:150]


@operation(
    "base.device.mode_set",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=DeviceModeIn,
    output=DeviceCurrentOut,
    ai=AI(
        description=(
            "Makes the device the person is using shared (a till several people use: PIN, a shift) or personal (one "
            "person's: no PIN, 30 days). Only on the device itself. Use this, not access.settings_update, to make "
            "the device in hand shared or personal; access.settings_update changes the business-wide PIN rules."
        ),
        asks={
            "en": (
                "make this tablet a shared till",
                "this laptop is only mine, set it to personal",
                "use this laptop as the whole team's till, with a PIN",
            ),
            "es": (
                "pon esta tablet como caja compartida",
                "este portátil es solo mío, que no pida PIN",
                "usa este portátil como caja de todo el equipo, con PIN",
            ),
        },
    ),
)
def device_mode_set(ctx: OperationContext, data: DeviceModeIn) -> dict:
    """«This device»: the mode of the browser that asks, never another's. The sessions opened from now on
    follow it; the open one keeps its end, fixed when it opened."""
    device = queries.device_of(ctx.request, for_update=True)
    if device is None:
        raise NotFound(
            gettext("Nobody has signed in with an account on this device yet: sign in once with your account on it."),
            code="base.device_unknown",
        )
    device.mode, device.mode_set_by, device.mode_set_at = data.mode, _actor_label(ctx), timezone.now()
    device.save(update_fields=["mode", "mode_set_by", "mode_set_at"])
    record_event(ctx, events.DEVICE_MODE_CHANGED, {"id": str(device.pk), "mode": data.mode})
    return {"known": True, "mode": device.mode, "mode_set_by": device.mode_set_by, "mode_set_at": device.mode_set_at}


def _device(device_id) -> TrustedDevice:
    device = TrustedDevice.objects.select_for_update().filter(pk=device_id).first()
    if device is None:
        raise NotFound(gettext("That device is no longer registered here. Refresh the list."), code="base.device_unknown")
    return device


@operation(
    "base.device.rename",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=DeviceRenameIn,
    output=DeviceByIdIn,
    ai=AI(
        description="Names a device of the hub after its place («Bar», «Kitchen», «Office laptop»).",
        asks={
            "en": (
                "call this tablet Bar",
                "rename the old iPad to Kitchen",
                "rename this device to Front desk",
            ),
            "es": (
                "llama a esta tablet «Barra»",
                "renombra el iPad viejo como «Terraza»",
                "cambia el nombre de este dispositivo a «Caja 2»",
            ),
        },
    ),
)
def device_rename(ctx: OperationContext, data: DeviceRenameIn) -> dict:
    """«Name it»: the one thing of a device the business decides."""
    name = data.name.strip()
    if len(name) > access.DEVICE_NAME_MAX_LENGTH:
        raise InvalidPayload(
            gettext("That name is too long. Give it a shorter one and save again."),
            code="base.device_name_too_long",
            fields={"name": "too_long"},
        )
    device = _device(data.id)
    device.name = name
    device.save(update_fields=["name"])
    record_event(ctx, events.DEVICE_RENAMED, {"id": str(device.pk)})
    return {"id": device.pk}


@operation(
    "base.device.remove",
    kind="command",
    permission=ADMINISTER_HUB,
    input=DeviceByIdIn,
    output=DeviceRemoveOut,
    ai=AI(
        description=(
            "Removes a lost device from the hub: its session ends at once and the PIN stops working on it until "
            "someone signs in with an account on it again. Removing the one in hand signs the person out. After "
            "device.list identifies the device, use this to close its access; listing alone changes nothing."
        ),
        risk="high",
        asks={
            "en": (
                "we lost the terrace tablet, remove it",
                "kick the stolen phone out of the business",
                "cut off access for the phone we lost",
            ),
            "es": (
                "hemos perdido la tablet de la terraza, quítala",
                "echa del negocio el móvil que nos robaron",
                "corta el acceso del móvil que se ha perdido",
            ),
        },
    ),
)
def device_remove(ctx: OperationContext, data: DeviceByIdIn) -> dict:
    """«Remove this device»: the device is cut off, not its people; whoever has an account can enter on it
    again, and then it is a new device."""
    device = _device(data.id)
    here = queries.device_of(ctx.request)
    yours = here is not None and here.pk == device.pk
    _remove_devices([device.pk])
    record_event(ctx, events.DEVICE_REMOVED, {"id": str(device.pk)})
    return {"removed": 1, "yours": yours}


@operation(
    "base.device.prune",
    kind="command",
    permission=ADMINISTER_HUB,
    input=DevicePruneIn,
    output=DevicePruneOut,
    ai=AI(
        description="Removes at once the devices of the hub nobody used in 30 days, never the one in hand.",
        risk="high",
        asks={
            "en": (
                "clean out the devices nobody has used in 30 days",
                "remove the old devices we don't use",
                "drop the computers nobody has opened in the last month",
            ),
            "es": (
                "limpia los dispositivos que nadie usa desde hace 30 días",
                "quita los aparatos viejos que ya no se usan",
                "da de baja los equipos que no se han usado en el último mes",
            ),
        },
    ),
)
def device_prune(ctx: OperationContext, data: DevicePruneIn) -> dict:
    """«Remove the unused»: those nobody entered on in 30 days, as «Remove this device» removes one."""
    ids = list(queries.unused_devices(queries.device_of(ctx.request)).select_for_update().values_list("pk", flat=True))
    _remove_devices(ids)
    record_event(ctx, events.DEVICES_PRUNED, {"removed": len(ids)})
    return {"removed": len(ids)}


def _remove_devices(ids: list) -> None:
    """End the sessions on the devices ``ids`` on every host (their tabs wake and leave) and forget the devices."""
    if not ids:
        return
    _end_sessions(SessionOwner.objects.filter(device_id__in=ids))
    TrustedDevice.objects.filter(pk__in=ids).delete()


@operation(
    "base.access.settings_update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=AccessSettingsUpdateIn,
    output=AccessSettingsOut,
    ai=AI(
        description=(
            "Changes how the business asks who is at the till: show the PIN pad or not, ask again after 1, 5, 10, 15 "
            "or 30 minutes without use or once per shift, and PINs of 4 or 6 digits."
        ),
        risk="high",
        asks={
            "en": (
                "ask for the PIN again after 5 minutes",
                "make the PINs 6 digits",
                "stop showing the PIN pad on the till",
                "only ask for the PIN once per shift",
            ),
            "es": (
                "que pida el PIN cada 10 minutos",
                "pon los PIN de 6 cifras",
                "quita el teclado del PIN de la caja",
                "que solo pida el PIN una vez por turno",
            ),
        },
    ),
)
def access_settings_update(ctx: OperationContext, data: AccessSettingsUpdateIn) -> dict:
    """The «PIN pad» card: only the fields sent change. The PINs of the other length keep working
    until their owners change them; the sessions already open keep their end."""
    changes = data.dict(exclude_none=True)
    if not changes:
        raise InvalidPayload(gettext("Nothing to change."), code="base.nothing_to_change")
    row = AccessSettings.objects.select_for_update().first()
    if row is None:
        try:
            with atomic():
                row = AccessSettings.objects.create()
        except IntegrityError:
            row = AccessSettings.objects.select_for_update().get()
    for field, value in changes.items():
        setattr(row, field, value)
    row.updated_by = _actor_label(ctx)
    row.save()
    record_event(ctx, events.ACCESS_SETTINGS_CHANGED, changes)
    return queries.access_settings_get(ctx, AccessSettingsIn())


def _profile(user) -> Profile:
    profile = Profile.objects.select_for_update().filter(username=user.get_username()).first()
    if profile is None:
        profile = Profile(username=user.get_username(), first_name=user.first_name[:150], last_name=user.last_name[:150])
    return profile


@operation(
    "base.profile.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=VIEW_HOME,
    input=ProfileUpdateIn,
    output=ProfileOut,
    ai=AI(
        description="Saves the person's own name, last name and contact email in this hub (not their sign-in email).",
        asks={
            "en": ("change my last name to García", "my contact email is now ana@bar.com"),
            "es": ("cambia mi apellido a García", "mi correo de contacto ahora es ana@bar.com"),
        },
    ),
)
def profile_update(ctx: OperationContext, data: ProfileUpdateIn) -> dict:
    """«Save my data»: how the person appears in this hub. The contact email gives and takes no access."""
    user = queries.signed_in(ctx)
    email = data.contact_email.strip()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            # Its own words: «Enter a valid email address.» is Django's, and other apps' catalogues translate it.
            raise InvalidPayload(
                gettext("Enter a valid contact email."), code="base.email_invalid", fields={"contact_email": "invalid"}
            ) from None
    profile = _profile(user)
    profile.first_name, profile.last_name, profile.contact_email = data.first_name.strip(), data.last_name.strip(), email
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    return queries.profile_get(ctx, ProfileIn())


@operation(
    "base.profile.preferences_set",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=VIEW_HOME,
    input=PreferencesIn,
    output=PreferencesOut,
    ai=AI(
        description="Sets the person's own language (Spanish, English or the business's) and appearance.",
        asks={
            "en": ("switch me to English", "put the app in dark mode", "change my language to Spanish"),
            "es": ("ponme el idioma en inglés", "quiero el modo oscuro", "cámbiame la apariencia a clara"),
        },
    ),
)
def preferences_set(ctx: OperationContext, data: PreferencesIn) -> dict:
    """«Preferences»: saved as chosen and applied at once; empty = the business's. They follow the person
    on any device of the hub (the language from their next entry on another one)."""
    user = queries.signed_in(ctx)
    profile = _profile(user)
    profile.language, profile.theme_mode, profile.palette = data.language, data.theme_mode, data.palette
    profile.ui_scale = data.ui_scale
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    language = queries.language_of(user, ctx.scope.key) or settings.LANGUAGE_CODE
    return {"language": language, "theme_mode": profile.theme_mode, "palette": profile.palette, "ui_scale": profile.ui_scale}


#: The largest photo, in bytes (before base64); the old Hub's.
MAX_AVATAR_BYTES = 2 * 1024 * 1024
_AVATAR_FORMATS = {"image/jpeg": ("JPEG", "jpg"), "image/png": ("PNG", "png"), "image/webp": ("WEBP", "webp")}


@operation(
    "base.profile.avatar_set",
    kind="command",
    permission=VIEW_HOME,
    input=AvatarIn,
    output=AvatarOut,
    ai={
        "description": "Not an assistant tool (it takes the image file the person picks in «Change photo»): sets the "
        "photo of their own profile.",
        "risk": "normal",
    },
)
def avatar_set(ctx: OperationContext, data: AvatarIn) -> dict:
    """«Change photo»: a JPG, PNG or WebP of 2 MB at most, kept in the hub's files under ``avatars/`` by
    its content's hash (served to the people of this hub only, ``base.media``)."""
    user = queries.signed_in(ctx)
    refused = gettext("The photo could not be saved. Use a JPG, PNG or WebP of up to 2 MB.")
    try:
        raw = base64.b64decode(data.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidPayload(refused, code="base.avatar_invalid") from None
    pillow_format, extension = _AVATAR_FORMATS[data.content_type]
    if not raw or len(raw) > MAX_AVATAR_BYTES or not _is_image(raw, pillow_format):
        raise InvalidPayload(refused, code="base.avatar_invalid")
    name = f"{AVATARS_FOLDER}{hashlib.sha256(raw).hexdigest()}.{extension}"
    key = f"{hub_prefix(hub_id(ctx.scope))}/{name}"
    store = storages["hub_files"]
    if not store.exists(key):
        store.save(key, ContentFile(raw))
    profile = _profile(user)
    profile.avatar = name
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    return {"avatar_url": queries.avatar_url(ctx, name)}


def _is_image(raw: bytes, pillow_format: str) -> bool:
    try:
        with PILImage.open(io.BytesIO(raw)) as image:
            if image.format != pillow_format:
                return False
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, PILImage.DecompressionBombError):
        return False
    return True


@operation(
    "base.profile.avatar_remove",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=VIEW_HOME,
    input=AvatarRemoveIn,
    output=AvatarOut,
    ai=AI(
        description="Removes the photo of the person's own profile.",
        asks={
            "en": ("remove my profile picture", "take the picture off my profile"),
            "es": ("quita mi foto de perfil", "no quiero foto en mi perfil"),
        },
    ),
)
def avatar_remove(ctx: OperationContext, data: AvatarRemoveIn) -> dict:
    """«Remove»: the profile forgets its photo (the file, named by its content, may be someone else's)."""
    user = queries.signed_in(ctx)
    profile = _profile(user)
    profile.avatar = ""
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    return {"avatar_url": ""}


# ── People and permissions: a person's way in ──────────────────────────────────────────────────────────────────────

_PERSON_REFUSALS = {people_rules.OWNER_ONLY: people_rules.OWNER_ONLY_MESSAGE, people_rules.OWN_BADGE: people_rules.OWN_BADGE_MESSAGE}


def _changeable_person(ctx: OperationContext, person_id: str, *, badge: bool) -> dict:
    """The person ``person_id`` of this business, if who asks may change their way in (``base.people.refusal``)."""
    person = queries.person_of(ctx, person_id)
    why = people_rules.refusal(
        actor=queries.signed_in_username(ctx),
        actor_role=queries.signed_in_role(ctx),
        target=person["id"],
        target_role=person["role"],
        badge=badge,
    )
    if why is not None:
        raise PermissionDenied(str(_PERSON_REFUSALS[why]), code=why)
    return person


def _person_answer(ctx: OperationContext, person_id: str) -> dict:
    return queries.person_detail_out(ctx, queries.person_of(ctx, person_id))


@operation(
    "base.person.pin_remove",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=PersonIn,
    output=PersonDetailOut,
    ai=AI(
        description=(
            "Takes a person's PIN away (a forgotten or shared one): they stop entering with it at the shared tills and "
            "keep entering with their erplora.com account. The owner's, only the owner."
        ),
        risk="high",
        preview={"operation": "base.person.detail", "fields": ["name", "email"]},
        asks={
            "en": ("Ana forgot her PIN, remove it", "take away Luis's PIN, he shared it"),
            "es": ("quítale el PIN a Luis, lo ha compartido", "Ana ha olvidado su PIN, bórraselo"),
        },
    ),
)
def person_pin_remove(ctx: OperationContext, data: PersonIn) -> dict:
    """«Remove the PIN»: the PIN goes at once, the badge and the account stay."""
    _changeable_person(ctx, data.person, badge=False)
    credential = Credential.objects.select_for_update().filter(username=data.person).exclude(pin_hash="").first()
    if credential is None:
        raise Conflict(gettext("This person has no PIN to remove."), code="base.person_no_pin")
    credential.pin_hash, credential.pin_set_at = "", None
    credential.save(update_fields=["pin_hash", "pin_set_at"])
    record_event(ctx, events.PERSON_PIN_REMOVED, {"person": data.person})
    return _person_answer(ctx, data.person)


@operation(
    "base.person.badge_set",
    kind="command",
    permission=ADMINISTER_HUB,
    input=BadgeSetIn,
    output=PersonDetailOut,
    ai={
        "description": "Not an assistant tool (a badge is a card passed through the reader): gives a person the badge "
        "they will enter with at the shared tills.",
        "risk": "high",
    },
)
def person_badge_set(ctx: OperationContext, data: BadgeSetIn) -> dict:
    """«Badge»: the card, kept as its digest; never one's own, never one somebody else carries. Every try
    counts against who gives it (``people.BADGE_CHANGE_LIMIT``): «already taken» tells something."""
    _changeable_person(ctx, data.person, badge=True)
    editor = queries.signed_in_username(ctx)
    wait = people_rules.BADGE_CHANGE_LIMIT.wait(ctx.scope.key, editor)
    if wait:
        raise OperationError(
            too_many_message(wait, gettext("Too many badges tried.")), code="base.too_many_badge_changes", status=429
        )
    people_rules.BADGE_CHANGE_LIMIT.failed(ctx.scope.key, editor)
    card = access.clean_badge(data.badge)
    if card is None:
        raise InvalidPayload(
            gettext("A badge has 4 to 64 characters: letters, digits, «-» and «_»."),
            code="base.badge_invalid",
            fields={"badge": "invalid"},
        )
    digest = access.badge_digest(card, key=badge_key())
    if Credential.objects.filter(badge_digest=digest).exclude(username=data.person).exists():
        raise Conflict(
            gettext("Somebody else already carries that badge. A badge says who is at the till: two people cannot share it."),
            code="base.badge_taken",
        )
    credential, _ = Credential.objects.select_for_update().get_or_create(username=data.person)
    credential.badge_digest, credential.badge_set_at = digest, timezone.now()
    try:
        with atomic():
            credential.save(update_fields=["badge_digest", "badge_set_at"])
    except IntegrityError:
        # Given to somebody else at this same moment: the unique digest keeps one.
        raise Conflict(
            gettext("Somebody else already carries that badge. A badge says who is at the till: two people cannot share it."),
            code="base.badge_taken",
        ) from None
    record_event(ctx, events.PERSON_BADGE_SET, {"person": data.person})
    return _person_answer(ctx, data.person)


@operation(
    "base.person.badge_remove",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=PersonIn,
    output=PersonDetailOut,
    ai=AI(
        description=(
            "Takes a person's badge away (a lost card): it stops opening the till; their PIN and account stay. For a "
            "person named in the chat, find their person id with person.list and then use this; do not ask for an id."
        ),
        asks={
            "en": (
                "Luis lost his card, take his badge away",
                "remove Marta's badge",
                "cancel Pedro's card, he lost it",
            ),
            "es": (
                "Luis ha perdido la tarjeta, quítale la placa",
                "quita la placa de Marta",
                "anula la tarjeta de Pedro, que se le ha perdido",
            ),
        },
    ),
)
def person_badge_remove(ctx: OperationContext, data: PersonIn) -> dict:
    """«Remove the badge»: the card stops opening anything; a lost one never leaves anybody out."""
    _changeable_person(ctx, data.person, badge=False)
    credential = Credential.objects.select_for_update().filter(username=data.person).exclude(badge_digest="").first()
    if credential is None:
        raise Conflict(gettext("This person has no badge to remove."), code="base.person_no_badge")
    credential.badge_digest, credential.badge_set_at = "", None
    credential.save(update_fields=["badge_digest", "badge_set_at"])
    record_event(ctx, events.PERSON_BADGE_REMOVED, {"person": data.person})
    return _person_answer(ctx, data.person)


# ── People and permissions: the business's API keys ────────────────────────────────────────────────────────────────


def _api_keys_available(ctx: OperationContext) -> None:
    """A key lives in its hub's own database; while the business shares its database with others, a key of it would open
    theirs too: none is made yet («not available yet», never the infrastructure's words)."""
    if not has_own_database(Hub.objects.filter(slug=ctx.scope.key).first()):
        raise Conflict(
            gettext("API keys are not available yet for this business."), code="base.api_keys_unavailable"
        )


def _checked_scopes(ctx: OperationContext, data: ApiKeyCreateIn) -> dict:
    """What a key per app may do on each app, of those this business has that publish it; nothing for the others."""
    if data.mode != ApiKey.Mode.PER_APP:
        return {}
    offered = {app["id"]: app for app in queries.api_apps(ctx)}
    scopes = {app: sorted(set(kinds)) for app, kinds in data.scopes.items() if kinds}
    if not scopes:
        message = gettext("Choose at least one app and what the key may do on it.")
        raise InvalidPayload(message, code="base.api_key_scopes_required", fields={"scopes": message})
    for app, kinds in scopes.items():
        found = offered.get(app)
        if found is None or any(not found[kind] for kind in kinds):
            message = gettext("That app does not publish what the key would do on it.")
            raise InvalidPayload(message, code="base.api_key_scope_unknown", fields={"scopes": message})
    return scopes


def _new_token_for(key: ApiKey) -> str:
    token = api_keys.new_token()
    key.token_digest, key.prefix = api_keys.digest(token), token[: api_keys.PREFIX_LENGTH]
    return token


@operation(
    "base.api_key.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ApiKeyCreateIn,
    output=ApiKeyTokenOut,
    ai={
        "description": "Not an assistant tool (its token is a secret shown once, never in a chat): makes an API key "
        "for another system, with a name, its requests a minute and what it may do.",
        "risk": "high",
    },
)
def api_key_create(ctx: OperationContext, data: ApiKeyCreateIn) -> dict:
    """«New API key»: its token once; the hub keeps its digest and its first characters."""
    _api_keys_available(ctx)
    name = " ".join(data.name.split())
    if not name:
        message = gettext("Give the key a name.")
        raise InvalidPayload(message, code="base.api_key_name_required", fields={"name": message})
    key = ApiKey(
        name=name,
        mode=data.mode,
        scopes=_checked_scopes(ctx, data),
        rate_per_minute=data.rate_per_minute,
        created_by=_actor_label(ctx),
    )
    token = _new_token_for(key)
    key.save()
    record_event(ctx, events.API_KEY_CREATED, {"id": str(key.id), "mode": key.mode})
    return {"key": queries.api_key_out(key), "token": token}


def _live_key(key_id: UUID) -> ApiKey:
    key = ApiKey.objects.select_for_update().filter(pk=key_id).first()
    if key is None:
        raise NotFound(gettext("That key no longer exists. Refresh the list and try again."), code="base.api_key_not_found")
    if key.revoked_at is not None:
        raise Conflict(gettext("That key was revoked: it never works again."), code="base.api_key_revoked")
    return key


@operation(
    "base.api_key.rotate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ApiKeyIdIn,
    output=ApiKeyTokenOut,
    ai={
        "description": "Not an assistant tool (its new token is a secret shown once): gives an API key a new token; "
        "the old one stops working at once.",
        "risk": "high",
    },
)
def api_key_rotate(ctx: OperationContext, data: ApiKeyIdIn) -> dict:
    """«Rotate»: a new token, shown once; the old one stops at once (its digest is gone)."""
    _api_keys_available(ctx)
    key = _live_key(data.id)
    token = _new_token_for(key)
    key.rotated_at = timezone.now()
    key.save(update_fields=["token_digest", "prefix", "rotated_at"])
    record_event(ctx, events.API_KEY_ROTATED, {"id": str(key.id)})
    return {"key": queries.api_key_out(key), "token": token}


@operation(
    "base.api_key.revoke",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ApiKeyIdIn,
    output=ApiKeyRevokeOut,
    ai=AI(
        description=(
            "Revokes an API key: any system using it loses access at once, for good. The key stays listed as revoked."
        ),
        risk="high",
        asks={
            "en": (
                "revoke the old Shopify key",
                "cut off the key the accountant was using",
                "kill that API key, it leaked",
            ),
            "es": (
                "revoca la clave de la tienda online",
                "córtale el acceso a la clave de la gestoría",
                "anula esa clave de API, se ha filtrado",
            ),
        },
    ),
)
def api_key_revoke(ctx: OperationContext, data: ApiKeyIdIn) -> dict:
    """«Revoke»: at once and for good; the key is kept, for the record."""
    _api_keys_available(ctx)
    key = _live_key(data.id)
    key.revoked_at, key.revoked_by = timezone.now(), _actor_label(ctx)
    key.save(update_fields=["revoked_at", "revoked_by"])
    record_event(ctx, events.API_KEY_REVOKED, {"id": str(key.id)})
    return {"key": queries.api_key_out(key)}


#: A key's last use is written at most once a minute: a busy integration does not write on every call.
API_KEY_LAST_USE_EVERY = dt.timedelta(minutes=1)


def authenticate_api_key(request: HttpRequest, token: str, op) -> "api_keys.KeyCaller | None":
    """The caller of ``token`` on the published operation ``op``, in the request's hub (``base.api_keys.KeyDoor``).

    401 ``base.api_keys_unavailable`` on a business that shares its database, where no key exists: a request
    that brings one is refused for that reason, never let through by a session. ``None`` (the
    session's door goes on) without a hub, or for a token nobody issued here (counted against the address); 429 once
    the address tried too many, or the key passed its pace; 403 when the key may not do this on this app."""
    hub = getattr(request, "hub", None)
    if hub is None:
        return None
    if not has_own_database(hub):
        raise Unauthorized(
            gettext("API keys are not available yet for this business."), code="base.api_keys_unavailable"
        )
    address = client_key(request)
    wait = api_keys.KEY_ADDRESS_LIMIT.wait(hub.slug, address)
    if wait:
        raise OperationError(
            too_many_message(wait, gettext("Too many keys tried from here.")),
            code="base.too_many_api_key_tries",
            status=429,
        )
    key = ApiKey.objects.filter(token_digest=api_keys.digest(token), revoked_at=None).first()
    if key is None:
        api_keys.KEY_ADDRESS_LIMIT.failed(hub.slug, address)
        return None
    if not api_keys.allows(key.mode, key.scopes, op.app_label, api_keys.kind_of(op)):
        raise PermissionDenied(
            gettext("This API key may not do that on this app."), code="base.api_key_scope"
        )
    if api_keys.over_pace(key.pk, key.rate_per_minute):
        raise OperationError(
            gettext("This API key went past its requests a minute: wait a moment."),
            code="base.api_key_rate_limited",
            status=429,
        )
    now = timezone.now()
    if key.last_used_at is None or now - key.last_used_at >= API_KEY_LAST_USE_EVERY:
        ApiKey.objects.filter(pk=key.pk).update(last_used_at=now)
    granted = frozenset({op.permission}) if op.permission else frozenset()
    return api_keys.KeyCaller(key_id=str(key.pk), name=key.name, prefix=key.prefix, permissions=granted)


# ── People and permissions: a manager's approval ───────────────────────────────────────────────────────────────────
from base import approvals as approval_rules  # noqa: E402
from base.models import Approval  # noqa: E402
from base.schemas import ApprovalIn, ApprovalPassOut, ApprovalSpendIn, ApprovalSpentOut  # noqa: E402


def _approval_refused() -> Unauthorized:
    return Unauthorized(
        gettext("Those details do not approve this. Check the name and the PIN, and try again."),
        code="base.approval_refused",
    )


def _approval_too_many(wait: int) -> OperationError:
    return OperationError(
        too_many_message(wait, gettext("Too many wrong attempts.")), code="base.too_many_attempts", status=429
    )


def _approver(ctx: OperationContext, data: ApprovalIn):
    """Who approves, by their PIN (counted against that person) or their badge (against the card), with the PIN
    pad's brakes: a wrong one also counts against the address; a right one starts the count again."""
    slug, address = ctx.scope.key, client_key(ctx.request)
    wait = access.PIN_ADDRESS_LIMIT.wait(slug, address)
    if wait:
        raise _approval_too_many(wait)
    if data.badge:
        user, card = badge_owner(slug, data.badge)
        brake = ("badge", card)
        way = Approval.Way.BADGE
    else:
        person = (data.person or "")[:64]
        brake = (person,)
        wait = access.PIN_PERSON_LIMIT.wait(slug, *brake)
        if wait:
            raise _approval_too_many(wait)
        user = queries.pin_owner(slug, person, (data.pin or "")[:16]) if data.pin else None
        way = Approval.Way.PIN
    if data.badge and (wait := access.PIN_PERSON_LIMIT.wait(slug, *brake)):
        raise _approval_too_many(wait)
    if user is None:
        access.PIN_PERSON_LIMIT.failed(slug, *brake)
        access.PIN_ADDRESS_LIMIT.failed(slug, address)
        raise _approval_refused()
    access.PIN_PERSON_LIMIT.clear(slug, *brake)
    return user, way


@operation(
    "base.approval.approve",
    kind="command",
    permission=VIEW_HOME,
    input=ApprovalIn,
    output=ApprovalPassOut,
    ai={
        "description": "Not an assistant tool (it takes a manager's PIN, never typed in a chat): a manager approves "
        "one action the person at the screen may not do, and the hub hands back a pass of one use.",
        "risk": "high",
    },
)
def approval_approve(ctx: OperationContext, data: ApprovalIn) -> dict:
    """«An approval is needed»: somebody of the business who may do the action approves it with their PIN
    or badge; a pass of one use for two minutes, bound to who asked, that action and that very request."""
    found = approval_rules.approvable(data.operation)
    if found is None:
        raise Conflict(gettext("This is not approved with a PIN."), code="base.approval_not_offered")
    op, _label = found
    if ctx.has(op.permission):
        raise Conflict(gettext("This no longer needs an approval: do it again."), code="base.approval_not_needed")
    if not data.badge and not (data.person and data.pin):
        raise InvalidPayload(
            gettext("Choose who approves it and type their PIN."), code="base.approval_incomplete", fields={"pin": "required"}
        )
    approver, way = _approver(ctx, data)
    if not queries.holds(approver, ctx.scope, op.permission):
        raise PermissionDenied(
            gettext("That person cannot approve this: ask somebody who may do it themselves."),
            code="base.approver_cannot",
        )
    token = approval_rules.new_token()
    approver_name = queries.face_name(approver)
    approval = Approval.objects.create(
        operation=op.name,
        permission=op.permission,
        fingerprint=data.fingerprint,
        token_digest=approval_rules.digest(token),
        requested_by=ctx.actor.get_username(),
        requested_by_name=queries.face_name(ctx.actor)[:150],
        approved_by=approver.get_username(),
        approved_by_name=approver_name[:150],
        way=way,
        expires_at=timezone.now() + dt.timedelta(seconds=approval_rules.PASS_SECONDS),
    )
    record_event(ctx, events.APPROVAL_GRANTED, {"id": str(approval.pk), "operation": op.name})
    return {"token": token, "approver": approver_name, "expires_in": approval_rules.PASS_SECONDS}


@operation(
    "base.approval.spend",
    kind="command",
    permission=VIEW_HOME,
    input=ApprovalSpendIn,
    output=ApprovalSpentOut,
    ai={
        "description": "Not an assistant tool, and no route: the approval's door spends a pass on the request it was "
        "given for (base.approvals).",
        "risk": "high",
    },
)
def approval_spend(ctx: OperationContext, data: ApprovalSpendIn) -> dict:
    """Spend a pass on the request it was given for: once, in time, by who asked, on that action and that request of
    this business. Anything else spends nothing."""
    if not hasattr(ctx.actor, "get_username"):
        return {"spent": False, "id": "", "approver": ""}
    now = timezone.now()
    approval = (
        Approval.objects.select_for_update()
        .filter(
            token_digest=approval_rules.digest(data.token),
            operation=data.operation,
            fingerprint=data.fingerprint,
            requested_by=ctx.actor.get_username(),
            used_at=None,
            expires_at__gt=now,
        )
        .first()
    )
    if approval is None:
        return {"spent": False, "id": "", "approver": ""}
    approval.used_at = now
    approval.figures = data.figures or None
    approval.save(update_fields=["used_at", "figures"])
    record_event(ctx, events.APPROVAL_USED, {"id": str(approval.pk), "operation": approval.operation})
    return {"spent": True, "id": str(approval.pk), "approver": approval.approved_by_name}



# ── People and permissions: the API's documentation ────────────────────────────────────────────────────────────────
from base.models import ApiSettings  # noqa: E402
from base.schemas import ApiDocSettingsIn, ApiDocSettingsOut, ApiDocSettingsUpdateIn  # noqa: E402


@operation(
    "base.api_doc.settings_update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ApiDocSettingsUpdateIn,
    output=ApiDocSettingsOut,
    ai=AI(
        description=(
            "Shows or hides the documentation of this business's API (for whoever connects another system); it comes "
            "hidden."
        ),
        asks={
            "en": ("show the API docs to our developer", "hide the API documentation again"),
            "es": ("publica la documentación de la API para el programador", "oculta otra vez la doc de la API"),
        },
    ),
)
def api_doc_settings_update(ctx: OperationContext, data: ApiDocSettingsUpdateIn) -> dict:
    """«Show the API documentation»: saved at once."""
    row = ApiSettings.objects.select_for_update().first()
    if row is None:
        try:
            with atomic():
                row = ApiSettings.objects.create()
        except IntegrityError:
            row = ApiSettings.objects.select_for_update().get()
    row.docs_enabled = data.docs_enabled
    row.updated_by = _actor_label(ctx)
    row.save()
    record_event(ctx, events.API_DOC_SETTINGS_CHANGED, {"docs_enabled": data.docs_enabled})
    return queries.api_doc_settings(ctx, ApiDocSettingsIn())


# ── Files ──────────────────────────────────────────────────────────────────────────────────────────────────────────
# The business's files in the hub file store (``base.files``), on the hub of the request only. Who runs the business
# uploads, makes folders and renames (``base.upload_files``) and deletes (``base.delete_files``); moving takes
# both, as it deletes where the file was and uploads where it goes. Each write records its event in its transaction;
# the store is written first, so a refusal of the store leaves no event (a lost event leaves the file: the listing
# reads the store, never the events).
UPLOAD_FILES = "base.upload_files"
DELETE_FILES = "base.delete_files"


def _file_bytes(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        message = gettext("The file did not arrive whole. Upload it again.")
        raise InvalidPayload(message, code="base.file_not_base64", fields={"content_base64": message}) from None


@operation(
    "base.file.upload",
    kind="command",
    permission=UPLOAD_FILES,
    input=FileUploadIn,
    output=FileSavedOut,
    expose_api=True,
    ai=AI(
        description=(
            "Keeps a file the person attached in the business's files, in a folder by its path (the folder «Facturas»; "
            "empty: the top). Never overwrites: a taken name becomes «name (1).ext». 25 MB at most; programs are "
            "refused."
        ),
        asks={
            "en": ("upload the contract I attached", "keep this photo in our files", "save this PDF in our files"),
            "es": (
                "archiva el documento que te adjunto",
                "guarda este PDF en los archivos",
                "sube el archivo que te he adjuntado",
            ),
        },
    ),
)
def file_upload(ctx: OperationContext, data: FileUploadIn) -> dict:
    """Keep the file, numbered when its name is taken, within the plan's space."""
    with translation.override(ctx.language):
        content = _file_bytes(data.content_base64)
        saved = files.upload(
            storages["hub_files"],
            hub_id(ctx.scope),
            data.folder,
            data.name,
            content,
            limit_bytes=queries.space_limit(ctx),
        )
    record_event(ctx, events.FILE_UPLOADED, {"path": saved["path"]})
    return saved


@operation(
    "base.file.create_folder",
    kind="command",
    permission=UPLOAD_FILES,
    input=FileFolderCreateIn,
    output=FilePathOut,
    expose_api=True,
    ai=AI(
        description=(
            "Makes a new, empty folder in the business's files, inside another by its path (the folder «Facturas»; "
            "empty: the top). Refused when that name is taken there."
        ),
        asks={
            "en": ("make a folder called Invoices", "create a 2026 folder inside Contracts"),
            "es": ("hazme una carpeta 2026 dentro de Contratos", "crea una carpeta para los contratos"),
        },
    ),
)
def file_create_folder(ctx: OperationContext, data: FileFolderCreateIn) -> dict:
    """A new folder, never over a file or folder of that name."""
    with translation.override(ctx.language):
        made = files.create_folder(storages["hub_files"], hub_id(ctx.scope), data.parent, data.name)
    record_event(ctx, events.FILE_FOLDER_CREATED, {"path": made["path"]})
    return made


@operation(
    "base.file.rename",
    kind="command",
    permission=UPLOAD_FILES,
    input=FileRenameIn,
    output=FilePathOut,
    expose_api=True,
    ai=AI(
        description=(
            "Gives a file or a folder of the business's files another name, where it is (the file «Facturas/marzo.pdf» "
            "becomes «abril.pdf»). Refused when the new name is taken there."
        ),
        asks={
            "en": ("rename march.pdf to april.pdf", "call that folder Suppliers instead"),
            "es": ("renombra marzo.pdf como abril.pdf", "renombra la carpeta Viejos como «Archivo 2024»"),
        },
    ),
)
def file_rename(ctx: OperationContext, data: FileRenameIn) -> dict:
    """A new name in the same folder; a folder takes everything in it along."""
    with translation.override(ctx.language):
        renamed = files.rename(storages["hub_files"], hub_id(ctx.scope), data.path, data.name)
    if renamed["path"] != data.path:
        record_event(ctx, events.FILE_RENAMED, {"path": renamed["path"], "from": data.path})
    return renamed


@operation(
    "base.file.move",
    kind="command",
    permission=DELETE_FILES,
    input=FileMoveIn,
    output=FilePathOut,
    expose_api=True,
    ai=AI(
        description=(
            "Moves a file or a folder of the business's files into another folder, both by their path (the file "
            "«marzo.pdf» into the folder «Facturas»; empty: the top). Never overwrites, and a folder never goes inside "
            "itself."
        ),
        asks={
            "en": ("move march.pdf into Invoices", "put the contracts folder inside Legal"),
            "es": ("mueve marzo.pdf a la carpeta Facturas", "mete la carpeta de contratos dentro de Legal"),
        },
    ),
)
def file_move(ctx: OperationContext, data: FileMoveIn) -> dict:
    """To another folder; deleting where it was and uploading where it goes."""
    with translation.override(ctx.language):
        if not ctx.has(UPLOAD_FILES):
            raise PermissionDenied(gettext("Only who runs the business can change the files."))
        moved = files.move(storages["hub_files"], hub_id(ctx.scope), data.path, data.to)
    record_event(ctx, events.FILE_MOVED, {"path": moved["path"], "from": data.path})
    return moved


@operation(
    "base.file.delete",
    kind="command",
    permission=DELETE_FILES,
    input=FileDeleteIn,
    output=FileDeletedOut,
    expose_api=True,
    ai=AI(
        description=(
            "Deletes a file of the business's files, or a folder and everything in it, by its path (the folder "
            "«Facturas/2025»). There is no bin: it cannot be undone."
        ),
        risk="high",
        asks={
            "en": ("delete the old 2025 folder", "throw away march.pdf from our files"),
            "es": ("borra la carpeta de 2025", "elimina marzo.pdf de los archivos"),
        },
    ),
)
def file_delete(ctx: OperationContext, data: FileDeleteIn) -> dict:
    """The file, or the folder and everything in it; no bin."""
    with translation.override(ctx.language):
        deleted = files.delete(storages["hub_files"], hub_id(ctx.scope), data.path)
    record_event(ctx, events.FILE_DELETED, {"path": deleted["path"], "folder": deleted["folder"]})
    return deleted


# ── Assistant ───────────────────────────────────────────────────────────────────────────────────────────────────

import dataclasses  # noqa: E402 - the assistant's block keeps its imports with it

from django.utils.translation import pgettext  # noqa: E402 - the assistant's block keeps its imports with it

from base.schemas import (  # noqa: E402
    AssistantReportIn,
    AssistantReportOut,
    AssistantSpeakIn,
    AssistantSpeakOut,
    AssistantTranscribeIn,
    AssistantTranscribeOut,
    AssistantTurnIn,
    AssistantTurnOut,
)

#: What the model hears of a tool that did not run (in English, as its instructions).
NOT_CONFIRMED = "Not confirmed by the person: nothing was done."
STOPPED = "The person stopped this request: nothing more was done."
NOT_AVAILABLE = "This tool is not available to this person here: nothing was done."
NOT_FROM_THE_CHAT = "This cannot be done from the chat (it names no record): nothing was done. Say where it is done."


def _assistant_screens(ctx: OperationContext) -> dict[str, str]:
    """The screens the assistant may link: the platform's and the menus of the apps on, by name."""
    with translation.override(ctx.language):
        screens = {
            "/": pgettext("base", "Home"),
            # In everybody's menu.
            "/employees": pgettext("base", "Employees"),
            "/apps": pgettext("base", "Apps"),
            "/settings": pgettext("base", "Settings"),
            "/profile": pgettext("base", "My profile"),
        }
        if ctx.has(ADMINISTER_HUB):
            screens["/system"] = pgettext("base", "System")
        if ctx.has(queries.VIEW_FILES):
            screens["/files"] = pgettext("base", "Files")
        for config in assistant.active_apps(ctx.scope).values():
            for nav in getattr(config, "navigation", []) or []:
                screens.setdefault(nav.path, f"{config.verbose_name} › {nav.label}")
    return screens


def _assistant_read(ctx: OperationContext, name: str) -> dict | None:
    """``name``'s answer for the person (a read of base), or ``None`` when it fails: never made up."""
    op = get_operation(name)
    try:
        return op(ctx, op.input()).model_dump(mode="json")
    except OperationError:
        return None


def _assistant_refusal(outcome: str, code: str, message: str) -> "assistant.ToolOutcome":
    """A tool that did not run, told to the model in the same envelope as an operation's error."""
    return assistant.ToolOutcome(outcome, code, assistant.error_content(code, message))


def _assistant_answer(ctx, tools, call, decision, *, stopped: bool):  # noqa: C901, PLR0911
    """Run one pending ``call`` (a read alone; a write with the person's yes) → ``(outcome, card, shown)``: the card
    when the write still waits for its answer, with what it will do when its app declares a preview (BASE-F98), and
    the fingerprint of what it shows (``shown``, ``assistant.fingerprint``); one that cannot be read is the write's
    outcome, and no card is shown. Neither is one for data the write would refuse: the model hears which
    (``invalid_payload``) and asks again with them corrected. The yes is for the card it answers (hub#1208): drawn
    again, a card that no longer shows what ``call.shown`` says — a record found by its name is another, a name or what
    it will do changed — runs nothing and is shown anew; a «no» or a word typed wrong never needs it."""
    op = assistant.operation_of(call.name, tools)
    if op is None:
        return _assistant_refusal("refused", "not_available", NOT_AVAILABLE), None, ""
    if stopped:
        return _assistant_refusal("cancelled", "base.assistant_stopped", STOPPED), None, ""
    if op.kind == "query":
        return assistant.run_tool(ctx, op, call.arguments), None, ""
    try:
        arguments = json.loads(call.arguments or "{}")
    except ValueError:
        arguments = None
    if not isinstance(arguments, dict):
        return assistant.run_tool(ctx, op, call.arguments), None, ""
    refused = assistant.invalid_arguments(op, arguments)
    if refused is not None:
        return refused, None, ""
    found: list = []
    card = assistant.card(op, arguments, ctx.language, ctx, found=found)
    answered = decision is not None and decision.call_id == call.call_id
    if card["blocked"]:
        if not answered:
            return None, card, ""
        return _assistant_refusal("cancelled", "base.assistant_not_from_chat", NOT_FROM_THE_CHAT), None, ""
    if answered and decision.stop:
        return _assistant_refusal("cancelled", "base.assistant_stopped", STOPPED), None, ""
    if answered and (not decision.accepted or not assistant.confirmed(card, decision.typed)):
        return _assistant_refusal("cancelled", "base.assistant_not_confirmed", NOT_CONFIRMED), None, ""
    failure, preview = assistant.preview(ctx, op, arguments, found=found)
    if failure is not None:
        return failure, None, ""
    drawn = {**card, "preview": preview}
    shown = assistant.fingerprint(drawn, found)
    if not answered or call.shown != shown:
        return None, drawn, shown
    return assistant.run_tool(_assistant_approved(ctx, op, call.arguments), op, call.arguments), None, ""


def _assistant_approved(ctx: OperationContext, op, arguments: str) -> OperationContext:
    """Who runs a write the person said yes to: the person. When they may not and a manager may approve it
   , the turn asks as the screen does — ``requires_elevation`` for this very request — and, repeated with
    the pass, runs it with that one permission more; the pass is spent in the write's own transaction
    (``base.approval_spend``), so a write that fails leaves it unspent and one that ran cannot run twice. The question
    says the figures of that write, read from its ``arguments`` as the command validates them."""
    request = getattr(ctx, "request", None)
    if ctx.has(op.permission) or request is None or approval_rules.approvable(op.name) is None:
        return ctx
    asked = approval_rules.fingerprint(request, ctx.scope.key)
    figures = approval_rules.figures_from(op, arguments)
    token = request.headers.get(approval_rules.HEADER, "")
    if not token.startswith(approval_rules.TOKEN_PREFIX):
        raise approval_rules.refusal(op.name, asked, figures, ctx.scope)
    request.approved = approval_rules.Approved(
        operation=op.name, permission=op.permission, token=token, fingerprint=asked, figures=figures
    )
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) | {op.permission})


@operation(
    "base.assistant.turn",
    kind="command",
    permission=VIEW_HOME,
    input=AssistantTurnIn,
    output=AssistantTurnOut,
    ai={"description": "Not an assistant tool (the assistant's own turn: the person writes it in its panel)."},
)
def assistant_turn(ctx: OperationContext, data: AssistantTurnIn) -> dict:
    """A turn of the Hub's assistant made ready: the reads the model asked for run as the
    person; a write shows its card and runs only with the person's yes (``decision``; «Cancel all» = ``stop``), and
    only on what that card showed (hub#1208: the call it waits on goes back with its ``shown``); a tool this person
    was not offered never runs. Then what goes to the gateway: the tools of what was asked, by relevance,
    and the instructions (with the person's role and the writes a manager must approve, hub#585; with the checklist,
    read again, in ``setup``). Past ``assistant.MAX_ROUNDS`` rounds of tools it goes no further (``stop``)."""
    if ctx.actor is None:
        raise Unauthorized(gettext("Sign in to talk to the assistant."))
    tools = assistant.catalog(ctx)
    pending = list(data.pending)
    decision = data.decision
    stopped = False
    append: list[dict] = []
    executed: list[dict] = []
    card = None
    while pending:
        call = pending[0]
        outcome, card, shown = _assistant_answer(ctx, tools, call, decision, stopped=stopped)
        if outcome is None:
            # The call its card waits on goes back with what the card showed: the yes comes with it (hub#1208).
            pending[0] = call.model_copy(update={"shown": shown})
            break
        if decision is not None and decision.call_id == call.call_id:
            stopped = decision.stop
            decision = None
        # What ran, or was refused, by its name: a write this person was not offered is named too.
        op = assistant.operation_of(call.name, tools) or assistant.named(call.name)
        append.append({"role": "tool", "tool_call_id": call.call_id, "content": outcome.content})
        with translation.override(ctx.language):
            # Named as its card names it: an app by its name, the platform by its screen.
            app_name = assistant.app_name(op) if op else ""
        executed.append(
            {
                "call_id": call.call_id,
                "name": op.name if op else call.name,
                "app": op.app_label if op else "",
                "app_name": app_name,
                "screen": assistant.screen(op) if op else "",
                "kind": op.kind if op else "",
                "outcome": outcome.outcome,
                "code": outcome.code,
            }
        )
        pending.pop(0)
    messages = [*data.messages, *append]
    asked = [str(m.get("content")) for m in data.messages if m.get("role") == "user" and isinstance(m.get("content"), str)]
    business = _assistant_read(ctx, "base.business.get") or {}
    if card is not None:
        # The card paints an amount (its schema's ``money`` mark) in the business's currency, with its decimals.
        currency = business.get("currency") or "EUR"
        card["money"] = {"currency": currency, "decimals": business.get("currency_decimals", 2)}
    offered = assistant.relevant(tools, asked[-2:], ctx.language)
    text = assistant.instructions(
        language=ctx.language,
        currency=business.get("currency") or "EUR",
        decimals=business.get("currency_decimals", 2),
        business=business.get("name") or "",
        screens=_assistant_screens(ctx),
        role=_assistant_role(ctx),
        # What is offered without its permission is a write a manager may approve (``assistant.catalog``).
        approvable=[op.name for op in offered if not ctx.has(op.permission)],
    )
    if data.setup:
        text += "\n\n" + assistant.setup_block(_assistant_read(ctx, "base.setup.status"))
    stop = ""
    if card is None and not stopped and assistant.rounds(messages) >= assistant.MAX_ROUNDS:
        stop = "assistant.too_many_steps"
    return {
        "messages": messages,
        "append": append,
        "executed": executed,
        "confirm": card,
        "pending": [p.model_dump() for p in pending],
        "tools": [assistant.tool_spec(op) for op in offered],
        "instructions": text,
        "continuation": data.continuation,
        "stop": stop,
    }


def _assistant_role(ctx: OperationContext) -> str:
    """The role in this business of whom the assistant serves (hub#585): their ``Membership``'s; "" for an actor with
    none here (an API key, ERPlora's staff)."""
    if not hasattr(ctx.actor, "get_username"):
        return ""
    return Membership.objects.filter(user=ctx.actor, host=ctx.scope.key).values_list("role", flat=True).first() or ""


def _gateway_failure(code: str, message: str) -> OperationError:
    """erplora.com did not do it (unreachable, down, refused): a 503 the panel says in its own words."""
    return OperationError(message, code=code, status=503)


@operation(
    "base.assistant.report",
    kind="command",
    permission=VIEW_HOME,
    input=AssistantReportIn,
    output=AssistantReportOut,
    ai={"description": "Not an assistant tool (the person reports an answer of the assistant from its panel)."},
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def assistant_report(ctx: OperationContext, data: AssistantReportIn) -> dict:
    """Send erplora.com's team an answer the person reports, with the question that led to it."""
    try:
        return assistant.report(ctx.scope, **data.model_dump())
    except assistant.GatewayError:
        raise _gateway_failure(
            "base.assistant_report_not_sent", gettext("The report could not be sent: try again in a moment.")
        ) from None


@operation(
    "base.assistant.transcribe",
    kind="command",
    permission=VIEW_HOME,
    input=AssistantTranscribeIn,
    output=AssistantTranscribeOut,
    ai={"description": "Not an assistant tool (the person's dictation in the panel, turned into text it reviews)."},
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def assistant_transcribe(ctx: OperationContext, data: AssistantTranscribeIn) -> dict:
    """The text of the person's dictation, by erplora.com: it goes to the box, never sent by itself."""
    try:
        return assistant.transcribe(ctx.scope, audio=data.audio, mime_type=data.mime_type, language=data.language or ctx.language)
    except assistant.GatewayError as exc:
        if exc.status == 413 or exc.code == "payload_too_large":
            raise OperationError(
                gettext("The recording is too long: dictate a shorter message."), code="base.assistant_audio_too_long", status=413
            ) from None
        raise _gateway_failure(
            "base.assistant_transcribe_failed", gettext("The audio could not be transcribed: try again.")
        ) from None


#: erplora.com has no voice to read with (no key of the voices' provider): nothing to try again.
SPEECH_NOT_CONFIGURED = frozenset({"assistant.speech_unavailable", "assistant.provider_not_configured"})


def _speech_unavailable() -> OperationError:
    return _gateway_failure(
        "base.assistant_speech_unavailable", gettext("Reading aloud in the server's voice is not available.")
    )


@operation(
    "base.assistant.speak",
    kind="command",
    permission=VIEW_HOME,
    input=AssistantSpeakIn,
    output=AssistantSpeakOut,
    ai={"description": "Not an assistant tool (the panel reads an answer aloud in the server's voice the person chose)."},
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def assistant_speak(ctx: OperationContext, data: AssistantSpeakIn) -> dict:
    """An answer read aloud in the server's voice, by erplora.com: the mp3. When it cannot, the panel reads with the
    device's voice. With no server voice (``ASSISTANT_SERVER_VOICE`` off) erplora.com is never asked."""
    if not settings.ASSISTANT_SERVER_VOICE:
        raise _speech_unavailable()
    try:
        spoken = assistant.speak(ctx.scope, text=data.text, language=data.language or ctx.language, voice=data.voice)
    except assistant.GatewayError as exc:
        if exc.code in SPEECH_NOT_CONFIGURED:
            raise _speech_unavailable() from None
        raise _gateway_failure(
            "base.assistant_speech_failed", gettext("The answer could not be read aloud: try again.")
        ) from None
    return {"content_type": spoken["content_type"], "content_base64": base64.b64encode(spoken["audio"]).decode()}


# ── «Report a problem» (BASE-F108; ACCOUNTS-F38 of the SaaS) ────────────────────────────────────────────────────────
# The user menu's dialog sends it to erplora.com, which mails its support mailbox «Reply-To» the account and limits it
# per account (SUPPORT_REPORT_RATELIMIT, the panel's and the hub's together): the hub keeps nothing and limits nothing.
from base.schemas import SupportReportIn, SupportReportOut  # noqa: E402

SUPPORT_REPORT_PATH = "/internal/support/report"
#: Characters of the browser a report sends: erplora.com keeps as many.
REPORT_BROWSER_MAX = 300


def _session_account(ctx: OperationContext) -> str | None:
    """The erplora.com account behind this session: only a session opened with it on this hub. A PIN or a badge on a
    shared till, a demo's visitor or a call without a session has none, and neither has a session that
    does not say how it was opened (``CREDENTIAL_SESSION_KEY``): never the account by default."""
    request, user = ctx.request, ctx.actor
    username = user.get_username() if hasattr(user, "get_username") else ""
    opened_with = request.session.get(CREDENTIAL_SESSION_KEY) if request is not None else None
    if (
        not username.startswith(SAAS_USERNAME_PREFIX)
        or opened_with != SessionOwner.Credential.ACCOUNT
        or getattr(request, "hub", None) is None
    ):
        return None
    return saas_user_id_of(user)


def _reporting_account(ctx: OperationContext) -> str:
    """The account support answers to (``_session_account``), or the refusal that says how to report."""
    account = _session_account(ctx)
    if account is None:
        raise PermissionDenied(
            gettext("Sign in with your erplora.com account to report a problem."), code="base.support_needs_account"
        )
    return account


def _report_not_sent() -> OperationError:
    return OperationError(
        gettext("We could not send your report. Write to us directly at %(email)s.") % {"email": settings.SUPPORT_EMAIL},
        code="base.report_not_sent",
        status=503,
    )


def _reply_to(answer: bytes) -> str | None:
    """The address erplora.com says support answers to, or ``None`` when its answer is no report sent."""
    try:
        payload = json.loads(answer)
    except ValueError:
        return None
    reply_to = payload.get("reply_to") if isinstance(payload, dict) else None
    return reply_to if isinstance(reply_to, str) and reply_to else None


@operation(
    "base.support.report",
    kind="command",
    permission=VIEW_HOME,
    input=SupportReportIn,
    output=SupportReportOut,
    ai=AI(
        description=(
            "Sends erplora.com's support team a problem the person describes: a short subject and what happened. Their "
            "account, this business, the screen and the browser go with it, and support answers by email to their "
            "account. Only for a person who entered with their erplora.com account, never with a PIN."
        ),
        asks={
            "en": (
                "tell support the payment screen freezes",
                "report a bug: the totals don't add up",
                "send ERPlora a problem",
            ),
            "es": (
                "reporta un fallo: no me cuadran los totales",
                "mándale una incidencia a ERPlora",
                "avisa a soporte de que la app se queda colgada",
            ),
        },
    ),
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def support_report(ctx: OperationContext, data: SupportReportIn) -> dict:
    """«Report a problem» (BASE-F108): ``POST {SAAS_INTERNAL_URL}/internal/support/report``, signed v1 + v2, with the
    account, the business, the screen and the browser. erplora.com's limit is «Too many attempts…»; erplora.com out of
    reach or refusing it, the address to write to. The text is never logged."""
    account = _reporting_account(ctx)
    subject, description = data.subject.strip(), data.description.strip()
    missing = {}
    if not subject:
        missing["subject"] = gettext("Add a subject.")
    if not description:
        missing["description"] = gettext("Describe the problem, please.")
    if missing:
        raise InvalidPayload(" ".join(missing.values()), code="base.support_report_incomplete", fields=missing)
    request = ctx.request
    hub = request.hub
    body = json.dumps(
        {
            "account": account,
            "hub": hub.slug,
            "hub_id": str(hub.id),
            "page": data.page,
            "browser": request.headers.get("User-Agent", "")[:REPORT_BROWSER_MAX],
            "subject": subject,
            "description": description,
        }
    ).encode()
    headers = {
        "Content-Type": "application/json",
        **signing.signed_headers("POST", SUPPORT_REPORT_PATH, body, int(time.time()), settings.INTERNAL_SHARED_SECRET),
    }
    try:
        status, answer = auth.post(auth.saas_internal_url(SUPPORT_REPORT_PATH), body, headers, auth.TIMEOUT_SECONDS)
    except OSError as failed:
        logger.warning("base.support_report_not_sent hub=%s: the SaaS is unreachable (%s).", hub.slug, failed)
        raise _report_not_sent() from None
    if status == 429:
        raise OperationError(
            gettext("Too many attempts. Please try again in a few minutes."), code="base.too_many_attempts", status=429
        )
    reply_to = _reply_to(answer) if status == 200 else None
    if reply_to is None:
        logger.warning("base.support_report_not_sent hub=%s: the SaaS answered %s.", hub.slug, status)
        raise _report_not_sent()
    logger.info("base.support_report_sent hub=%s", hub.slug)
    return {"reply_to": reply_to}


# ── The pass to erplora.com (the SaaS's ``accounts/hub_pass.py``) ───────────────────────────────────────────────────
# «Upgrade plan» and «erplora.com» arrive already signed in. The Hub signs and the SaaS only checks, so nothing asks the
# SaaS anything per request. It is signed at the click, never in the shell's HTML: it would expire in a
# minute and every script of the page could read it. The pass opens a session, so it is never logged.
from django.core import signing as django_signing  # noqa: E402

from base.schemas import SaasPassIn, SaasPassOut  # noqa: E402

#: erplora.com's door and its salt: a value signed for anything else with the same secret is no pass.
SAAS_PASS_PATH = "/hub-pass/"
SAAS_PASS_SALT = "erplora.hub-pass.v1"


@operation(
    "base.saas_pass.create",
    kind="command",
    permission=VIEW_HOME,
    input=SaasPassIn,
    output=SaasPassOut,
    # A pass in a chat would stay in its history and in the model's context for a minute.
    ai=INTERNAL,
    database=False,
)
def saas_pass_create(ctx: OperationContext, data: SaasPassIn) -> dict:
    """The address of erplora.com with a pass of this person to this business's plan or panel: a minute, one use. The
    SaaS decides again whether the account is a member; ``business`` here only for who may see that button."""
    account = _session_account(ctx)
    if account is None:
        raise PermissionDenied(
            gettext("Sign in with your erplora.com account to go there directly."), code="base.saas_pass_needs_account"
        )
    if data.next == "business" and not ctx.has(OPEN_MANAGEMENT):
        raise PermissionDenied(
            gettext("You don't have permission to manage this business on erplora.com."),
            code="base.saas_pass_needs_management",
        )
    secret = settings.INTERNAL_SHARED_SECRET
    if not secret:
        # Django's signer would fall back on SECRET_KEY, and erplora.com would refuse that pass.
        logger.error("base.saas_pass_unavailable hub=%s: INTERNAL_SHARED_SECRET is empty.", ctx.request.hub.slug)
        raise OperationError(
            gettext("We could not open erplora.com directly."), code="base.saas_pass_unavailable", status=503
        )
    token = django_signing.dumps(
        {"user": account, "hub": ctx.request.hub.slug, "next": data.next, "nonce": secrets.token_urlsafe(32)},
        key=secret,
        salt=SAAS_PASS_SALT,
    )
    return {"url": auth.saas_url(f"{SAAS_PASS_PATH}?{urlencode({'pass': token})}")}


# ── Apps turned on and off by the business, with the plan's limit ──────────────────────────────────────────────────
# The rules are base.activation's; here, their rows (base.AppActivation) under a lock of the business's rows, so two
# people at once never both pass the limit, and the events. Turning an app off never drops its tables.
#
# In a hub with its own database an app whose tables its database
# does not have yet (``Hub.schema_apps``, what the migrator confirmed) is ``creating``: the answer says so (the route's
# 202), the event ``base.app.activation_requested`` is recorded and the hub's ``hub_due`` rung after the COMMIT; the
# worker makes its tables (``ensure_schema``) and turns it on (``base.app.activation_settle``: ``base.app.enabled``, its
# live notice), or ``failed`` with why, tried again at 1, 5 and 15 minutes and then every hour, or by hand
# (``base.app.retry``). What it needs goes in the same plan. One whose tables it has is on at once. A
# business without its own database turns every app on at once: none is
# served, only the suite's tests written before the tenancy still have one (``base/tenancy/tests/legacy.py``).
from functools import cache as _cache  # noqa: E402
from typing import Any  # noqa: E402

from live.meta import module_configs  # noqa: E402
from live.operations import on_commit as after_commit  # noqa: E402,F811

from base import activation, entitlement, home  # noqa: E402
from base.activation import CREATING, FAILED, ON  # noqa: E402
from base.models import AppActivation  # noqa: E402
from base.schemas import AppActivationSettleIn, AppActivationSettleOut, AppChangeIn, AppChangeOut  # noqa: E402
from base.tenancy import migrator  # noqa: E402

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


class AppLimitReached(OperationError):
    """Turning on one more app the business chooses, at its plan's limit (``plan.max_apps``): 402, with the limit and
    the chosen apps on, for the screen's notice and its «Upgrade plan»."""

    status = 402
    code = "base.app_limit_reached"

    def __init__(self, message: str, *, max_apps: int, enabled: int) -> None:
        super().__init__(message)
        self.max_apps, self.enabled = max_apps, enabled

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"].update(max_apps=self.max_apps, enabled=self.enabled)
        return envelope


class AppRequired(Conflict):
    """Turning off an app another app on needs: 409, with those apps (they go off first)."""

    def __init__(self, message: str, *, required_by: list[str]) -> None:
        super().__init__(message, code="base.app_required")
        self.required_by = list(required_by)

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"]["required_by"] = list(self.required_by)
        return envelope


class AppVetoed(Conflict):
    """An app refused to go off or on (its ``can_disable``, ``can_enable``): 409, with its reason as the message and
    its id."""

    def __init__(self, message: str, *, app: str) -> None:
        super().__init__(message, code="base.app_vetoed")
        self.app = app

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"]["app"] = self.app
        return envelope


def _business_hub(ctx: OperationContext) -> Hub | None:
    return Hub.objects.filter(slug=ctx.scope.key).first()


def _business_module(ctx: OperationContext, said: str, hub: Hub | None) -> Any:
    """The module ``said`` names (its id, or its name as the person says it: ``queries.find_app``) as this business
    shows it; 404 for any other (the platform, or one it never shows), 409 ``base.app_ambiguous`` for a name of several."""
    return queries.find_app(said, demo=bool(hub and hub.is_demo), language=ctx.language)


def _locked_states(ctx: OperationContext, graph: dict) -> dict[str, activation.Activation]:
    """Every module's state in the business, its rows locked until the COMMIT: a business on its baseline writes it
    down first (another doing it at the same time leaves its rows: ON CONFLICT DO NOTHING). The rows are read again
    once locked, a new statement, which sees what another committed meanwhile."""
    host = ctx.scope.key
    rows = AppActivation.objects.filter(host=host)
    if not rows.exists():
        AppActivation.objects.bulk_create(
            [
                AppActivation(host=host, app=label, state=row.state, chosen=row.chosen)
                for label, row in activation.baseline(graph).items()
            ],
            ignore_conflicts=True,
        )
    list(rows.select_for_update().order_by("app").values_list("id", flat=True))
    return activation.effective(queries.app_activations(host), graph)


def _write_states(host: str, changes: dict[str, activation.Activation]) -> None:
    """Write ``changes`` and, after the COMMIT of the running change, forget what the cache kept of the business. A row
    that goes ``creating`` waits for no time (the worker takes it now) and keeps its failed attempts; one that goes on or
    off has none left."""
    after_commit(partial(activation.forget, host))
    now = timezone.now()
    existing = set(AppActivation.objects.filter(host=host, app__in=list(changes)).values_list("app", flat=True))
    for label, row in changes.items():
        if label in existing:
            settled = {"target": _code_leaf(label)} if row.state == CREATING else {"attempts": 0, "last_error": ""}
            AppActivation.objects.filter(host=host, app=label).update(
                state=row.state, chosen=row.chosen, changed_at=now, next_attempt_at=None, **settled
            )
    AppActivation.objects.bulk_create(
        AppActivation(
            host=host,
            app=label,
            state=row.state,
            chosen=row.chosen,
            target=_code_leaf(label) if row.state == CREATING else "",
        )
        for label, row in changes.items()
        if label not in existing
    )


@_cache
def _code_leaves() -> dict[str, str]:
    """This code's last migration of each app (its migrations never change while the process runs)."""
    return dict(migrator.code_migrations().leaves)


def _code_leaf(label: str) -> str:
    """The last migration of ``label`` in this code, which its tables are made to; ``""`` for an app without any."""
    return _code_leaves().get(label, "")


def _apps_without_migrations() -> frozenset[str]:
    """The modules with no migration: created in every hub by definition (they have no tables)."""
    return frozenset(activation.module_graph()) - set(_code_leaves())


def apps_created(hub: Hub | None) -> frozenset[str] | None:
    """The modules whose tables ``hub``'s own database has: what the migrator confirmed (``Hub.schema_apps``; the
    worker's ``ensure_schema`` makes what it lacks and is a no-op for what it has) and those without migrations;
    ``None`` for a hub that shares its database, where every app has them."""
    if not has_own_database(hub):
        return None
    return frozenset(hub.schema_apps or ()) | _apps_without_migrations()


def _tables_first(
    changes: dict[str, activation.Activation],
    current: dict[str, activation.Activation],
    created: frozenset[str] | None,
) -> dict[str, activation.Activation]:
    """``changes`` as they are written: when an app they turn on lacks its tables, every app they turn on is
    ``creating`` (one plan); an app already on stays on."""
    turning_on = [label for label, row in changes.items() if row.on and not current[label].on]
    if created is None or all(label in created for label in turning_on):
        return changes
    return {
        label: activation.Activation(CREATING, row.chosen) if label in turning_on else row
        for label, row in changes.items()
    }


def _ring(hub: Hub) -> None:
    """The hub has tables to make: due in ``hub_due`` now, so the worker takes it at its next tick (after the COMMIT of
    the change that asked for them; on control)."""
    HubDue.mark_due(hub, timezone.now())


def _wanted(listed: Iterable[str], selected: set[str], graph: dict) -> list[str]:
    """The apps of a blueprint's manifest a load turns on: those ``selected``, when the person chose some."""
    return [app for app in dict.fromkeys(listed) if app in graph and (not selected or app in selected)]


def _being_set_up(ctx: OperationContext, listed: Iterable[str], selected: set[str]) -> set[str]:
    """Which of the apps a load turns on its hub's own database is still making the tables of, read from their rows."""
    states = activation.states_of(ctx.scope)
    return {app for app in _wanted(listed, selected, activation.module_graph()) if states[app].state == CREATING}


def _waiting_loads() -> list[ImportBatch]:
    """The loads of this business still waiting for an app, oldest first, locked as what is written on them is."""
    return list(
        ImportBatch.objects.select_for_update()
        .filter(report__apps__contains=[{"status": blueprint.WAITING}], undone_at__isnull=True)
        .order_by("created_at", "id")
    )


def _stop_waiting(ctx: OperationContext, loads: Iterable[ImportBatch], apps: Collection[str] | None, reason: Any) -> None:
    """``loads`` stop waiting for ``apps`` (``None``: for any): their report says ``reason``, and they load nothing."""
    for load in loads:
        waited = [app for app in blueprint.waiting_apps(load) if apps is None or app in apps]
        if waited:
            blueprint.stop_waiting(ctx, load, waited, reason)
            load.save(update_fields=["report", "status", "created_rows"])


def _load_what_waited(ctx: OperationContext, on: Iterable[str]) -> None:
    """The apps ``on`` just went on: what the loads of this business waited to bring of them comes now, in this same
    transaction (hub#609). Nothing but those rows says what waits: a worker that dies here undid the app going on, and
    the next one does both, so nothing is lost or left half done. Oldest first: what is there already is left as it is."""
    on = set(on)
    for load in _waiting_loads():
        waited = set(blueprint.waiting_apps(load)) & on
        if waited:
            blueprint.finish_waiting(ctx, load, waited)
            load.save(update_fields=["report", "status", "created_rows"])
            record_event(ctx, events.BLUEPRINT_IMPORTED, {"id": str(load.pk), "status": load.status})


def _turn_on_listed(ctx: OperationContext, listed: Iterable[str], selected: set[str]) -> dict[str, str]:
    """Before a blueprint loads, turn on the apps its manifest lists (only those ``selected``, when the person chose
    some) that are off here, each through ``base.app.enable``: its plan's limit, its rights, what it needs along and
    its event, as if the person turned it on in Apps. Their roots first, chosen, so what they need comes along and
    does not count against the limit (as a vertical's template, ``base.activation.template``); then any listed app
    still off. An app refused stays off and its reason is returned, by app: the rest are turned on and load, or wait
    for their tables (``creating``: ``_being_set_up``)."""
    graph = activation.module_graph()
    wanted = _wanted(listed, selected, graph)
    roots = activation.roots(set(wanted) | activation.needs(wanted, graph), graph)
    enable = get_operation("base.app.enable")
    blocked = entitlement.blocked_apps(ctx.scope)
    refused: dict[str, str] = {}
    for app in [app for app in wanted if app in roots] + [app for app in wanted if app not in roots]:
        if app not in blocked and activation.states_of(ctx.scope)[app].on:
            continue
        try:
            enable(ctx, AppChangeIn(app=app))
        except OperationError as refusal:
            refused[app] = refusal.message
    return refused


def _named(ctx: OperationContext, labels: Iterable[str]) -> list[dict[str, str]]:
    names = {config.label: config.verbose_name for config in module_configs()}
    with translation.override(ctx.language):
        return [{"id": label, "name": str(names.get(label, label))} for label in labels]


def _names_said(ctx: OperationContext, labels: list[str]) -> str:
    """«A», «A and B», «A, B and C», in the language of who asks."""
    with translation.override(ctx.language):
        names = [item["name"] for item in _named(ctx, labels)]
        if len(names) == 1:
            return names[0]
        return gettext("%(first)s and %(last)s") % {"first": ", ".join(names[:-1]), "last": names[-1]}


def _app_answer(label: str, row: activation.Activation, along: list[dict[str, str]], *, already: bool) -> dict:
    """``already``: it was in that state before (on, or off), and nothing went on or off: the assistant says so."""
    return {"app": label, "state": row.state, "chosen": row.wanted and row.chosen, "along": along, "already": already}


@operation(
    "base.app.enable",
    kind="command",
    permission=ADMINISTER_HUB,
    input=AppChangeIn,
    output=AppChangeOut,
    # A dict, not AI(...): AI has no ``check`` (base.assistant.check_of), the read run before the card (hub#542).
    ai={
        "description": "Turns on one of this business's apps (by its name as the person says it, or its id), with the "
        "apps it needs, which come along: it shows in the menu and can be used, with the data it had. Refused when the "
        "plan's limit of apps is reached (turn one off, or upgrade the plan on erplora.com), a paid app is not "
        "subscribed, the app itself says why not or the name fits several apps (ask which one). state=creating: it is "
        "being set up and is on in a moment. already=true: it was on (or being set up) already, nothing changed. Use "
        "this when an app should be available again, not another app's settings operation.",
        "risk": "normal",
        "check": "base.app.get",
        "asks": {
            "en": (
                "turn on the customers app",
                "activate the bookings app",
                "can you turn on the kitchen module?",
                "bring back the time clock app I took off the menu",
            ),
            "es": (
                "activa la app de clientes",
                "ponme la app de cocina",
                "activa el módulo de citas",
                "recupera la app de fichajes que quité del menú",
                "vuelve a dejar disponible la app de tareas",
            ),
        },
    },
)
def app_enable(ctx: OperationContext, data: AppChangeIn) -> dict:
    """BASE-F18/F24: the app on and chosen, and what it needs on along with it (not chosen: it does not count). A
    paid one without its right (or needing one) is 402 ``app_entitlement_blocked``; one more chosen app at the plan's
    limit, 402 ``base.app_limit_reached`` (a lower limit than the chosen ones turns nothing off: it only refuses this);
    409 ``base.app_vetoed`` when it, or what would come along, refuses (``can_enable``, hub#694).
    In a hub with its own database whose tables for it (or for what it needs) are not made yet, ``creating`` (202):
    the worker makes them and turns it on; one that failed is tried again."""
    with activation.changing(ctx.scope.key):
        return _enable(ctx, data)


def _enable(ctx: OperationContext, data: AppChangeIn) -> dict:  # noqa: C901
    hub = _business_hub(ctx)
    app = _business_module(ctx, data.app, hub).label
    graph = activation.module_graph()
    blocked = entitlement.blocked_apps(ctx.scope)
    for label in [app, *sorted(activation.needs([app], graph))]:
        if label in blocked:
            raise entitlement.refused(label, ctx.language)
    current = activation.states_of(ctx.scope)
    if not activation.enabling(app, current, graph):
        return _unchanged(hub, app, current[app])
    current = _locked_states(ctx, graph)
    changes = activation.enabling(app, current, graph)
    if not changes:
        return _unchanged(hub, app, current[app])
    vetoed = activation.veto(
        [label for label in changes if not current[label].on], ctx=ctx, hook=activation.CAN_ENABLE
    )
    if vetoed is not None:
        raise AppVetoed(vetoed[1], app=vetoed[0])
    if changes.get(app, current[app]).chosen and not (current[app].wanted and current[app].chosen):
        limit = queries.app_limit(hub)
        shown = {config.label for config in home.shown_modules(demo_hub=bool(hub and hub.is_demo))}
        enabled = activation.chosen_on(current, among=shown)
        if limit is not None and enabled >= limit:
            with translation.override(ctx.language):
                message = ngettext(
                    "You have reached the %(count)s-app limit of your plan. Upgrade your plan or turn one off.",
                    "You have reached the %(count)s-app limit of your plan. Upgrade your plan or turn one off.",
                    limit,
                ) % {"count": limit}
            raise AppLimitReached(message, max_apps=limit, enabled=enabled)
    changes = _tables_first(changes, current, apps_created(hub))
    _write_states(ctx.scope.key, changes)
    on_now = [label for label, row in changes.items() if row.on]
    if hub is not None and not hub.is_demo and on_now:
        _sync_photo_blocks(hub, on_now)
    along = [label for label in changes if label != app]
    answer = changes.get(app, current[app])
    if any(row.state == CREATING for row in changes.values()):
        after_commit(partial(_ring, hub))
    name = events.APP_ACTIVATION_REQUESTED if answer.state == CREATING else events.APP_ENABLED
    record_event(ctx, name, {"app": app, "along": along})
    if on_now:
        _load_what_waited(ctx, on_now)
    return _app_answer(app, answer, _named(ctx, along), already=current[app].on)


def _unchanged(hub: Hub | None, label: str, row: activation.Activation) -> dict:
    """Turning on an app on and chosen already, or being created (its hub rung again: a ring lost is found again):
    ``already``, nothing went on."""
    if row.state == CREATING:
        after_commit(partial(_ring, hub))
    return _app_answer(label, row, [], already=True)


@operation(
    "base.app.disable",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=AppChangeIn,
    output=AppChangeOut,
    # A dict, not AI(...): AI has no ``check`` (base.assistant.check_of), the read run before the card (hub#542).
    ai={
        "description": "Turns off one of this business's apps (by its name as the person says it, or its id): it "
        "leaves everyone's menu and its screens stop opening; the apps that came along only with it go off too. Nothing "
        "is deleted: turned on again, it has its data; an app the business's country requires stays on. Refused while "
        "another app on needs it, when the business's country requires the app on, when the app itself says why not "
        "yet or when the name fits several apps (ask which one). already=true: it was off already.",
        "risk": "high",
        "check": "base.app.get",
        "asks": {
            "en": (
                "turn off the reservations app",
                "we don't use tables anymore, switch that app off",
                "deactivate the loyalty module",
            ),
            "es": (
                "desactiva la app de reservas",
                "apaga la app de mesas, ya no la usamos",
                "quita el módulo de fidelización, no lo necesitamos",
            ),
        },
    },
)
def app_disable(ctx: OperationContext, data: AppChangeIn) -> dict:
    """BASE-F23/F25: the app off, and what came along only with it but what the business's country requires on, which
    stays on (hub#997). 409 ``base.app_required`` while an app on needs it (naming the ones to turn off first); 409
    ``base.app_vetoed`` when it, one that would go off with it or one of those that need it refuses (``can_disable``, or
    base's reason for one the country requires on: hub#619, hub#997; nobody can turn off
    first one that refuses). Its tables are never dropped."""
    with activation.changing(ctx.scope.key):
        return _disable(ctx, data)


def _disable(ctx: OperationContext, data: AppChangeIn) -> dict:
    hub = _business_hub(ctx)
    app = _business_module(ctx, data.app, hub).label
    graph = activation.module_graph()
    if not activation.states_of(ctx.scope)[app].wanted:
        return _app_answer(app, activation.OFF_ROW, [], already=True)
    current = _locked_states(ctx, graph)
    if not current[app].wanted:
        return _app_answer(app, activation.OFF_ROW, [], already=True)
    # What the business's country requires on never goes off, by itself nor along with this one (hub#997).
    country = hub.country if hub else ""
    kept = activation.mandatory_on(current, country)
    keeping = activation.keeping_on(app, current, graph, kept)
    said = activation.refusals(keeping, ctx=ctx, kept=kept, country=country)
    refused = queries.app_off_refusal(ctx, app, current, graph, said, kept)
    if refused is not None:
        raise AppVetoed(refused[1], app=refused[0])
    needed = activation.required_by(app, current, graph)
    if needed:
        # The ones to turn off: those chosen (what came along goes off with them).
        first = [label for label in needed if current[label].chosen] or needed
        with translation.override(ctx.language):
            message = gettext("Turn off %(apps)s first.") % {"apps": _names_said(ctx, first)}
        raise AppRequired(message, required_by=needed)
    changes = activation.disabling(app, current, graph, kept)
    _write_states(ctx.scope.key, changes)
    along = [label for label in changes if label != app]
    record_event(ctx, events.APP_DISABLED, {"app": app, "along": along})
    _stop_waiting(ctx, _waiting_loads(), changes, blueprint.STOPPED_TURNED_OFF)
    return _app_answer(app, activation.OFF_ROW, _named(ctx, along), already=False)


@operation(
    "base.app.retry",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=AppChangeIn,
    output=AppChangeOut,
    # A dict, not AI(...): AI has no ``check`` (base.assistant.check_of), the read run before the card (hub#542, hub#539).
    ai={
        "description": "Tries again to set up one of this business's apps that could not be turned on (its state "
        "«failed» in base.app.list; by its name as the person says it, or its id), with what it needs that failed too: "
        "it is set up in a moment and then shows in the menu. Refused for an app that is not waiting for it, or when the "
        "name fits several apps (ask which one).",
        "risk": "normal",
        "check": "base.app.get",
        "asks": {
            "en": (
                "the bookings app could not be turned on, try again",
                "retry setting up the kitchen app",
                "try turning on the website app again",
            ),
            "es": (
                "la app de reservas no se pudo activar, inténtalo otra vez",
                "reintenta preparar la app de cocina",
                "vuelve a intentar activar la web",
            ),
        },
    },
)
def app_retry(ctx: OperationContext, data: AppChangeIn) -> dict:
    """An app whose tables could not be made (``failed``) is ``creating`` again now, with what it needs
    that failed too, and its hub rung (the worker also tries again by itself). 409 ``base.app_not_failed`` for any
    other app, and in a hub that shares its database, where nothing is ever made later; 409 ``base.app_vetoed``
    when it refuses to go on (``can_enable``, as «Turn on»). The app by its name or its id, as ``base.app.enable`` takes
    it (hub#539)."""
    with activation.changing(ctx.scope.key):
        hub = _business_hub(ctx)
        app = _business_module(ctx, data.app, hub).label
        current = _locked_states(ctx, activation.module_graph()) if has_own_database(hub) else None
        if current is None or current[app].state != FAILED:
            raise Conflict(gettext("This app is not waiting to be set up again."), code="base.app_not_failed")
        graph = activation.module_graph()
        closure = {app, *activation.needs([app], graph)}
        changes = {
            label: activation.Activation(CREATING, row.chosen)
            for label, row in current.items()
            if label in closure and row.state == FAILED
        }
        vetoed = activation.veto(changes, ctx=ctx, hook=activation.CAN_ENABLE)
        if vetoed is not None:
            raise AppVetoed(vetoed[1], app=vetoed[0])
        _write_states(ctx.scope.key, changes)
        after_commit(partial(_ring, hub))
        along = [label for label in changes if label != app]
        record_event(ctx, events.APP_ACTIVATION_REQUESTED, {"app": app, "along": along})
        return _app_answer(app, changes[app], _named(ctx, along), already=False)


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
    activations_rung_at(hub.pk, queries.activation_next_at(host))


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


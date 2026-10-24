"""Writes of base: opening the Hub's session for the person the SaaS vouched for, the clock of the apps' scheduled
tasks (``base.scheduler``), the outbox relay's deliveries (``base.relay``) and the registry of hubs (``base.Hub``,
the operations ``base.hub.*``).

The session is not an ``@operation``: it runs before there is an actor, for ``/auth/callback`` only, and needs the
request to log in. Phase 1 keeps it on ``django.contrib.auth`` + ``Membership``; phase 2 replaces
it with the hub's ``DeviceSession`` (PLAN-SAAS §2.1).

Two doors, each with its own local copy of the SaaS account: a customer entering their hub
(:func:`open_session_from_saas`, ``saas:<id>``, never staff) and the platform's staff entering the
Hub admin on the platform host (:func:`open_admin_session_from_saas`, ``saas-staff:<id>``, round 13,
PLAN §18.1). Separate copies, so an account that is both staff and a hub member neither loses
``is_staff`` in the admin nor gains it on its hub when it enters by the other door.

The registry's operations (plan 2026-10-17, §1.5) are what the SaaS's signed ``/internal/hubs/{id}`` calls run
(``base.internal``), as the platform only (``base.internal_only`` for anyone else), on the registry's scope. Phase 1
has no database to clone: a sign-up is ``ready`` in its own transaction, and the SaaS hears it once it commits
(:func:`report_ready`); if that call fails, the SaaS asks ``GET /internal/hubs/{id}`` two minutes later.

Settings › Data (APP-BASE-2, PLAN-HUB round 2026-10-21): ``base.blueprint.import`` loads a template or a file and keeps
it as an ``ImportBatch``, ``base.import.undo`` removes exactly what one load created and ``base.hub.reset`` empties the
apps chosen (only with the hub's own database); the rules are ``base.blueprint``'s.

The demos (plan 2026-10-17, §1.6 and §1.7) are rows of that registry too: ``base.demo.create`` gives a browser of the
SaaS its live demo or a new empty ``demo-<8 hex>`` for ``DEMO_TTL_MINUTES``; ``base.demo.code_create`` a one-time
code into it for that browser only, which the demo's ``/auth/callback`` redeems here (:func:`redeem_demo_code`) and
turns into the owner's session (:func:`open_demo_session`); the worker's reaper (:func:`reap_demos`) purges the ones
that ended, each with ``base.demo.purge``, and forgets them after ``DEMO_TOMBSTONE_DAYS``.
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
from collections.abc import Callable, Iterable
from contextvars import ContextVar
from functools import partial
from uuid import UUID

import pydantic
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.db.models import Max, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.http import HttpRequest
from django.utils import timezone, translation
from django.utils.translation import gettext, ngettext
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied, Unauthorized
from live.live_registry import ALL_EVENTS
from live.models import OutboxEvent
from live.operations import get as get_operation
from live.operations import operation
from live.outbox import notify, record_event
from live.slugs import DEMO_SLUG_PREFIX, validate_hub_slug
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from base import access, auth, blueprint, events, queries, registry, signing, system
from base.registry import REGISTRY_SCOPE, hub_answer, internal_only
from base.auth import PLATFORM_ADMIN, PLATFORM_SUPPORT, RedeemedUser
from base.middleware import PLATFORM_SESSION_HOST, session_host
from base.models import (
    AccessSettings,
    Credential,
    DemoCode,
    EventDelivery,
    Hub,
    ImportBatch,
    Membership,
    Profile,
    SessionOwner,
    TaskSchedule,
    TrustedDevice,
)
from base.media import AVATARS_FOLDER
from base.operations import hub_id
from base.storage import hub_prefix
from base.permissions import ADMINISTER_HUB, VIEW_HOME
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
from base.schemas import (
    BlueprintImportIn,
    BlueprintSourceIn,
    BlueprintSummaryOut,
    DemoCodeIn,
    DemoCodeOut,
    DemoCreateIn,
    DemoOut,
    DemoSlugIn,
    DemoStatusOut,
    FailedEventCountOut,
    FailedEventDiscardIn,
    FailedEventIn,
    FailedEventOutId,
    FailedEventRetryAllIn,
    HubCancelIn,
    HubOut,
    HubRegisterOut,
    HubRegistryIn,
    HubRestoreIn,
    HubSeedLocalIn,
    HubSeedLocalOut,
    HubStateIn,
    HubResetIn,
    HubResetOut,
    HubStateOut,
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
    SessionRevokeIn,
    SessionRevokeOut,
)

logger = logging.getLogger(__name__)

MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"
#: The SaaS account the session belongs to (``SessionOwner`` is the index /internal/sessions/revoke reads).
SAAS_USER_ID_SESSION_KEY = "saas_user_id"
#: Read-only group of ``platform_support`` in the Hub admin (the SaaS's ``support``). Phase 2
#: replaces it with the ``StaffUser`` mark (PLAN §17).
SUPPORT_GROUP = "support"


class InactiveUser(Exception):
    """The Hub's copy of the user was deactivated (in the admin): no session, whatever the SaaS says."""


#: The username prefix of the customer copies of SaaS accounts (:func:`username_for`).
SAAS_USERNAME_PREFIX = "saas:"


def username_for(saas_user_id: str) -> str:
    """The customer copy of a SaaS account (hub door)."""
    return f"{SAAS_USERNAME_PREFIX}{saas_user_id}"


def staff_username_for(saas_user_id: str) -> str:
    """The staff copy of a SaaS account (Hub admin door); never has a ``Membership``."""
    return f"saas-staff:{saas_user_id}"


def _local_copy(redeemed: RedeemedUser, *, username: str, is_staff: bool, is_superuser: bool):
    """Get or create ``username`` and make it say what the SaaS says; ``InactiveUser`` if deactivated."""
    user_model = get_user_model()
    first_name = redeemed.name[: user_model._meta.get_field("first_name").max_length]
    wanted = {"email": redeemed.email, "first_name": first_name, "is_staff": is_staff, "is_superuser": is_superuser}
    # get_or_create: two first entries at once end in one user, not an IntegrityError.
    user, _ = user_model.objects.get_or_create(
        username=username,
        defaults={**wanted, "password": make_password(None)},
    )
    if not user.is_active:
        raise InactiveUser(user.username)
    changed = [field for field, value in wanted.items() if getattr(user, field) != value]
    if changed:
        for field in changed:
            setattr(user, field, wanted[field])
        user.save(update_fields=changed)
    return user


def _log_in(
    request: HttpRequest,
    user,
    saas_user_id: str,
    *,
    device: TrustedDevice | None = None,
    credential: str = SessionOwner.Credential.ACCOUNT,
) -> None:
    """Log ``user`` in (a new session key) as the SaaS account ``saas_user_id``; on a hub's ``device``, for as long
    as that device and the business allow (``base.access.session_lifetime``), fixed now."""
    login(request, user, backend=MODEL_BACKEND)
    request.session[SAAS_USER_ID_SESSION_KEY] = saas_user_id
    if device is not None:
        policy = queries.access_settings().pin_policy
        request.session.set_expiry(timezone.now() + access.session_lifetime(device.mode, policy))
    _note_the_owner(request, saas_user_id, device=device, credential=credential)


def _note_the_owner(
    request: HttpRequest,
    saas_user_id: str,
    *,
    device: TrustedDevice | None = None,
    credential: str = SessionOwner.Credential.ACCOUNT,
) -> None:
    """Note whose and where the new session is (``SessionOwner``), so ``base.session.revoke`` finds it by index, and
    on which device and with which credential it was opened.

    ``login`` gives the session a new key and saves it, unless it flushed another user's session first: then it has
    no key until it is saved, which happens here, in the login's transaction.
    """
    if request.session.session_key is None:
        request.session.save()
    SessionOwner.objects.update_or_create(
        session_id=request.session.session_key,
        defaults={
            "saas_user_id": saas_user_id,
            "host": session_host(request) or "",
            "device_id": None if device is None else device.pk,
            "credential": credential,
        },
    )


@transaction.atomic
def open_session_from_saas(request: HttpRequest, redeemed: RedeemedUser, slug: str):
    """Get or create the customer copy, set its role on ``slug`` and log it in (a new session key).

    The local user is a copy of a customer of the SaaS: never staff nor superuser, so a hub role
    never opens the Hub's ``/admin/`` (that one belongs to the platform's staff). A copy raised to
    staff by hand is lowered again here.
    """
    user = _local_copy(redeemed, username=username_for(redeemed.user_id), is_staff=False, is_superuser=False)
    Membership.objects.update_or_create(user=user, host=slug, defaults={"role": redeemed.role})
    device = trust_device(request, user)
    _log_in(request, user, redeemed.user_id, device=device)
    _end_other_devices(slug, device)
    return user


@transaction.atomic
def open_admin_session_from_saas(request: HttpRequest, redeemed: RedeemedUser):
    """Log the platform's staff into the Hub admin (a new session key), as the SaaS vouched.

    ``platform_admin`` is staff and superuser; ``platform_support`` is staff in the read-only
    ``support`` group. Any other role is a programming error: ``base.auth`` refuses it first. The
    session is for the account's staff copy, never for its customer copy.
    """
    if redeemed.role not in (PLATFORM_ADMIN, PLATFORM_SUPPORT):
        raise ValueError(f"The Hub admin takes only a platform role, not {redeemed.role!r}.")
    superuser = redeemed.role == PLATFORM_ADMIN
    user = _local_copy(
        redeemed, username=staff_username_for(redeemed.user_id), is_staff=True, is_superuser=superuser
    )
    support = _support_group()
    if superuser:
        user.groups.remove(support)
    else:
        user.groups.add(support)
    _log_in(request, user, redeemed.user_id)
    return user


def _support_group() -> Group:
    """The ``support`` group with every ``view_*`` permission and nothing else (created on first use)."""
    group, _ = Group.objects.get_or_create(name=SUPPORT_GROUP)
    group.permissions.set(Permission.objects.filter(codename__startswith="view_"))
    return group


# ── The scheduled tasks' clock (base.scheduler) ────────────────────────────────────────────────


def sync_task_schedules(declared: Iterable[tuple[str, str, str, str, dt.datetime]]) -> None:
    """Write the tasks the apps declare, ``(app_label, name, operation, cron, first_run)``; forget the rest.

    Not an ``@operation``: the worker calls it for no hub's user when it starts. A task it already knew keeps
    its ``next_run`` and ``last_run`` (a boot never resets the clock) and takes the declared operation and
    cron; a new one is due at ``first_run``.
    """
    with transaction.atomic():
        keep = set()
        for app_label, name, operation, cron, first_run in declared:
            TaskSchedule.objects.update_or_create(
                app_label=app_label,
                name=name,
                defaults={"operation": operation, "cron": cron},
                create_defaults={"operation": operation, "cron": cron, "next_run": first_run},
            )
            keep.add((app_label, name))
        gone = [row.pk for row in TaskSchedule.objects.all() if (row.app_label, row.name) not in keep]
        TaskSchedule.objects.filter(pk__in=gone).delete()


def run_next_due_task(
    now: dt.datetime,
    *,
    execute: Callable[[str], object],
    reschedule: Callable[[str, dt.datetime], dt.datetime],
) -> tuple[str, bool] | None:
    """Claim one task due at ``now``, run it and move its ``next_run``, all in one transaction.

    ``SELECT … FOR UPDATE SKIP LOCKED``: a second worker (a deploy overlaps the old one and the new one)
    skips the row this one holds, and once it commits the row is no longer due. ``execute(operation)``
    runs in a savepoint: a task that raises is logged and its writes undone, and it is rescheduled all the
    same, so it runs again at its next time instead of on every tick; ``last_run`` is the last run that
    finished. ``reschedule(cron, now)`` is the next time strictly after ``now``: missed times collapse into
    this one run. Returns ``("<app>.<name>", ran)``,
    or ``None`` when nothing is due.
    """
    with transaction.atomic():
        row = (
            TaskSchedule.objects.select_for_update(skip_locked=True)
            .filter(next_run__lte=now)
            .order_by("next_run", "app_label", "name")
            .first()
        )
        if row is None:
            return None
        ran = True
        try:
            with transaction.atomic():
                execute(row.operation)
        except Exception:
            ran = False
            logger.exception(
                "scheduler: %s (%s) failed; its writes were undone and it runs again at its next time.",
                row,
                row.operation,
            )
        row.next_run = reschedule(row.cron, now)
        if ran:
            row.last_run = now
        row.save(update_fields=["next_run", "last_run"])
    return str(row), ran


# ── The outbox relay's deliveries (base.relay) ───────────────────────────────────────────────────────────────────

#: The longest ``last_error`` a delivery keeps (the start of the error is what tells it).
LAST_ERROR_MAX_LENGTH = 2000
#: What a delivery past the deepest level says (``base.relay.MAX_EVENT_DEPTH``).
TOO_DEEP = "Not delivered: its depth, {depth}, is past the deepest level of events ({limit})."
#: The events the running delivery records, so they are handed over one level deeper, in its transaction.
_recorded_by_the_delivery: ContextVar[list[OutboxEvent] | None] = ContextVar(
    "base_recorded_by_the_delivery", default=None
)


@receiver(post_save, sender=OutboxEvent, dispatch_uid="base.services.recorded_by_the_delivery")
def _note_an_event_recorded_by_the_delivery(sender, instance: OutboxEvent, created: bool, **kwargs) -> None:
    recorded = _recorded_by_the_delivery.get()
    if created and recorded is not None:
        recorded.append(instance)


def relay_take_events(
    now: dt.datetime, *, listeners: Callable[[OutboxEvent], list[str]], limit: int, max_depth: int
) -> int:
    """Take up to ``limit`` events nobody took yet, oldest first: one delivery per app of ``listeners(event)``,
    and the event's ``delivered_at`` (taken) in the same transaction. Returns how many it took.

    ``SELECT … FOR UPDATE SKIP LOCKED``: a second worker (a deploy overlaps the old one and the new one) skips the
    events this one holds, and once it commits they are taken.
    """
    with transaction.atomic():
        taken = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(delivered_at__isnull=True)
            .order_by("created_at", "id")[:limit]
        )
        _hand_over(taken, now=now, depth=0, listeners=listeners, max_depth=max_depth)
    return len(taken)


def relay_deliver_next(
    now: dt.datetime,
    *,
    deliver: Callable[[str, OutboxEvent], object],
    listeners: Callable[[OutboxEvent], list[str]],
    max_depth: int,
    max_attempts: int,
    backoff: Callable[[int], dt.timedelta],
) -> tuple[EventDelivery, bool] | None:
    """Claim one delivery due at ``now`` (the oldest event first), run its app's reaction and mark it, all in
    one transaction; returns ``(delivery, delivered)``, or ``None`` when nothing is due.

    The claim is ``SKIP LOCKED``, as the scheduler's. ``deliver(app_label, event)`` runs in a savepoint, and the
    events it records (and keeps) are handed over in it, one level deeper: a reaction that raises has its writes
    undone and waits ``backoff(attempts)``; after ``max_attempts`` it is given up (``dead``). Either way it is
    logged with the event, and the other deliveries go on: a refusal of the business (an ``OperationError``) as a
    warning with its code; anything else, and the delivery given up, as an error with its traceback.
    """
    with transaction.atomic():
        delivery = (
            EventDelivery.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("event")
            .filter(status=EventDelivery.Status.PENDING, next_attempt_at__lte=now)
            .order_by("event__created_at", "event_id", "app_label")
            .first()
        )
        if delivery is None:
            return None
        delivery.attempts += 1
        try:
            with transaction.atomic():
                recorded: list[OutboxEvent] = []
                token = _recorded_by_the_delivery.set(recorded)
                try:
                    deliver(delivery.app_label, delivery.event)
                finally:
                    _recorded_by_the_delivery.reset(token)
                # Only what the reaction kept: an event recorded in a savepoint it gave up is gone.
                kept = list(
                    OutboxEvent.objects.filter(pk__in=[event.pk for event in recorded]).order_by("created_at", "id")
                )
                _hand_over(kept, now=now, depth=delivery.depth + 1, listeners=listeners, max_depth=max_depth)
        except Exception as error:
            delivered = False
            delivery.last_error = f"{type(error).__name__}: {error}"[:LAST_ERROR_MAX_LENGTH]
            # A refusal of the business (an ``OperationError``: no issuer yet…) is expected and has its code; a
            # traceback only for the unexpected, and for the delivery given up.
            refused = isinstance(error, OperationError)
            reason = error.code if refused else type(error).__name__
            if delivery.attempts >= max_attempts:
                delivery.status = EventDelivery.Status.DEAD
                _tell_failed(Scope(delivery.event.scope_kind, delivery.event.scope_key))
                logger.exception(
                    "relay: %s gave up on %s (%s) after %d attempts (%s); its writes were undone.",
                    delivery.app_label,
                    delivery.event.name,
                    delivery.event_id,
                    delivery.attempts,
                    reason,
                )
            else:
                delivery.next_attempt_at = now + backoff(delivery.attempts)
                logger.log(
                    logging.WARNING if refused else logging.ERROR,
                    "relay: %s failed on %s (%s) with %s, attempt %d of %d; its writes were undone and it tries "
                    "again at %s.",
                    delivery.app_label,
                    delivery.event.name,
                    delivery.event_id,
                    reason,
                    delivery.attempts,
                    max_attempts,
                    delivery.next_attempt_at.isoformat(),
                    exc_info=not refused,
                )
        else:
            delivered = True
            delivery.status, delivery.delivered_at, delivery.last_error = EventDelivery.Status.DELIVERED, now, ""
        delivery.save(update_fields=["attempts", "status", "next_attempt_at", "last_error", "delivered_at"])
    return delivery, delivered


def _hand_over(
    events: list[OutboxEvent],
    *,
    now: dt.datetime,
    depth: int,
    listeners: Callable[[OutboxEvent], list[str]],
    max_depth: int,
) -> None:
    """One delivery of each event per app that listens to it, at ``depth``; the events are taken (``delivered_at``).

    Past ``max_depth`` the deliveries are written given up, with why: a reaction that records an event another
    reaction answers with an event… never loops.
    """
    if not events:
        return
    too_deep = depth > max_depth
    rows = [
        EventDelivery(
            event=event,
            app_label=app_label,
            depth=depth,
            next_attempt_at=now,
            status=EventDelivery.Status.DEAD if too_deep else EventDelivery.Status.PENDING,
            last_error=TOO_DEEP.format(depth=depth, limit=max_depth) if too_deep else "",
        )
        for event in events
        for app_label in listeners(event)
    ]
    EventDelivery.objects.bulk_create(rows)
    OutboxEvent.objects.filter(pk__in=[event.pk for event in events]).update(delivered_at=now)
    for row in rows if too_deep else ():
        logger.error(
            "relay: %s (%s) not delivered to %s: %s", row.event.name, row.event_id, row.app_label, row.last_error
        )
    for scope in {Scope(row.event.scope_kind, row.event.scope_key) for row in rows} if too_deep else ():
        _tell_failed(scope)


def _tell_failed(scope: Scope) -> None:
    """After the COMMIT, ``scope``'s hub hears that a failed event appeared: its bell and System › Failed events follow
    at once (BASE-F10, APP-BASE-7). A notice, not an outbox event: a listener of every event that failed on it would
    feed itself; and none after a rollback."""
    transaction.on_commit(partial(notify, scope, [events.FAILED_EVENT_CREATED]), robust=True)


# ── The registry of hubs: what the SaaS's /internal/hubs/{id} runs (plan 2026-10-17, §1.5) ──────────────────────

#: The path of the SaaS that hears a business is ready (``hubs/internal.py`` of the SaaS).
READY_PATH = "/internal/hubs/{id}/ready"
#: The statuses a hub never comes back from: the SaaS reads ``hub_purged`` literally (``_restore``).
PURGED_STATUSES = frozenset({Hub.Status.PURGED, Hub.Status.EXPIRED})


def _locked_hub(hub_id: UUID) -> Hub:
    hub = Hub.objects.select_for_update().filter(pk=hub_id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    return hub


def _refuse_purged(hub: Hub) -> None:
    if hub.status in PURGED_STATUSES:
        raise Conflict(gettext("This hub was purged: it cannot come back."), code="hub_purged")


def _slug_taken() -> Conflict:
    return Conflict(gettext("Another hub has this address."), code="base.slug_taken")


@operation("base.hub.register", kind="command", permission=None, input=HubRegistryIn, output=HubRegisterOut)
def hub_register(ctx: OperationContext, data: HubRegistryIn) -> dict:
    """Register the SaaS's business ``data.id`` (or update its name, slug, country…): ``ready`` at once in phase 1.

    A customer's slug never takes a demo's ``demo-…`` nor a reserved name (``base.slug_invalid``); one that is
    another hub's is ``base.slug_taken``. A cancelled hub is restored first (``base.hub_cancelled``); a purged one
    never comes back (``hub_purged``). The SaaS hears ``ready`` after the COMMIT when the row is new or was not
    ready yet; a rename, idempotent, says nothing.
    """
    internal_only(ctx)
    try:
        slug = validate_hub_slug(data.slug)
    except ValueError as invalid:
        raise InvalidPayload(
            gettext("This address cannot name a business (%(reason)s).") % {"reason": invalid},
            code="base.slug_invalid",
        ) from None
    if Hub.objects.filter(slug=slug).exclude(pk=data.id).exists():
        raise _slug_taken()
    now = timezone.now()
    fields = {
        "slug": slug,
        "name": data.name,
        "country": data.country,
        "timezone": data.timezone,
        "language": data.language,
        "vertical": data.vertical or "",
    }
    hub = Hub.objects.select_for_update().filter(pk=data.id).first()
    created = hub is None
    if created:
        try:
            with transaction.atomic():
                hub = Hub.objects.create(id=data.id, status=Hub.Status.READY, ready_at=now, **fields)
        except IntegrityError:
            # A concurrent call took the slug, or registered this same id first (then it is an update).
            hub = Hub.objects.select_for_update().filter(pk=data.id).first()
            if hub is None:
                raise _slug_taken() from None
            created = False
    was_ready = created
    if not created:
        _refuse_purged(hub)
        if hub.status == Hub.Status.CANCELLED:
            raise Conflict(gettext("This hub was cancelled: restore it first."), code="base.hub_cancelled")
        was_ready = hub.status == Hub.Status.READY
        for field, value in fields.items():
            setattr(hub, field, value)
        if not was_ready:
            hub.status, hub.ready_at = Hub.Status.READY, now
        try:
            with transaction.atomic():
                hub.save()
        except IntegrityError:
            raise _slug_taken() from None
    record_event(ctx, events.HUB_REGISTERED, {"id": str(hub.id), "slug": hub.slug, "created": created})
    # Registered as the platform (/internal): Settings › Business (APP-BASE-6) listens on the business's channel, so a
    # name, zone or language changed on erplora.com shows without reloading, after the COMMIT as the photo's.
    transaction.on_commit(partial(notify, Scope("host", hub.slug), [events.HUB_REGISTERED]), robust=True)
    if created or not was_ready:
        transaction.on_commit(partial(report_ready, hub.id), robust=True)
    return {**hub_answer(hub), "created": created}


def report_ready(hub_id: UUID) -> None:
    """Tell the SaaS that ``hub_id`` is ready: ``POST {SAAS_INTERNAL_URL}/internal/hubs/{id}/ready``, signed v1 + v2.

    Called after the COMMIT that made it ready, never inside it. It never raises: a failure is logged and not
    retried, because the SaaS asks ``GET /internal/hubs/{id}`` about a sign-up without its ``ready`` two minutes
    later (``reconcile_hub_states``) and marks it itself.
    """
    path = READY_PATH.format(id=hub_id)
    body = json.dumps({"id": str(hub_id)}).encode()
    headers = {
        "Content-Type": "application/json",
        **signing.signed_headers("POST", path, body, int(time.time()), settings.INTERNAL_SHARED_SECRET),
    }
    try:
        status, _answer = auth.post(auth.saas_internal_url(path), body, headers, auth.TIMEOUT_SECONDS)
    except OSError as failed:
        logger.warning("base.hub.ready_unreported hub=%s: the SaaS is unreachable (%s).", hub_id, failed)
        return
    if 200 <= status < 300:
        logger.info("base.hub.ready_reported hub=%s", hub_id)
    else:
        logger.warning("base.hub.ready_unreported hub=%s: the SaaS answered %s.", hub_id, status)


@operation("base.hub.state_apply", kind="command", permission=None, input=HubStateIn, output=HubStateOut)
def hub_state_apply(ctx: OperationContext, data: HubStateIn) -> dict:
    """Keep the SaaS's photo of ``data.id`` if it is newer than the one kept; an equal or older one changes nothing.

    Phase 1 applies of it what the apps already use: the VeriFactu block and the business's status, through
    ``verifactu.config.sync`` on the hub's slug, and the number's state of WhatsApp (``whatsapp``), through
    ``whatsapp_inbox.channel.sync`` with the photo's version when the app is on in that business (off, the photo
    applies and the block waits for the next one); both in this same transaction, so their notices go out after its
    COMMIT (a block out of contract keeps nothing). Its ``members`` apply on the business's memberships
    (:func:`_apply_members`), in this transaction too. Its modules and plan are read where they are kept: the right
    to a paid app (``base.entitlement``) and «Plan and limits» (``base.plan.usage``) follow this photo.
    """
    internal_only(ctx)
    hub = _locked_hub(data.id)
    if data.version <= hub.state_version:
        return {"applied": False, "version": hub.state_version}
    was_open = not registry.is_suspended(hub)
    hub.state, hub.state_version = data.photo, data.version
    hub.save(update_fields=["state", "state_version", "updated_at"])
    if data.verifactu is not None or data.status is not None:
        _sync_verifactu(hub, data)
    if data.whatsapp is not None:
        _sync_whatsapp(hub, data)
    if data.members is not None:
        _apply_members(hub, data.members)
    record_event(ctx, events.HUB_STATE_APPLIED, {"id": str(hub.id), "version": data.version})
    # Applied as the platform (/internal): its own notice goes to the platform's channel. The live queries that
    # follow the photo (base/live.py) listen on the business's, which hears it after the COMMIT too.
    transaction.on_commit(partial(notify, Scope("host", hub.slug), [events.HUB_STATE_APPLIED]), robust=True)
    if was_open and registry.is_suspended(hub):
        transaction.on_commit(partial(_wake_open_apps, hub.slug), robust=True)
    return {"applied": True, "version": data.version}


def _wake_open_apps(slug: str) -> None:
    """The business of ``slug`` just stopped serving the app (suspended, cancelled), or some of its sessions ended:
    every open live stream and print socket of its host re-runs now («*», everything may have changed), hears the host
    gate and its session again (``base.operations.HubContextBuilder.refresh``) and ends if they no longer hold,
    instead of waiting for the hub's next write or the safety re-run (BILLING-F16 of the SaaS, step 4: the devices with
    the app open leave for the Hub's page)."""
    notify(Scope("host", slug), [ALL_EVENTS])


# ── The sessions of a SaaS account (/internal/sessions/revoke) ───────────────────────────────────────────────────


@operation("base.session.revoke", kind="command", permission=None, input=SessionRevokeIn, output=SessionRevokeOut)
def session_revoke(ctx: OperationContext, data: SessionRevokeIn) -> dict:
    """End the Hub's sessions of the SaaS account ``data.user_id``: those on the business ``data.hub_id`` or, without
    it, every one of them, the Hub admin's included (PLAN-SAAS §2.1, OIDC's back-channel logout).

    The SaaS sends it after the COMMIT that removed the person from a business, changed their role or handed the
    business over (with the business), or after a password change, «sign out everywhere» or deleting the account
    (without it). The sessions are found through ``SessionOwner``, never by decoding the table's. Idempotent: what
    already ended counts nothing; a business the registry does not know ends nothing and answers as one without
    sessions. The hosts whose sessions ended wake after the COMMIT (:func:`_end_sessions`).
    """
    internal_only(ctx)
    owners = SessionOwner.objects.filter(saas_user_id=str(data.user_id))
    if data.hub_id is not None:
        slug = Hub.objects.filter(pk=data.hub_id).values_list("slug", flat=True).first()
        if slug is None:
            return {"ended": 0}
        # A session that noted no host (from before the rule) is valid on every host, this one's too.
        owners = owners.filter(host__in=[slug, ""])
    return {"ended": _end_sessions(owners)}


def _end_sessions(owners) -> int:
    """Delete the sessions of ``owners`` (their notes go with them) and wake each hub's host they were on after the
    COMMIT, so a tab open with one of them loses it now (``bye``) instead of at its next write; how many ended."""
    hosts = set(owners.values_list("host", flat=True))
    _, deleted = Session.objects.filter(session_key__in=owners.values("session_id")).delete()
    for host in sorted(hosts - {PLATFORM_SESSION_HOST, ""}):
        transaction.on_commit(partial(_wake_open_apps, host), robust=True)
    return deleted.get(Session._meta.label, 0)


def _apply_members(hub: Hub, members: list) -> None:
    """Make the memberships of ``hub`` say what the photo's ``members`` say (HUBS-F26, F27 and F28 of the SaaS).

    A person whose role changed has it now and a person no longer listed loses their membership; either way their
    sessions on this business end (:func:`_end_sessions`), so the next thing they do runs with the permissions of
    the photo, not of their login. Nobody is created: a person the Hub has not seen yet takes their role when they
    first enter (:func:`open_session_from_saas`). Only the copies of SaaS accounts are the photo's (``saas:<id>``):
    a demo's owner is not.
    """
    wanted = {str(member.user_id): member.role for member in members}
    changed = []
    memberships = (
        Membership.objects.select_for_update(of=("self",))
        .select_related("user")
        .filter(host=hub.slug, user__username__startswith=SAAS_USERNAME_PREFIX)
    )
    for membership in memberships:
        saas_user_id = membership.user.username.removeprefix(SAAS_USERNAME_PREFIX)
        role = wanted.get(saas_user_id)
        if role is None:
            membership.delete()
        elif role != membership.role:
            membership.role = role
            membership.save(update_fields=["role"])
        else:
            continue
        changed.append(saas_user_id)
    if changed:
        # A session that noted no host (from before the rule) is valid on every host, this business's too.
        _end_sessions(SessionOwner.objects.filter(saas_user_id__in=changed, host__in=[hub.slug, ""]))


def _sync_verifactu(hub: Hub, data: HubStateIn) -> None:
    from base.tenancy.context import use_hub

    sync = get_operation("verifactu.config.sync")
    try:
        payload = sync.input.model_validate(
            {**(data.verifactu or {}), "version": data.version, "hub_status": data.status, "hub_id": hub.id}
        )
    except pydantic.ValidationError as invalid:
        raise InvalidPayload(
            f"The verifactu block is out of contract: {invalid}", code="internal.payload_invalid"
        ) from None
    # The hub's own operation, in its database: the same transaction while it shares control's (phase 1, S1–S4).
    with use_hub(hub):
        sync(system_context(Scope("host", hub.slug)), payload)


#: The app whose number's state travels in the photo (``whatsapp``) and whose doors erplora.com calls.
WHATSAPP_APP = "whatsapp_inbox"


def _sync_whatsapp(hub: Hub, data: HubStateIn) -> None:
    # base.relay imports this module: asked when the photo comes, not when this module loads.
    from base import relay
    from base.tenancy.context import use_hub

    scope = Scope("host", hub.slug)
    if WHATSAPP_APP not in relay.active_apps(scope):
        return
    sync = get_operation("whatsapp_inbox.channel.sync")
    try:
        payload = sync.input.model_validate({**data.whatsapp, "version": data.version})
    except pydantic.ValidationError as invalid:
        raise InvalidPayload(
            f"The whatsapp block is out of contract: {invalid}", code="internal.payload_invalid"
        ) from None
    with use_hub(hub):
        sync(system_context(scope), payload)


@operation("base.hub.cancel", kind="command", permission=None, input=HubCancelIn, output=HubOut)
def hub_cancel(ctx: OperationContext, data: HubCancelIn) -> dict:
    """The SaaS deleted the business: its host answers 410 from now on; its members and data stay, for a restore."""
    internal_only(ctx)
    hub = _locked_hub(data.id)
    _refuse_purged(hub)
    if hub.status != Hub.Status.CANCELLED:
        hub.status, hub.cancelled_at = Hub.Status.CANCELLED, timezone.now()
        hub.save(update_fields=["status", "cancelled_at", "updated_at"])
        record_event(ctx, events.HUB_CANCELLED, {"id": str(hub.id)})
        transaction.on_commit(partial(_wake_open_apps, hub.slug), robust=True)
    return hub_answer(hub)


@operation("base.hub.restore", kind="command", permission=None, input=HubRestoreIn, output=HubOut)
def hub_restore(ctx: OperationContext, data: HubRestoreIn) -> dict:
    """Bring a cancelled hub back (``ready``); a hub that never ended stays as it is; a purged one is ``hub_purged``."""
    internal_only(ctx)
    hub = _locked_hub(data.id)
    _refuse_purged(hub)
    if hub.status == Hub.Status.CANCELLED:
        hub.status, hub.cancelled_at = Hub.Status.READY, None
        hub.save(update_fields=["status", "cancelled_at", "updated_at"])
        record_event(ctx, events.HUB_RESTORED, {"id": str(hub.id)})
    return hub_answer(hub)


@operation("base.hub.seed_local", kind="command", permission=None, input=HubSeedLocalIn, output=HubSeedLocalOut)
def hub_seed_local(ctx: OperationContext, data: HubSeedLocalIn) -> dict:
    """Leave the local hubs ``data.slugs`` ready in the registry, with an id of their own (``seed_local_hubs``).

    Local development only (the command checks ``DEBUG``): they are no business of the SaaS's, so the SaaS hears
    nothing. Idempotent: a hub already ready stays as it is; one left cancelled is ready again.
    """
    internal_only(ctx)
    now = timezone.now()
    hubs = []
    for slug in data.slugs:
        hub, created = Hub.objects.select_for_update().get_or_create(
            slug=slug, defaults={"status": Hub.Status.READY, "ready_at": now}
        )
        outcome = "created" if created else "already_ready"
        if not created and hub.status != Hub.Status.READY:
            hub.status, hub.ready_at, hub.cancelled_at = Hub.Status.READY, now, None
            hub.save(update_fields=["status", "ready_at", "cancelled_at", "updated_at"])
            outcome = "ready_again"
        if outcome != "already_ready":
            record_event(ctx, events.HUB_REGISTERED, {"id": str(hub.id), "slug": slug, "created": created})
        hubs.append({"slug": slug, "outcome": outcome})
    return {"hubs": hubs}


# ── The demos (plan 2026-10-17, §1.6 and §1.7) ───────────────────────────────────────────────────────────────────

#: How long a client waits before asking for a demo again when they are all taken (``Retry-After`` of the 503).
DEMO_FULL_RETRY_AFTER_SECONDS = 60
#: How many addresses ``base.demo.create`` draws before it gives up (2³² of them: a second draw is already rare).
DEMO_SLUG_DRAWS = 5
#: Taken by ``base.demo.create`` before it counts the live demos, held until its transaction ends: two calls at once
#: create one after the other and never pass ``MAX_CONCURRENT_DEMOS``. A transaction lock, as PgBouncer in transaction
#: mode needs (a session one would outlive the transaction on a pooled connection, and is forbidden); no row stands
#: for "the demos" to ``SELECT … FOR UPDATE``, and locking the live ones would not stop a new one being inserted.
DEMO_CAP_LOCK = "SELECT pg_advisory_xact_lock(hashtext('erplora.base.demo.create'))"
#: The demo a session was opened in (:func:`open_demo_session`).
DEMO_SLUG_SESSION_KEY = "demo_slug"
#: The name the owner of every demo goes by in the shell.
DEMO_USER_NAME = "Demo"


def demo_username_for(slug: str) -> str:
    """The local user that owns the demo ``slug``: one per demo, purged with it."""
    return f"demo:{slug}"


def _demo_ttl() -> dt.timedelta:
    return dt.timedelta(minutes=settings.DEMO_TTL_MINUTES)


def _demo_out(hub: Hub, *, created: bool) -> dict:
    return {"id": hub.id, "slug": hub.slug, "expires_at": hub.expires_at, "created": created}


def _demo_status(hub: Hub) -> dict:
    return {"slug": hub.slug, "status": hub.status, "expires_at": hub.expires_at}


def _live_demo_of(session_key: str, now: dt.datetime) -> Hub | None:
    """The demo of this browser that is still on, or ``None``."""
    return Hub.objects.filter(
        is_demo=True, status=Hub.Status.READY, demo_session_key=session_key, expires_at__gt=now
    ).first()


def _demo_full() -> OperationError:
    return OperationError(
        gettext("Every demo is taken right now; try again in a minute."), code="base.demo_full", status=503
    )


def _platform_or_its_admin(ctx: OperationContext) -> None:
    """The platform, or one of its admins in the Hub admin (staff and superuser, ``platform_admin``); nobody else."""
    actor = ctx.actor
    if getattr(actor, "is_staff", False) and getattr(actor, "is_superuser", False):
        return
    internal_only(ctx)


def _locked_demo(slug: str) -> Hub:
    hub = Hub.objects.select_for_update().filter(slug=slug, is_demo=True).first()
    if hub is None:
        raise NotFound(gettext("No demo has this address."))
    return hub


@operation("base.demo.create", kind="command", permission=None, input=DemoCreateIn, output=DemoOut)
def demo_create(ctx: OperationContext, data: DemoCreateIn) -> dict:
    """This browser's demo: its live one (``created`` false, nothing spent), or a new, empty ``demo-<8 hex>``.

    A new one is ready at once (phase 1 has no database to clone, plan §1.5) and ends ``DEMO_TTL_MINUTES`` from now;
    ``vertical`` is only noted (the verticals' seed comes with the blueprints). Beyond ``MAX_CONCURRENT_DEMOS`` live
    demos it is ``base.demo_full`` (503). The count and the new row hold :data:`DEMO_CAP_LOCK`, so two calls at the
    same instant never pass the cap: the second counts once the first has committed. A demo of this browser that ran
    out and the reaper has not purged yet is marked ``expired`` first: it frees the browser for a new one (one live
    demo per browser, a unique constraint).
    """
    internal_only(ctx)
    now = timezone.now()
    live = _live_demo_of(data.session_key, now)
    if live is not None:
        return _demo_out(live, created=False)
    Hub.objects.filter(
        is_demo=True, status=Hub.Status.READY, demo_session_key=data.session_key, expires_at__lte=now
    ).update(status=Hub.Status.EXPIRED, updated_at=now)
    with connection.cursor() as cursor:
        cursor.execute(DEMO_CAP_LOCK)
    live_demos = Hub.objects.filter(is_demo=True, status=Hub.Status.READY, expires_at__gt=now).count()
    if live_demos >= settings.MAX_CONCURRENT_DEMOS:
        raise _demo_full()
    for _draw in range(DEMO_SLUG_DRAWS):
        slug = f"{DEMO_SLUG_PREFIX}{secrets.token_hex(4)}"
        try:
            with transaction.atomic():
                hub = Hub.objects.create(
                    slug=slug,
                    is_demo=True,
                    status=Hub.Status.READY,
                    ready_at=now,
                    expires_at=now + _demo_ttl(),
                    demo_session_key=data.session_key,
                    vertical=data.vertical or "",
                    language=data.language,
                )
        except IntegrityError:
            # Either another call of this browser made its demo first (then it is that one), or the address is taken.
            live = _live_demo_of(data.session_key, now)
            if live is not None:
                return _demo_out(live, created=False)
            continue
        record_event(ctx, events.DEMO_CREATED, {"id": str(hub.id), "slug": hub.slug, "vertical": hub.vertical})
        return _demo_out(hub, created=True)
    logger.error("base.demo.no_free_address after %d draws", DEMO_SLUG_DRAWS)
    raise OperationError(
        gettext("No demo could be made right now; try again."), code="base.demo_unavailable", status=503
    )


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


@operation("base.demo.code_create", kind="command", permission=None, input=DemoCodeIn, output=DemoCodeOut)
def demo_code_create(ctx: OperationContext, data: DemoCodeIn) -> dict:
    """A one-time code into the demo ``data.slug`` for the browser that owns it, valid ``DEMO_CODE_TTL_SECONDS``.

    Only its sha256 is kept. 404 when no demo has the slug, 410 ``base.hub_gone`` once it ended, 403
    ``base.demo_not_owner`` for another browser (the SaaS sends that browser back to its door).
    """
    internal_only(ctx)
    now = timezone.now()
    hub = Hub.objects.filter(slug=data.slug, is_demo=True).first()
    if hub is None:
        raise NotFound(gettext("No demo has this address."))
    if registry.is_gone(hub, now):
        raise OperationError(gettext("This demo has ended."), code="base.hub_gone", status=410)
    if not secrets.compare_digest(hub.demo_session_key.encode(), data.session_key.encode()):
        raise PermissionDenied(gettext("This demo is another browser's."), code="base.demo_not_owner")
    code = secrets.token_urlsafe(32)
    expires_at = now + dt.timedelta(seconds=auth.DEMO_CODE_TTL_SECONDS)
    DemoCode.objects.create(hub=hub, code_hash=_code_hash(code), language=data.language, expires_at=expires_at)
    record_event(ctx, events.DEMO_CODE_CREATED, {"slug": hub.slug})
    return {"code": code, "expires_at": expires_at}


def redeem_demo_code(slug: str, code: str | None, *, now: dt.datetime | None = None) -> DemoCode | None:
    """Spend ``code`` on the demo ``slug``: the code, once, within its minute and while the demo lasts; else ``None``.

    Not an ``@operation``: like :func:`open_session_from_saas`, it runs for ``/auth/callback`` before there is an
    actor. One conditional ``UPDATE`` of the code's own row (``used_at`` still empty) claims it, so two posts of the
    same code open one session at most: the second one finds it spent once the first commits.
    """
    if not code or not code.strip():
        return None
    now = now or timezone.now()
    found = DemoCode.objects.select_related("hub").filter(code_hash=_code_hash(code)).first()
    if found is None or found.hub.slug != slug or not found.hub.is_demo:
        return None
    if found.hub.status != Hub.Status.READY or registry.is_gone(found.hub, now):
        return None
    claimed = DemoCode.objects.filter(pk=found.pk, used_at__isnull=True, expires_at__gt=now).update(used_at=now)
    if not claimed:
        return None
    found.used_at = now
    return found


@transaction.atomic
def open_demo_session(request: HttpRequest, hub: Hub):
    """Log the visitor in as the owner of the demo ``hub`` (``demo:<slug>``, ``hub_owner``; a new session key).

    One local user per demo, named «Demo», with no password and never staff nor superuser (a copy raised by hand is
    lowered again, as a customer's); the reaper deletes it with the demo. ``InactiveUser`` if it was deactivated.
    """
    user_model = get_user_model()
    wanted = {"first_name": DEMO_USER_NAME, "is_staff": False, "is_superuser": False}
    user, _ = user_model.objects.get_or_create(
        username=demo_username_for(hub.slug), defaults={**wanted, "password": make_password(None)}
    )
    if not user.is_active:
        raise InactiveUser(user.username)
    changed = [field for field, value in wanted.items() if getattr(user, field) != value]
    if changed:
        for field in changed:
            setattr(user, field, wanted[field])
        user.save(update_fields=changed)
    Membership.objects.update_or_create(user=user, host=hub.slug, defaults={"role": Membership.Role.OWNER})
    login(request, user, backend=MODEL_BACKEND)
    request.session[DEMO_SLUG_SESSION_KEY] = hub.slug
    return user


@operation("base.demo.expire", kind="command", permission=None, input=DemoSlugIn, output=DemoStatusOut)
def demo_expire(ctx: OperationContext, data: DemoSlugIn) -> dict:
    """End the demo ``data.slug`` now: its host answers 410 at once and the reaper purges it on its next pass.

    For the platform (``manage.py demo_expire``) and its admins (the Hub admin's «Expire now»). A demo that already
    ended stays as it is.
    """
    _platform_or_its_admin(ctx)
    hub = _locked_demo(data.slug)
    if hub.status == Hub.Status.READY:
        now = timezone.now()
        hub.status = Hub.Status.EXPIRED
        hub.expires_at = min(hub.expires_at, now) if hub.expires_at is not None else now
        hub.save(update_fields=["status", "expires_at", "updated_at"])
        record_event(ctx, events.DEMO_EXPIRED, {"id": str(hub.id), "slug": hub.slug})
    return _demo_status(hub)


@operation("base.demo.purge", kind="command", permission=None, input=DemoSlugIn, output=DemoStatusOut)
def demo_purge(ctx: OperationContext, data: DemoSlugIn) -> dict:
    """Purge the demo ``data.slug``, which ended: its codes, its owner and its role go, and :func:`purge_demo_data`
    gets it; the row stays ``purged`` as a tombstone (410) for ``DEMO_TOMBSTONE_DAYS``.

    The reaper's, one transaction per demo. A demo still on is ``base.demo_live``; one already purged stays as it is.
    """
    internal_only(ctx)
    hub = _locked_demo(data.slug)
    if hub.status == Hub.Status.PURGED:
        return _demo_status(hub)
    if not registry.is_gone(hub):
        raise Conflict(gettext("This demo has not ended yet."), code="base.demo_live")
    DemoCode.objects.filter(hub=hub).delete()
    Membership.objects.filter(host=hub.slug).delete()
    get_user_model().objects.filter(username=demo_username_for(hub.slug)).delete()
    purge_demo_data(hub)
    hub.status, hub.purged_at = Hub.Status.PURGED, timezone.now()
    hub.save(update_fields=["status", "purged_at", "updated_at"])
    record_event(ctx, events.DEMO_PURGED, {"id": str(hub.id), "slug": hub.slug})
    return _demo_status(hub)


def purge_demo_data(hub: Hub) -> None:
    """Delete what the demo ``hub`` wrote in the apps: in phase 1, nothing, on purpose.

    Phase 1 has one database: the apps' tables are shared by every demo, by ``a``/``b`` and by the businesses, and
    their rows carry no ``hub_id`` (CLAUDE.md «Tenencia del Hub»), so nothing tells a demo's rows from anyone else's
    and deleting any would delete someone else's (the limitation Ioan accepted, plan 2026-10-17 §1.7). Phase 2 gives
    each demo its own database, cloned from ``hub_template_<vertical>``, and this is where it goes:
    ``DROP DATABASE demo_<hex> WITH (FORCE)``.
    """
    return None


def reap_demos(now: dt.datetime | None = None) -> int:
    """Purge every demo that ended by ``now`` (its time ran out, or it was expired by hand); return how many.

    The worker's (``base.worker``, every ``REAPER_INTERVAL_SECONDS``) and ``manage.py demo_expire``'s. Each demo is
    purged in its own transaction (``base.demo.purge``): one that fails is logged and the others are purged; it is
    tried again on the next pass. Then the tombstones older than ``DEMO_TOMBSTONE_DAYS`` are forgotten.
    """
    now = now or timezone.now()
    ended = Hub.objects.filter(
        Q(status=Hub.Status.READY, expires_at__lte=now) | Q(status=Hub.Status.EXPIRED), is_demo=True
    ).values_list("slug", flat=True)
    ctx = system_context(REGISTRY_SCOPE)
    purged = 0
    for slug in list(ended):
        try:
            demo_purge(ctx, DemoSlugIn(slug=slug))
        except Exception:
            logger.exception("base.demo.purge_failed demo=%s: it is tried again on the next pass.", slug)
            continue
        purged += 1
    reap_demo_tombstones(now)
    return purged


def reap_demo_tombstones(now: dt.datetime | None = None) -> int:
    """Forget the demos purged more than ``DEMO_TOMBSTONE_DAYS`` before ``now``: their hosts answer 404 from then on.

    Housekeeping of the reaper, as the scheduler's clock is (no operation, no event: the purge recorded its own).
    """
    now = now or timezone.now()
    cutoff = now - dt.timedelta(days=settings.DEMO_TOMBSTONE_DAYS)
    _, deleted = Hub.objects.filter(is_demo=True, status=Hub.Status.PURGED, purged_at__lt=cutoff).delete()
    return deleted.get(Hub._meta.label, 0)


# ── Data: blueprints, imports and reset (APP-BASE-2) ──


def _who(ctx: OperationContext) -> str:
    actor = ctx.actor
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.get_username())[:150]
    return str(actor)[:150]


@operation(
    "base.blueprint.inspect",
    kind="command",
    permission=ADMINISTER_HUB,
    input=BlueprintSourceIn,
    output=BlueprintSummaryOut,
    ai={"description": "Says what a template of the catalogue brings, app by app, before loading it; it writes nothing."},
)
def blueprint_inspect(ctx: OperationContext, data: BlueprintSourceIn) -> dict:
    """What a template or an uploaded file brings and what of it would load here (BASE-G104, BASE-G105).

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
    ai={
        "description": "Loads a template of the catalogue (a restaurant, a hair salon…) into this business: its menu "
        "or services, its tables and the rest of its apps' data, app by app; what is already there is left as it was. "
        "Returns the report of what went in. Never brings people, PINs or fiscal data.",
        "risk": "high",
    },
)
def blueprint_import(ctx: OperationContext, data: BlueprintImportIn) -> dict:
    """Load a template, a file or what a load left out (BASE-G103–G107) and keep its report and the rows it created."""
    with translation.override(ctx.language):
        retried = None
        if data.retry_of is not None:
            retried = ImportBatch.objects.select_for_update().filter(pk=data.retry_of).first()
            if retried is None:
                raise NotFound(gettext("This load is not there any more."), code="base.import_not_found")
            blocked = blueprint.retry_state(retried)
            if blocked:
                code, message = blueprint.RETRY_BLOCKED[blocked]
                raise Conflict(str(message), code=code)
            bundle, seed = blueprint.open_source(retried.template_key, "")
            apps = list(retried.apps)
        else:
            bundle, seed = blueprint.open_source(data.template, data.file_base64)
            apps = list(dict.fromkeys(data.apps)) if data.apps is not None else []
        applied = blueprint.apply(ctx, bundle, apps=set(apps) if apps else None)
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
        return blueprint.describe_load(load)


@operation(
    "base.import.undo",
    kind="command",
    permission=ADMINISTER_HUB,
    input=ImportUndoIn,
    output=ImportUndoOut,
    ai={
        "description": "Undoes one load of a template or a file: removes exactly the rows it brought; what was made "
        "afterwards stays.",
        "risk": "high",
    },
)
def import_undo(ctx: OperationContext, data: ImportUndoIn) -> dict:
    """Remove exactly the rows one load created (BASE-G108), once."""
    with translation.override(ctx.language):
        load = ImportBatch.objects.select_for_update().filter(pk=data.id).first()
        if load is None:
            raise NotFound(gettext("This load is not there any more."), code="base.import_not_found")
        if load.undone_at is not None:
            raise Conflict(gettext("This load was undone already."), code="base.import_undone")
        removed = blueprint.undo(ctx, load.created_rows)
        load.undone_at = timezone.now()
        load.save(update_fields=["undone_at"])
        record_event(ctx, events.IMPORT_UNDONE, {"id": str(load.pk)})
        return {"id": load.pk, "apps": removed["apps"]}


def same_name(typed: str, name: str) -> bool:
    """The name typed is the business's: spaces around and inside collapsed, case ignored, accents kept — what the
    confirmation dialog of the screen (``ConfirmDialog`` of ``@erplora/ui``) already asked."""

    def tidy(text: str) -> str:
        return " ".join(unicodedata.normalize("NFC", text).split()).casefold()

    return tidy(typed) == tidy(name)


def has_own_database(hub: Hub | None) -> bool:
    """The hub keeps its business in its own database (phase 2's S5): emptying it touches no other hub.

    In phase 1 every hub with ``db_name=""`` shares one database (plan 2026-10-22-fase-2-tenencia, decision 1), and
    an app's rows are everyone's: a reset would empty them for all.
    """
    return bool(hub is not None and hub.db_name)


@operation(
    "base.hub.reset",
    kind="command",
    permission=ADMINISTER_HUB,
    input=HubResetIn,
    output=HubResetOut,
    ai={
        "description": "With dry_run, says what each app of this business would lose if emptied and what name must be "
        "typed to confirm. Without it, empties the apps chosen for good, given the business's name typed exactly.",
        "risk": "high",
    },
)
def hub_reset(ctx: OperationContext, data: HubResetIn) -> dict:
    """The plan of what each app would lose, or empty the apps chosen with the business's name typed (BASE-G109)."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        confirm_with = hub.name.strip() if hub and hub.name.strip() else ctx.scope.key
        sections = blueprint.reset_plan(ctx)
        answer = {
            "dry_run": data.dry_run,
            "confirm_with": confirm_with,
            "available": has_own_database(hub),
            "sections": sections,
            "apps": [],
        }
        if data.dry_run:
            return answer
        if not answer["available"]:
            raise Conflict(
                gettext(
                    "Resetting the business is not available yet. Undo a load instead, or remove what you want "
                    "from each app."
                ),
                code="base.reset_shared_database",
            )
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
        removed = blueprint.reset(ctx, chosen)
        record_event(ctx, events.HUB_DATA_RESET, {"apps": chosen})
        return {**answer, "sections": blueprint.reset_plan(ctx), "apps": removed["apps"]}


# ── System: the failed events (APP-BASE-7) ─────────────────────────────────────────────────────────────────────────
# The old hub's ``/api/hub/events/:id/retry``, ``retry-all`` and ``:id/discard`` (HUB-F55…F57), for who runs the
# business. A failed event is a delivery the relay gave up on (``dead``): resending puts it back in the queue for the
# app that had failed only; discarding closes it for good and keeps the row. One hub never touches another's.


@operation(
    "base.failed_event.retry",
    kind="command",
    permission=ADMINISTER_HUB,
    input=FailedEventIn,
    output=FailedEventOutId,
    ai={
        "description": "Resends one failed event of this hub (by its id, from the list of failed events) once its "
        "cause is fixed: it goes back to the queue with its attempts at zero, for the app that could not take it "
        "only. Refused when that app is no longer on in this business.",
        "risk": "normal",
    },
)
def failed_event_retry(ctx: OperationContext, data: FailedEventIn) -> dict:
    """HUB-F55: ``pending`` again, due now, attempts at zero; the relay takes it on its next tick."""
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
    ai={
        "description": "Resends every failed event of this hub that can be resent (also those beyond the first page "
        "of the list), once the cause of a passing failure is fixed. Those for an app that is no longer on stay. "
        "Says how many went back to the queue.",
        "risk": "normal",
    },
)
def failed_event_retry_all(ctx: OperationContext, data: FailedEventRetryAllIn) -> dict:
    """HUB-F56: every ``dead`` delivery of the hub whose app is on; another worker's rows wait (``SKIP LOCKED``)."""
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
    permission=ADMINISTER_HUB,
    input=FailedEventDiscardIn,
    output=FailedEventOutId,
    ai={
        "description": "Discards one failed event of this hub for good (by its id), with an optional reason: it is "
        "never delivered again and is kept with who discarded it, when and why. Only when it must not be delivered "
        "(a duplicate, already done by hand): discarding a sale's event for Invoicing leaves that sale without its "
        "invoice.",
        "risk": "high",
    },
)
def failed_event_discard(ctx: OperationContext, data: FailedEventDiscardIn) -> dict:
    """HUB-F57: closed as ``discarded`` with who, when and why; the row and its last error stay for the audit."""
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


# ── The way in: devices, PIN, badge, the business's dial and the person's profile (APP-BASE-3) ───────────────────

def trust_device(request: HttpRequest, user) -> TrustedDevice:
    """This browser's device of the hub, made a trusted one by an entry with the account (BASE-G52, G53).

    The device of the cookie ``hub_device`` if the hub knows it (its mode and name are kept), else a new one with a
    new token. Its last person in and entry are now's, and a notice of sessions it lost (``ended_reason``) is read.
    """
    now = timezone.now()
    device = queries.device_of(request, for_update=True)
    if device is None:
        token = access.new_device_token()
        device = TrustedDevice.objects.create(
            token_digest=access.token_digest(token),
            agent=access.device_agent(request.META.get("HTTP_USER_AGENT", ""))[:80],
            last_username=user.get_username(),
            last_user_label=_label_of(user),
            last_entry_at=now,
        )
    else:
        token = request.COOKIES[access.DEVICE_COOKIE]
        _entered(device, user, now)
    setattr(request, access.DEVICE_TOKEN_ATTR, token)
    return device


def _entered(device: TrustedDevice, user, now: dt.datetime) -> None:
    device.last_username, device.last_user_label, device.last_entry_at = user.get_username(), _label_of(user), now
    device.ended_reason, device.ended_at = "", None
    device.save(update_fields=["last_username", "last_user_label", "last_entry_at", "ended_reason", "ended_at"])


def _label_of(user) -> str:
    """How a person is named in this hub: its profile's name, else its account's (``base.queries.person_label``)."""
    return queries.person_label(user)[:150]


def _end_other_devices(slug: str, device: TrustedDevice) -> None:
    """Keep within the devices the business's plan covers (``plan.max_devices`` of the SaaS's photo; 0 or none, no
    cap; BASE-G57): an entry on ``device`` ends the live sessions on this host of every other device past the
    ``max_devices - 1`` most recently entered, and marks those devices so their next way in says why. A session with
    no device (from before the rule) never counts as a kept one. Their tabs wake after the COMMIT and leave."""
    hub = Hub.objects.filter(slug=slug).first()
    plan = (hub.state or {}).get("plan") if hub is not None and isinstance(hub.state, dict) else None
    cap = plan.get("max_devices") if isinstance(plan, dict) else None
    if not isinstance(cap, int) or cap < 1:
        return
    now = timezone.now()
    others = SessionOwner.objects.filter(host=slug, session__expire_date__gt=now).exclude(device_id=device.pk)
    latest = (
        others.exclude(device_id=None).values("device_id").annotate(opened=Max("created_at")).order_by("-opened")
    )
    kept = [row["device_id"] for row in latest[: cap - 1]]
    ending = others.exclude(device_id__in=kept) if kept else others
    devices = {pk for pk in ending.values_list("device_id", flat=True) if pk is not None}
    _end_sessions(ending)
    TrustedDevice.objects.filter(pk__in=devices).update(
        ended_reason=TrustedDevice.EndedReason.DEVICE_LIMIT, ended_at=now
    )


@transaction.atomic
def open_session_on_device(request: HttpRequest, user, device: TrustedDevice, credential: str) -> None:
    """Log ``user`` in on the hub's ``device`` with its PIN or its badge (BASE-G55, G56, G60), for a shift (or what the
    device and the business allow). Over someone else's session («Switch user») ``login`` ends that one only now, once
    the new one is being opened in this transaction: a refused PIN never reaches here and changes nothing."""
    device = TrustedDevice.objects.select_for_update().get(pk=device.pk)
    _entered(device, user, timezone.now())
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
    """Choose or change one's own PIN (BASE-G54, G126): the business's length, digits only, not guessable, with the
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
    with transaction.atomic():
        row = AccessSettings.objects.select_for_update().first()
        if row is None:
            try:
                with transaction.atomic():
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
    permission=ADMINISTER_HUB,
    input=DeviceModeIn,
    output=DeviceCurrentOut,
    ai={
        "description": "Makes the device the person is using shared (a till several people use: PIN, a shift) or "
        "personal (one person's: no PIN, 30 days). Only on the device itself.",
        "risk": "normal",
    },
)
def device_mode_set(ctx: OperationContext, data: DeviceModeIn) -> dict:
    """«This device» (BASE-G72): the mode of the browser that asks, never another's. The sessions opened from now on
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
    permission=ADMINISTER_HUB,
    input=DeviceRenameIn,
    output=DeviceByIdIn,
    ai={
        "description": "Names a device of the hub after its place («Bar», «Kitchen», «Office laptop»).",
        "risk": "normal",
    },
)
def device_rename(ctx: OperationContext, data: DeviceRenameIn) -> dict:
    """«Name it» (BASE-G64): the one thing of a device the business decides."""
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
    ai={
        "description": "Removes a lost device from the hub: its session ends at once and the PIN stops working on "
        "it until someone signs in with an account on it again. Removing the one in hand signs the person out.",
        "risk": "high",
    },
)
def device_remove(ctx: OperationContext, data: DeviceByIdIn) -> dict:
    """«Remove this device» (BASE-G65): the device is cut off, not its people; whoever has an account can enter on it
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
    ai={
        "description": "Removes at once the devices of the hub nobody used in 30 days, never the one in hand.",
        "risk": "high",
    },
)
def device_prune(ctx: OperationContext, data: DevicePruneIn) -> dict:
    """«Remove the unused» (BASE-G66): those nobody entered on in 30 days, as BASE-G65 removes one."""
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
    permission=ADMINISTER_HUB,
    input=AccessSettingsUpdateIn,
    output=AccessSettingsOut,
    ai={
        "description": "Changes how the business asks who is at the till: show the PIN pad or not, ask again after "
        "1, 5, 10, 15 or 30 minutes without use or once per shift, and PINs of 4 or 6 digits.",
        "risk": "high",
    },
)
def access_settings_update(ctx: OperationContext, data: AccessSettingsUpdateIn) -> dict:
    """The «PIN pad» card (BASE-G62, G151): only the fields sent change. The PINs of the other length keep working
    until their owners change them; the sessions already open keep their end."""
    changes = data.dict(exclude_none=True)
    if not changes:
        raise InvalidPayload(gettext("Nothing to change."), code="base.nothing_to_change")
    row = AccessSettings.objects.select_for_update().first()
    if row is None:
        try:
            with transaction.atomic():
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
    permission=VIEW_HOME,
    input=ProfileUpdateIn,
    output=ProfileOut,
    ai={
        "description": "Saves the person's own name, last name and contact email in this hub (not their sign-in "
        "email).",
        "risk": "normal",
    },
)
def profile_update(ctx: OperationContext, data: ProfileUpdateIn) -> dict:
    """«Save my data» (BASE-G125): how the person appears in this hub. The contact email gives and takes no access."""
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
    permission=VIEW_HOME,
    input=PreferencesIn,
    output=PreferencesOut,
    ai={
        "description": "Sets the person's own language (Spanish, English or the business's) and appearance.",
        "risk": "normal",
    },
)
def preferences_set(ctx: OperationContext, data: PreferencesIn) -> dict:
    """«Preferences» (BASE-G125): saved as chosen and applied at once; empty = the business's. They follow the person
    on any device of the hub (the language from their next entry on another one)."""
    user = queries.signed_in(ctx)
    profile = _profile(user)
    profile.language, profile.theme_mode, profile.palette = data.language, data.theme_mode, data.palette
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    language = queries.language_of(user, ctx.scope.key) or settings.LANGUAGE_CODE
    return {"language": language, "theme_mode": profile.theme_mode, "palette": profile.palette}


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
    """«Change photo» (BASE-G125): a JPG, PNG or WebP of 2 MB at most, kept in the hub's files under ``avatars/`` by
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
    permission=VIEW_HOME,
    input=AvatarRemoveIn,
    output=AvatarOut,
    ai={"description": "Removes the photo of the person's own profile.", "risk": "normal"},
)
def avatar_remove(ctx: OperationContext, data: AvatarRemoveIn) -> dict:
    """«Remove» (BASE-G125): the profile forgets its photo (the file, named by its content, may be someone else's)."""
    user = queries.signed_in(ctx)
    profile = _profile(user)
    profile.avatar = ""
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    return {"avatar_url": ""}


# ── People and permissions: a person's way in (APP-BASE-5) ─────────────────────────────────────────────────────────

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
    permission=ADMINISTER_HUB,
    input=PersonIn,
    output=PersonDetailOut,
    ai={
        "description": "Takes a person's PIN away (a forgotten or shared one): they stop entering with it at the "
        "shared tills and keep entering with their erplora.com account. The owner's, only the owner.",
        "risk": "high",
    },
)
def person_pin_remove(ctx: OperationContext, data: PersonIn) -> dict:
    """«Remove the PIN» (BASE-G139): the PIN goes at once, the badge and the account stay."""
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
    """«Badge» (BASE-G140): the card, kept as its digest; never one's own, never one somebody else carries. Every try
    counts against who gives it (``people.BADGE_CHANGE_LIMIT``, gh:hub#2560): «already taken» tells something."""
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
        with transaction.atomic():
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
    permission=ADMINISTER_HUB,
    input=PersonIn,
    output=PersonDetailOut,
    ai={
        "description": "Takes a person's badge away (a lost card): it stops opening the till; their PIN and account stay.",
        "risk": "normal",
    },
)
def person_badge_remove(ctx: OperationContext, data: PersonIn) -> dict:
    """«Remove the badge» (BASE-G140): the card stops opening anything; a lost one never leaves anybody out."""
    _changeable_person(ctx, data.person, badge=False)
    credential = Credential.objects.select_for_update().filter(username=data.person).exclude(badge_digest="").first()
    if credential is None:
        raise Conflict(gettext("This person has no badge to remove."), code="base.person_no_badge")
    credential.badge_digest, credential.badge_set_at = "", None
    credential.save(update_fields=["badge_digest", "badge_set_at"])
    record_event(ctx, events.PERSON_BADGE_REMOVED, {"person": data.person})
    return _person_answer(ctx, data.person)


# ── People and permissions: the business's API keys (APP-BASE-5) ───────────────────────────────────────────────────


def _api_keys_available(ctx: OperationContext) -> None:
    """A key lives in its hub's own database; while the business shares phase 1's with others, a key of it would open
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
        raise InvalidPayload(
            gettext("Choose at least one app and what the key may do on it."),
            code="base.api_key_scopes_required",
            fields={"scopes": "required"},
        )
    for app, kinds in scopes.items():
        found = offered.get(app)
        if found is None or any(not found[kind] for kind in kinds):
            raise InvalidPayload(
                gettext("That app does not publish what the key would do on it."),
                code="base.api_key_scope_unknown",
                fields={"scopes": app},
            )
    return scopes


def _new_token_for(key: ApiKey) -> str:
    token = api_keys.new_token()
    key.token_digest, key.prefix = api_keys.digest(token), token[: api_keys.PREFIX_LENGTH]
    return token


@operation(
    "base.api_key.create",
    kind="command",
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
    """«New API key» (BASE-G146): its token once; the hub keeps its digest and its first characters."""
    _api_keys_available(ctx)
    name = " ".join(data.name.split())
    if not name:
        raise InvalidPayload(gettext("Give the key a name."), code="base.api_key_name_required", fields={"name": "required"})
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
    """«Rotate» (BASE-G147): a new token, shown once; the old one stops at once (its digest is gone)."""
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
    permission=ADMINISTER_HUB,
    input=ApiKeyIdIn,
    output=ApiKeyRevokeOut,
    ai={
        "description": "Revokes an API key: any system using it loses access at once, for good. The key stays listed "
        "as revoked.",
        "risk": "high",
    },
)
def api_key_revoke(ctx: OperationContext, data: ApiKeyIdIn) -> dict:
    """«Revoke» (BASE-G148): at once and for good; the key is kept, for the record."""
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

    ``None`` (the session's door goes on) on a business that shares phase 1's database, or for a token nobody issued
    here (counted against the address); 429 once the address tried too many, or the key passed its pace; 403 when the
    key may not do this on this app."""
    hub = getattr(request, "hub", None)
    if not has_own_database(hub):
        return None
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


# ── People and permissions: a manager's approval (APP-BASE-5) ──────────────────────────────────────────────────────
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
    pad's brakes (APP-BASE-3): a wrong one also counts against the address; a right one starts the count again."""
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
    """«An approval is needed» (BASE-G136): somebody of the business who may do the action approves it with their PIN
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
    approval.save(update_fields=["used_at"])
    record_event(ctx, events.APPROVAL_USED, {"id": str(approval.pk), "operation": approval.operation})
    return {"spent": True, "id": str(approval.pk), "approver": approval.approved_by_name}



# ── People and permissions: the API's documentation (APP-BASE-5) ───────────────────────────────────────────────────
from base.models import ApiSettings  # noqa: E402
from base.schemas import ApiDocSettingsIn, ApiDocSettingsOut, ApiDocSettingsUpdateIn  # noqa: E402


@operation(
    "base.api_doc.settings_update",
    kind="command",
    permission=ADMINISTER_HUB,
    input=ApiDocSettingsUpdateIn,
    output=ApiDocSettingsOut,
    ai={
        "description": "Shows or hides the documentation of this business's API (for whoever connects another "
        "system); it comes hidden.",
        "risk": "low",
    },
)
def api_doc_settings_update(ctx: OperationContext, data: ApiDocSettingsUpdateIn) -> dict:
    """«Show the API documentation» (BASE-G100): saved at once."""
    row = ApiSettings.objects.select_for_update().first()
    if row is None:
        try:
            with transaction.atomic():
                row = ApiSettings.objects.create()
        except IntegrityError:
            row = ApiSettings.objects.select_for_update().get()
    row.docs_enabled = data.docs_enabled
    row.updated_by = _actor_label(ctx)
    row.save()
    record_event(ctx, events.API_DOC_SETTINGS_CHANGED, {"docs_enabled": data.docs_enabled})
    return queries.api_doc_settings(ctx, ApiDocSettingsIn())

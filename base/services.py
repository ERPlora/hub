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

import datetime as dt
import hashlib
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
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.http import HttpRequest
from django.utils import timezone, translation
from django.utils.translation import gettext
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.live_registry import ALL_EVENTS
from live.models import OutboxEvent
from live.operations import get as get_operation
from live.operations import operation
from live.outbox import notify, record_event
from live.slugs import DEMO_SLUG_PREFIX, validate_hub_slug

from base import auth, blueprint, events, registry, signing, system
from base.registry import REGISTRY_SCOPE, hub_answer, internal_only
from base.auth import PLATFORM_ADMIN, PLATFORM_SUPPORT, RedeemedUser
from base.middleware import PLATFORM_SESSION_HOST, session_host
from base.models import DemoCode, EventDelivery, Hub, ImportBatch, Membership, SessionOwner, TaskSchedule
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


def _log_in(request: HttpRequest, user, redeemed: RedeemedUser) -> None:
    login(request, user, backend=MODEL_BACKEND)
    request.session[SAAS_USER_ID_SESSION_KEY] = redeemed.user_id
    _note_the_owner(request, redeemed.user_id)


def _note_the_owner(request: HttpRequest, saas_user_id: str) -> None:
    """Note whose and where the new session is (``SessionOwner``), so ``base.session.revoke`` finds it by index.

    ``login`` gives the session a new key and saves it, unless it flushed another user's session first: then it has
    no key until it is saved, which happens here, in the login's transaction.
    """
    if request.session.session_key is None:
        request.session.save()
    SessionOwner.objects.update_or_create(
        session_id=request.session.session_key,
        defaults={"saas_user_id": saas_user_id, "host": session_host(request) or ""},
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
    _log_in(request, user, redeemed)
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
    _log_in(request, user, redeemed)
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
#: Who runs the hub: loads, undoes and resets (the old hub's ``hub.administer``).
ADMINISTER_HUB = "base.administer_hub"


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

#: Who runs the business: the permission of System's failed events (``base.queries.ADMINISTER_HUB``).
ADMINISTER_HUB = "base.administer_hub"


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


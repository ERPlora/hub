"""Writes of base: opening the Hub's session for the person the SaaS vouched for, the clock of the apps' scheduled
tasks (``base.scheduler``) and the registry of hubs (``base.Hub``, the operations ``base.hub.*``).

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
from collections.abc import Callable, Iterable
from functools import partial
from uuid import UUID

import pydantic
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext, Scope, system_context
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.operations import get as get_operation
from live.operations import operation
from live.outbox import record_event
from live.slugs import DEMO_SLUG_PREFIX, validate_hub_slug

from base import auth, events, registry, signing
from base.registry import REGISTRY_SCOPE, hub_answer, internal_only
from base.auth import PLATFORM_ADMIN, PLATFORM_SUPPORT, RedeemedUser
from base.models import DemoCode, Hub, Membership, TaskSchedule
from base.schemas import (
    DemoCodeIn,
    DemoCodeOut,
    DemoCreateIn,
    DemoOut,
    DemoSlugIn,
    DemoStatusOut,
    HubCancelIn,
    HubOut,
    HubRegisterOut,
    HubRegistryIn,
    HubRestoreIn,
    HubSeedLocalIn,
    HubSeedLocalOut,
    HubStateIn,
    HubStateOut,
)

logger = logging.getLogger(__name__)

MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"
#: The SaaS account the session belongs to, for /internal/sessions/revoke (phase 2).
SAAS_USER_ID_SESSION_KEY = "saas_user_id"
#: Read-only group of ``platform_support`` in the Hub admin (the SaaS's ``support``). Phase 2
#: replaces it with the ``StaffUser`` mark (PLAN §17).
SUPPORT_GROUP = "support"


class InactiveUser(Exception):
    """The Hub's copy of the user was deactivated (in the admin): no session, whatever the SaaS says."""


def username_for(saas_user_id: str) -> str:
    """The customer copy of a SaaS account (hub door)."""
    return f"saas:{saas_user_id}"


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
    ``verifactu.config.sync`` on the hub's slug, in this same transaction (a block out of contract keeps
    nothing). The rights it carries (plan, modules, members) are only kept until phase 2 applies them.
    """
    internal_only(ctx)
    hub = _locked_hub(data.id)
    if data.version <= hub.state_version:
        return {"applied": False, "version": hub.state_version}
    hub.state, hub.state_version = data.photo, data.version
    hub.save(update_fields=["state", "state_version", "updated_at"])
    if data.verifactu is not None or data.status is not None:
        _sync_verifactu(hub, data)
    record_event(ctx, events.HUB_STATE_APPLIED, {"id": str(hub.id), "version": data.version})
    return {"applied": True, "version": data.version}


def _sync_verifactu(hub: Hub, data: HubStateIn) -> None:
    sync = get_operation("verifactu.config.sync")
    try:
        payload = sync.input.model_validate(
            {**(data.verifactu or {}), "version": data.version, "hub_status": data.status, "hub_id": hub.id}
        )
    except pydantic.ValidationError as invalid:
        raise InvalidPayload(
            f"The verifactu block is out of contract: {invalid}", code="internal.payload_invalid"
        ) from None
    sync(system_context(Scope("host", hub.slug)), payload)


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

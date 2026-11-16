"""The demos, rows of the registry of hubs too.

``base.demo.create`` gives a browser of the
SaaS its live demo or a new empty ``demo-<8 hex>`` for ``DEMO_TTL_MINUTES``; ``base.demo.code_create`` a one-time
code into it for that browser only, which the demo's ``/auth/callback`` redeems here (:func:`redeem_demo_code`) and
turns into the owner's session (:func:`open_demo_session`); the worker's reaper (:func:`reap_demos`) purges the ones
that ended, each with ``base.demo.purge``, and forgets them after ``DEMO_TOMBSTONE_DAYS``.
"""

import datetime as dt
import hashlib
import logging
import secrets
from uuid import UUID, uuid7

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import make_password
from django.core.files.storage import storages
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, NotFound, OperationError, PermissionDenied
from live.operations import INTERNAL, atomic, operation
from live.outbox import record_event
from live.slugs import DEMO_SLUG_PREFIX

from base import auth, events, files, registry
from base.models import DemoCode, Hub, Membership
from base.registry import internal_only
from base.schemas import DemoCodeIn, DemoCodeOut, DemoCreateIn, DemoOut, DemoSlugIn, DemoStatusOut
from base.services.provisioning import _control_transaction
from base.services.sessions import InactiveUser, MODEL_BACKEND, ensure_hub_user
from base.tenancy import names as database_names
from base.tenancy.connections import control_name
from control.models import HubDue

logger = logging.getLogger(__name__)


# ── The demos ────────────────────────────────────────────────────────────────────────────────────────────────────

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


#: The statuses of a demo that is not over yet: the reaper ends it once its hour is up, an admin may end it by hand.
OPEN_DEMO_STATUSES = frozenset({*registry.PREPARING_STATUSES, Hub.Status.READY})
#: The statuses of a browser's live demo (one per browser, under the cap): being made or ready. One whose preparation
#: failed is not: the browser gets another and that one ends.
LIVE_DEMO_STATUSES = OPEN_DEMO_STATUSES - {Hub.Status.FAILED}


def _demo_out(hub: Hub, *, created: bool) -> dict:
    return {"id": hub.id, "slug": hub.slug, "status": hub.status, "expires_at": hub.expires_at, "created": created}


def _demo_status(hub: Hub) -> dict:
    return {"slug": hub.slug, "status": hub.status, "expires_at": hub.expires_at}


def _live_demo_of(session_key: str, now: dt.datetime) -> Hub | None:
    """The demo of this browser that is still on (being made or ready), or ``None``."""
    return Hub.objects.filter(
        is_demo=True, status__in=LIVE_DEMO_STATUSES, demo_session_key=session_key, expires_at__gt=now
    ).first()


def _demo_full() -> OperationError:
    return OperationError(
        gettext("Every demo is taken right now; try again in a minute."), code="base.demo_full", status=503
    )


def _platform_or_its_admin(ctx: OperationContext) -> None:
    """The platform, or one of its admins in the Hub admin (staff and superuser, ``platform_admin``) on the platform's
    own scope (``REGISTRY_SCOPE``); nobody else: on a business's host, staff is no more than anyone there (review of
    hub#490)."""
    from base.tenancy.context import PLATFORM_SCOPE_KIND

    actor = ctx.actor
    on_the_platform = ctx.scope.kind == PLATFORM_SCOPE_KIND
    if on_the_platform and getattr(actor, "is_staff", False) and getattr(actor, "is_superuser", False):
        return
    internal_only(ctx)


def _locked_demo(slug: str) -> Hub:
    hub = Hub.objects.select_for_update().filter(slug=slug, is_demo=True).first()
    if hub is None:
        raise NotFound(gettext("No demo has this address."))
    return hub


# Not an assistant tool: the SaaS's door to the demo (/internal), no person.
@operation("base.demo.create", kind="command", permission=None, input=DemoCreateIn, output=DemoOut, ai=INTERNAL)
def demo_create(ctx: OperationContext, data: DemoCreateIn) -> dict:
    """This browser's demo: its live one (``created`` false, nothing spent), or a new, empty ``demo-<8 hex>``.

    A new one is ``requested`` with a database of its own to make (``<control>_demo_<hex>``, cloned from its
    vertical's template by the worker): the SaaS waits for ``ready`` on
    ``GET /internal/hubs/{id}`` before it asks for a code. It ends ``DEMO_TTL_MINUTES`` from now. Beyond
    ``MAX_CONCURRENT_DEMOS`` live demos (being made or ready) it is ``base.demo_full`` (503). The count and the new row
    hold :data:`DEMO_CAP_LOCK`, so two calls at the same instant never pass the cap and one browser never gets two: the
    second looks again once the first has committed. A demo of this browser that ran out and the reaper has not purged
    yet, or whose preparation failed, is marked ``expired`` and due first (the reaper drops it): it frees the browser for
    a new one.
    """
    internal_only(ctx)
    now = timezone.now()
    live = _live_demo_of(data.session_key, now)
    if live is not None:
        return _demo_out(live, created=False)
    ended = Hub.objects.filter(
        Q(expires_at__lte=now) | Q(status=Hub.Status.FAILED),
        is_demo=True,
        status__in=OPEN_DEMO_STATUSES,
        demo_session_key=data.session_key,
    )
    for hub in ended:
        HubDue.mark_due(hub, now)
    ended.update(status=Hub.Status.EXPIRED, updated_at=now)
    with connection.cursor() as cursor:
        cursor.execute(DEMO_CAP_LOCK)
    # Under the lock: a call of this browser that made its demo meanwhile has committed it.
    live = _live_demo_of(data.session_key, now)
    if live is not None:
        return _demo_out(live, created=False)
    live_demos = Hub.objects.filter(is_demo=True, status__in=LIVE_DEMO_STATUSES, expires_at__gt=now).count()
    if live_demos >= settings.MAX_CONCURRENT_DEMOS:
        raise _demo_full()
    for _draw in range(DEMO_SLUG_DRAWS):
        slug = f"{DEMO_SLUG_PREFIX}{secrets.token_hex(4)}"
        try:
            with atomic():
                demo_id = uuid7()
                hub = Hub.objects.create(
                    id=demo_id,
                    slug=slug,
                    is_demo=True,
                    status=Hub.Status.REQUESTED,
                    db_name=database_names.demo_db_name(control_name(), demo_id),
                    expires_at=now + _demo_ttl(),
                    demo_session_key=data.session_key,
                    vertical=data.vertical or "",
                    language=data.language,
                )
                HubDue.mark_due(hub, now)
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


# Not an assistant tool: the SaaS's door to the demo (/internal), no person.
@operation("base.demo.code_create", kind="command", permission=None, input=DemoCodeIn, output=DemoCodeOut, ai=INTERNAL)
def demo_code_create(ctx: OperationContext, data: DemoCodeIn) -> dict:
    """A one-time code into the demo ``data.slug`` for the browser that owns it, valid ``DEMO_CODE_TTL_SECONDS``.

    Only its sha256 is kept. 404 when no demo has the slug, 410 ``base.hub_gone`` once it ended, 403
    ``base.demo_not_owner`` for another browser (the SaaS sends that browser back to its door), 503
    ``base.hub_preparing`` while its database is being made (the SaaS waits for ``ready`` first).
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
    if registry.is_preparing(hub):
        raise OperationError(
            gettext("This demo is still being prepared; try again in a few seconds."),
            code=registry.HUB_PREPARING,
            status=503,
        )
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


@transaction.atomic  # control's: the demo's local user, its Membership and the session
@atomic  # the hub's: the owner's person (base.HubUser)
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
    ensure_hub_user(user)
    login(request, user, backend=MODEL_BACKEND)
    request.session[DEMO_SLUG_SESSION_KEY] = hub.slug
    return user


# Not an assistant tool: the SaaS's door to the demo (/internal), no person.
@operation("base.demo.expire", kind="command", permission=None, input=DemoSlugIn, output=DemoStatusOut, ai=INTERNAL)
def demo_expire(ctx: OperationContext, data: DemoSlugIn) -> dict:
    """End the demo ``data.slug`` now: its host answers 410 at once and the reaper purges it on its next pass.

    For the platform (``manage.py demo_expire``) and its admins (the Hub admin's «Expire now»), being made or ready. A
    demo that already ended stays as it is.
    """
    _platform_or_its_admin(ctx)
    hub = _locked_demo(data.slug)
    if hub.status in OPEN_DEMO_STATUSES:
        now = timezone.now()
        hub.status = Hub.Status.EXPIRED
        hub.expires_at = min(hub.expires_at, now) if hub.expires_at is not None else now
        hub.save(update_fields=["status", "expires_at", "updated_at"])
        HubDue.mark_due(hub, now)
        record_event(ctx, events.DEMO_EXPIRED, {"id": str(hub.id), "slug": hub.slug})
    return _demo_status(hub)


# Not an assistant tool: the SaaS's door to the demo (/internal), no person.
@operation("base.demo.purge", kind="command", permission=None, input=DemoSlugIn, output=DemoStatusOut, ai=INTERNAL)
def demo_purge(ctx: OperationContext, data: DemoSlugIn) -> dict:
    """Purge the demo ``data.slug``, which ended: its codes, its owner and its role go; the row stays ``purged`` as a
    tombstone (410) for ``DEMO_TOMBSTONE_DAYS``. Rows only: its database and its files went before, outside any
    transaction of control (:func:`purge_demo_data`, from ``base.tenancy.provision.drop``).

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
    hub.status, hub.purged_at = Hub.Status.PURGED, timezone.now()
    hub.save(update_fields=["status", "purged_at", "updated_at"])
    record_event(ctx, events.DEMO_PURGED, {"id": str(hub.id), "slug": hub.slug})
    return _demo_status(hub)


def purge_demo_data(hub: Hub) -> None:
    """Delete what the demo ``hub`` wrote: its whole database, ``DROP DATABASE … WITH (FORCE)`` on its cluster
    (``base.tenancy.ops``), outside any transaction, and only its own ``<control>_demo_<hex>`` (a row that names another
    database, or no demo, is refused and loses nothing); it is never emptied nor reused. Then its files, its prefix in
    the store and no other (:func:`base.files.delete_hub_files`).

    A demo made before demos got their own database (``db_name`` empty) kept its rows in a database every hub shared,
    where nothing tells them from anyone else's: only its files are deleted. A database already
    gone is no failure; one the server refuses to drop, or a store that does not delete, fails the purge, which the
    reaper tries again.
    """
    from base.tenancy import ops

    own = database_names.demo_db_name(control_name(), hub.id)
    if not hub.is_demo or hub.db_name not in ("", own):
        raise database_names.InvalidDatabaseName(
            f"{hub.db_name!r} is not the demo {hub.slug}'s own database ({own!r}): nothing is dropped."
        )
    if hub.db_name:
        ops.drop_database(hub.db_name, cluster=hub.cluster)
    files.delete_hub_files(storages["hub_files"], hub.id)


def reap_demos(now: dt.datetime | None = None) -> int:
    """Purge every demo that ended by ``now`` (its time ran out, or it was expired by hand); return how many.

    The worker's (``base.worker``, every ``REAPER_INTERVAL_SECONDS``) and ``manage.py demo_expire``'s. Every demo
    that ended is marked ``expired`` and due (``hub_due``) first, then dropped and purged under its lease
    (``base.tenancy.provision.drop``: its database and its files, then ``base.demo.purge`` in its own transaction). One
    that fails, or whose lease the worker holds (it was still being made), is logged or left, and the others are purged;
    the worker takes it again as due. Then the tombstones older than ``DEMO_TOMBSTONE_DAYS`` are forgotten.
    """
    from base.tenancy import provision

    now = now or timezone.now()
    ended = list(
        Hub.objects.filter(
            Q(status__in=OPEN_DEMO_STATUSES, expires_at__lte=now)
            | Q(status__in=(Hub.Status.EXPIRED, Hub.Status.DROPPING)),
            is_demo=True,
        ).only("id", "slug")
    )
    with _control_transaction():
        Hub.objects.filter(pk__in=[hub.pk for hub in ended], status__in=OPEN_DEMO_STATUSES).update(
            status=Hub.Status.EXPIRED, updated_at=now
        )
        for hub in ended:
            HubDue.mark_due(hub, now)
    purged = 0
    for hub in ended:
        try:
            dropped = provision.drop(hub, now=now)
        except Exception:
            logger.exception("base.demo.purge_failed demo=%s: it is tried again on the next pass.", hub.slug)
            continue
        purged += dropped
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


def gone_hubs(ids: list[UUID]) -> dict[UUID, Hub | None]:
    """Of ``ids``, the hubs that are gone for good, each with its tombstone: ``purged``, or ``None`` with no row in the
    registry at all (a demo's, forgotten after ``DEMO_TOMBSTONE_DAYS``). Any other status is not gone: on its way,
    served, restorable or still being dropped (its own purge deletes its files, and retries).

    A plain read of control (the caller opens ``use_control``), no operation: ``manage.py delete_leftover_hub_files``'s,
    which deletes the files these left in the store before hub#781 (hub#785)."""
    rows = {hub.pk: hub for hub in Hub.objects.filter(pk__in=ids).only("id", "slug", "status", "is_demo", "purged_at")}
    return {
        hub_id: rows.get(hub_id)
        for hub_id in ids
        if hub_id not in rows or rows[hub_id].status == Hub.Status.PURGED
    }

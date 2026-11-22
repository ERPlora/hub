"""The sessions the SaaS opens on the Hub and their end, and the business's people in its own database.

The session is not an ``@operation``: it runs before there is an actor, for ``/auth/callback`` only, and needs the
request to log in. It lives on ``django.contrib.auth`` + ``Membership``.

Two doors, each with its own local copy of the SaaS account: a customer entering their hub
(:func:`open_session_from_saas`, ``saas:<id>``, never staff) and the platform's staff entering the
Hub admin on the platform host (:func:`open_admin_session_from_saas`, ``saas-staff:<id>``). Separate copies, so an account that is both staff and a hub member neither loses
``is_staff`` in the admin nor gains it on its hub when it enters by the other door.
"""

import datetime as dt
from functools import partial
from uuid import UUID

from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Max
from django.http import HttpRequest
from django.utils import timezone
from live.context import OperationContext, Scope, system_context
from live.live_registry import ALL_EVENTS
from live.operations import INTERNAL, atomic, operation
from live.outbox import notify

from base import access, queries
from base.access import CREDENTIAL_SESSION_KEY
from base.auth import PLATFORM_ADMIN, PLATFORM_SUPPORT, RedeemedUser
from base.session_host import PLATFORM_SESSION_HOST, session_host
from base.models import Hub, HubUser, Membership, SessionOwner, TrustedDevice
from base.registry import internal_only
from base.schemas.sessions import HubUserSyncIn, HubUserSyncOut, SessionRevokeIn, SessionRevokeOut
from control.models import HubVisit


MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"
#: The SaaS account the session belongs to (``SessionOwner`` is the index /internal/sessions/revoke reads).
SAAS_USER_ID_SESSION_KEY = "saas_user_id"
#: Read-only group of ``platform_support`` in the Hub admin (the SaaS's ``support``).
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
    request.session[CREDENTIAL_SESSION_KEY] = credential
    if device is not None:
        policy = queries.access.access_settings().pin_policy
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
    on which device and with which credential it was opened; and, on a hub, that its person came in today
    (``control.HubVisit``, its nightly use and who is active now).

    ``login`` gives the session a new key and saves it, unless it flushed another user's session first: then it has
    no key until it is saved, which happens here, in the login's transaction.
    """
    if request.session.session_key is None:
        request.session.save()
    host = session_host(request) or ""
    SessionOwner.objects.update_or_create(
        session_id=request.session.session_key,
        defaults={
            "saas_user_id": saas_user_id,
            "host": host,
            "device_id": None if device is None else device.pk,
            "credential": credential,
        },
    )
    if host and host != PLATFORM_SESSION_HOST:
        # Who came into the business today (its nightly use, ``base.usage``): once a day, whatever the logins; what they
        # do next keeps ``last_seen_at`` going (``base.meter``).
        now = timezone.now()
        HubVisit.objects.bulk_create(
            [HubVisit(host=host, day=now.date(), saas_user_id=saas_user_id, last_seen_at=now)], ignore_conflicts=True
        )


@transaction.atomic  # control's: the account's copy, its Membership and the session
@atomic  # the hub's: the person (base.HubUser), the trusted device and the ones it ends
def open_session_from_saas(request: HttpRequest, redeemed: RedeemedUser, slug: str):
    """Get or create the customer copy, set its role on ``slug`` and log it in (a new session key).

    The local user is a copy of a customer of the SaaS: never staff nor superuser, so a hub role
    never opens the Hub's ``/admin/`` (that one belongs to the platform's staff). A copy raised to
    staff by hand is lowered again here.
    """
    user = _local_copy(redeemed, username=username_for(redeemed.user_id), is_staff=False, is_superuser=False)
    Membership.objects.update_or_create(user=user, host=slug, defaults={"role": redeemed.role})
    ensure_hub_user(user)
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


# ── The device a session is opened on ──────────────────────────────────────────────────────────────────────


def trust_device(request: HttpRequest, user) -> TrustedDevice:
    """This browser's device of the hub, made a trusted one by an entry with the account.

    The device of the cookie ``hub_device`` if the hub knows it (its mode and name are kept), else a new one with a
    new token. Its last person in and entry are now's, and a notice of sessions it lost (``ended_reason``) is read.
    """
    now = timezone.now()
    device = queries.devices.device_of(request, for_update=True)
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
    """How a person is named in this hub: its profile's name, else its account's (``base.queries.people.person_label``)."""
    return queries.people.person_label(user)[:150]


def _end_other_devices(slug: str, device: TrustedDevice) -> None:
    """Keep within the devices the business's plan covers (``plan.max_devices`` of the SaaS's photo; 0 or none, no
    cap): an entry on ``device`` ends the live sessions on this host of every other device past the
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


# ── The people of the business in its own database (base.HubUser) ────────────────────────────────────────────────


def _account_id(username: str) -> UUID | None:
    """The erplora.com account behind a copy ``saas:<id>``; ``None`` for anyone else (a demo's owner) or an id that is
    no UUID (the SaaS's are)."""
    if not username.startswith(SAAS_USERNAME_PREFIX):
        return None
    try:
        return UUID(username.removeprefix(SAAS_USERNAME_PREFIX))
    except ValueError:
        return None


def _bring_up_to_date(person: HubUser, wanted: dict) -> bool:
    """Save in ``person`` what differs from ``wanted``; whether anything did."""
    changed = [field for field, value in wanted.items() if getattr(person, field) != value]
    if changed:
        for field in changed:
            setattr(person, field, wanted[field])
        person.save(update_fields=changed)
    return bool(changed)


def ensure_hub_user(user) -> HubUser:
    """The ``HubUser`` of control's ``user`` in the active hub's database, made or brought up to date with what its
    copy says (name, email, whether it is active). Every entry to the hub calls it (the code of erplora.com, a demo, a
    PIN or a badge), and so does the first write of whoever has none yet (:func:`acting_hub_user`)."""
    username = user.get_username()
    wanted = {
        "account_id": _account_id(username),
        "email": user.email or "",
        "name": user.get_full_name()[: HubUser._meta.get_field("name").max_length],
        "is_active": user.is_active,
    }
    # get_or_create: two first entries at once end in one person, not an IntegrityError (its savepoint is on the hub's
    # own alias).
    person, created = HubUser.objects.get_or_create(username=username, defaults=wanted)
    if not created:
        _bring_up_to_date(person, wanted)
    return person


def acting_hub_user(ctx: OperationContext) -> HubUser | None:
    """The ``HubUser`` of the person behind ``ctx``, made if missing, for what a write signs; ``None`` for the
    platform, an API key or nobody (no person)."""
    if not queries.people.is_a_person(ctx.actor):
        return None
    return ensure_hub_user(ctx.actor)


# Not an assistant tool: the SaaS's photo (/internal), no person.
@operation(
    "base.hub_user.sync", kind="command", permission=None, input=HubUserSyncIn, output=HubUserSyncOut, ai=INTERNAL
)
def hub_user_sync(ctx: OperationContext, data: HubUserSyncIn) -> dict:
    """Make the people of the business's database say what the SaaS's photo lists (its ``members``), before they ever
    enter: who is new is made, with the name and the email the photo says (what it leaves out stays as it was); who is
    no longer in the business keeps their name on what they signed and is no longer active: everyone the photo leaves
    out, since a business's database holds only its own people. The photo's own transaction calls it in the
    business's database (:func:`hub_state_apply`), after the memberships changed; ``left`` is the SaaS's, unused here."""
    internal_only(ctx)
    made = updated = 0
    listed = set()
    for member in data.members:
        username = username_for(str(member.user_id))
        listed.add(username)
        wanted = {"account_id": member.user_id, "is_active": True}
        if member.email is not None:
            wanted["email"] = member.email
        if member.name is not None:
            wanted["name"] = member.name[: HubUser._meta.get_field("name").max_length]
        person, created = HubUser.objects.get_or_create(username=username, defaults=wanted)
        if created:
            made += 1
        elif _bring_up_to_date(person, wanted):
            updated += 1
    gone = HubUser.objects.filter(username__startswith=SAAS_USERNAME_PREFIX, is_active=True).exclude(
        username__in=listed
    )
    return {"made": made, "updated": updated, "left": gone.update(is_active=False)}


def _sync_hub_users(hub: Hub, members: list, left: list[str]) -> None:
    """The photo's people in the business's own database (``base.hub_user.sync``), and who just left it."""
    from base.tenancy.context import use_hub

    with use_hub(hub):
        hub_user_sync(system_context(Scope("host", hub.slug)), HubUserSyncIn(members=members, left=left))


# ── The sessions of a SaaS account (/internal/sessions/revoke) ───────────────────────────────────────────────────


# Not an assistant tool: the platform's end of a session, no person.
@operation(
    "base.session.revoke",
    kind="command",
    permission=None,
    input=SessionRevokeIn,
    output=SessionRevokeOut,
    ai=INTERNAL,
)
def session_revoke(ctx: OperationContext, data: SessionRevokeIn) -> dict:
    """End the Hub's sessions of the SaaS account ``data.user_id``: those on the business ``data.hub_id`` or, without
    it, every one of them, the Hub admin's included (as OIDC's back-channel logout).

    The SaaS sends it after the COMMIT that removed the person from a business or handed the business over (with
    the business), or after a password change, «sign out everywhere» or deleting the account
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


def _apply_members(hub: Hub, members: list) -> list[str]:
    """Make the memberships of ``hub`` say what the photo's ``members`` say (HUBS-F26, F27 and F28 of the SaaS).

    A person whose role changed has it now and keeps their sessions: the business's open apps wake after the COMMIT
    (:func:`_wake_open_apps`) and every request and live re-run reads the permissions of the new role. A person no
    longer listed loses their membership and their sessions on this business end (:func:`_end_sessions`). Nobody is
    created: a person the Hub has not seen yet takes their role when they first enter (:func:`open_session_from_saas`).
    Only the copies of SaaS accounts are the photo's (``saas:<id>``): a demo's owner is not. Returns the SaaS accounts
    that left the business (their memberships gone).
    """
    wanted = {str(member.user_id): member.role for member in members}
    changed_role = False
    left = []
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
            left.append(saas_user_id)
        elif role != membership.role:
            membership.role = role
            membership.save(update_fields=["role"])
            changed_role = True
    if left:
        # A session that noted no host (from before the rule) is valid on every host, this business's too.
        _end_sessions(SessionOwner.objects.filter(saas_user_id__in=left, host__in=[hub.slug, ""]))
    if changed_role:
        transaction.on_commit(partial(_wake_open_apps, hub.slug), robust=True)
    return left


def _wake_open_apps(slug: str) -> None:
    """The business of ``slug`` just stopped serving the app (suspended, cancelled), some of its sessions ended, or
    somebody's role in it changed: every open live stream and print socket of its host re-runs now («*», everything may have changed), hears the host
    gate and its session again (``base.operations.HubContextBuilder.refresh``) and ends if they no longer hold,
    instead of waiting for the hub's next write or the safety re-run (BILLING-F16 of the SaaS, step 4: the devices with
    the app open leave for the Hub's page)."""
    notify(Scope("host", slug), [ALL_EVENTS])

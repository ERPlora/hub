"""The way in to a hub: the business's access settings, the PIN door and its faces, and how this session was opened."""

from typing import Any
from uuid import UUID

from django.contrib.auth.hashers import check_password
from django.http import HttpRequest
from live.context import OperationContext
from live.operations import AI, operation

from base import access, saas_store
from base.models.access import AccessSettings, Credential
from base.models import Membership
from base.models.sessions import SessionOwner
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas.access import AccessDoorIn, AccessDoorOut, AccessSettingsIn, AccessSettingsOut
from base.throttle import client_key

from .devices import device_of
from .people import face_name


# ── The way in: devices, PIN, badge, the business's dial and the person's profile ────────────────────────────────


def access_settings() -> AccessSettings:
    """How the business asks who is at the till: its row, or the factory values (an unsaved row) without one. A
    stored value this build does not understand reads as the factory one, never as «not asking» (``base.access``)."""
    row = AccessSettings.objects.first() or AccessSettings()
    row.pin_policy = access.policy_or_default(row.pin_policy)
    row.pin_inactivity_minutes = access.inactivity_or_default(row.pin_inactivity_minutes)
    row.pin_length = access.pin_length_or_default(row.pin_length)
    return row


def pin_people(slug: str, *, exclude: str = "") -> list[tuple[Credential, Any]]:
    """The active people of ``slug`` with a PIN, with their user (but ``exclude``, a username); in no order.

    Two reads, never a join: who is a member is control's (``Membership``) and the PINs are the hub's."""
    users = {
        membership.user.get_username(): membership.user
        for membership in Membership.objects.team(slug).select_related("user")
    }
    users.pop(exclude, None)
    credentials = Credential.objects.filter(username__in=list(users)).exclude(pin_hash="")
    return [(credential, users[credential.username]) for credential in credentials]


def pin_owner(slug: str, person: str, pin: str) -> Any | None:
    """The active person of ``slug`` whose way in is ``person`` and whose PIN is ``pin``; else ``None``, whatever
    failed (an unknown id, another hub's person, a deactivated one, no PIN, a wrong one: the door says the same)."""
    try:
        person_id = UUID(person)
    except (TypeError, ValueError):
        return None
    credential = Credential.objects.filter(pk=person_id).exclude(pin_hash="").first()
    if credential is None:
        return None
    membership = (
        Membership.objects.team(slug).filter(user__username=credential.username)
        .select_related("user")
        .first()
    )
    if membership is None or not check_password(pin, credential.pin_hash):
        return None
    return membership.user


def pin_door_open(request: HttpRequest, slug: str) -> bool:
    """Whether this browser enters ``slug`` by the PIN pad: a shared device of the hub, a business that asks, and
    somebody of it with a PIN to choose."""
    device = device_of(request)
    if device is None or not access.pin_offered(device.mode, access_settings().pin_policy):
        return False
    return bool(pin_people(slug))


@operation(
    "base.access.door",
    kind="query",
    permission=None,
    input=AccessDoorIn,
    output=AccessDoorOut,
    ai={
        "description": "Not an assistant tool (what the browser of a till shows by itself, before anyone is in): the "
        "people who can enter with a PIN on this shared device, by name and initials, and the PIN's length."
    },
)
def access_door(ctx: OperationContext, data: AccessDoorIn) -> dict[str, Any]:
    """The way in of the browser that asks: on a shared device of the hub of a business that asks, the
    people of this hub with a PIN, by name and initials (never their email nor account) and the PIN's length.

    The grid reaches only whom the PIN would let in: anyone else, and an address that tried
    too many wrong PINs (with how long it still waits), hears the same answer with nobody in it."""
    return _door(ctx)


@operation(
    "base.access.faces",
    kind="query",
    permission=VIEW_HOME,
    input=AccessDoorIn,
    output=AccessDoorOut,
    ai={
        "description": "Not an assistant tool (the «Switch user» grid of the till in hand, followed live): the people "
        "who can enter with a PIN on this device, by name and initials."
    },
)
def access_faces(ctx: OperationContext, data: AccessDoorIn) -> dict[str, Any]:
    """The door's grid for a session: «Switch user», live, so a new PIN shows up and a person removed
    leaves without reloading the till."""
    return _door(ctx)


def _door(ctx: OperationContext) -> dict[str, Any]:
    settings = access_settings()
    device = device_of(ctx.request)
    offered = device is not None and access.pin_offered(device.mode, settings.pin_policy)
    wait = access.PIN_ADDRESS_LIMIT.wait(ctx.scope.key, client_key(ctx.request)) if offered else 0
    people = [] if not offered or wait else pin_people(ctx.scope.key)
    faces = sorted(
        ({"id": str(credential.pk), "name": (name := face_name(user)), "initials": access.initials(name)}
         for credential, user in people),
        key=lambda face: face["name"].casefold(),
    )
    return {
        "pin": offered and (bool(faces) or wait > 0),
        "pin_length": settings.pin_length,
        "people": faces,
        "wait": wait,
        # «Upgrade plan» to a browser nobody is signed in on: erplora.com's plans, never this hub's id.
        "plan_url": saas_store.plans_url(ctx.scope.key),
    }


def has_pin(user) -> bool:
    return Credential.objects.filter(username=user.get_username()).exclude(pin_hash="").exists()


@operation(
    "base.access.settings",
    kind="query",
    permission=VIEW_HOME,
    input=AccessSettingsIn,
    output=AccessSettingsOut,
    ai=AI(
        description=(
            "Reads how the business asks who is at the till, as the PIN pad card of Settings › General shows it: "
            "showing the PIN pad is off when pin_policy is never; asking again after inactivity is "
            "pin_inactivity_minutes min when pin_policy is always, and until signing out when it is per_shift (its "
            "minutes then do not count); and how many digits a PIN has. With the PIN pad on, each person enters with "
            "their own PIN and every sale carries their name. Say it to the person as that card does, in their "
            "language."
        ),
        asks={
            "en": (
                "how many digits is the PIN?",
                "does the till ask for the PIN again after a while?",
                "when does the screen lock and ask who's there?",
            ),
            "es": (
                "¿cada cuánto pide el PIN la caja?",
                "¿se bloquea la caja si nadie la toca?",
                "¿el PIN es de 4 o de 6 cifras?",
            ),
        },
    ),
)
def access_settings_get(ctx: OperationContext, data: AccessSettingsIn) -> dict[str, Any]:
    """The «PIN pad» card of Settings › General: what the Hub confirmed, for everyone of the hub."""
    row = access_settings()
    return {
        "pin_policy": row.pin_policy,
        "pin_inactivity_minutes": row.pin_inactivity_minutes,
        "pin_length": row.pin_length,
        "can_change": ctx.has(ADMINISTER_HUB),
    }


def shell_access(request: HttpRequest, slug: str) -> dict[str, Any]:
    """What the shell needs of this session's way in (``hub-home``'s ``access``, ``base.spa``): how it was opened,
    whether «Switch user» is offered (a shared device of the hub of a business that asks, with somebody on
    its grid) and, when the business always asks on such a device, after how many idle minutes it locks."""
    credential = (
        SessionOwner.objects.filter(session_id=request.session.session_key).values_list("credential", flat=True).first()
        or SessionOwner.Credential.ACCOUNT
    )
    device = device_of(request)
    settings = access_settings()
    offered = device is not None and access.pin_offered(device.mode, settings.pin_policy)
    return {
        "credential": credential,
        "switch_user": offered and bool(pin_people(slug)),
        "idle_minutes": settings.pin_inactivity_minutes if offered and settings.pin_policy == access.ALWAYS else None,
    }

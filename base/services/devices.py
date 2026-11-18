"""The way in: a session on a trusted device, the PIN (``base.pin.set``), the badges' key and the devices of the
business (``base.device.*``).
"""

import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext, ngettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied, Unauthorized
from live.operations import AI, atomic, operation
from live.outbox import record_event

from base import access, events, queries
from base.middleware import session_host
from base.models import AccessSettings, Credential, Membership, SessionOwner, TrustedDevice
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas import (
    DeviceByIdIn,
    DeviceCurrentOut,
    DeviceModeIn,
    DevicePruneIn,
    DevicePruneOut,
    DeviceRemoveOut,
    DeviceRenameIn,
    PinSetIn,
    PinSetOut,
)
from base.services.sessions import (
    SAAS_USERNAME_PREFIX,
    _end_other_devices,
    _end_sessions,
    _entered,
    _log_in,
    ensure_hub_user,
)


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
    length = queries.access.access_settings().pin_length
    problem = access.pin_problem(data.pin, length)
    if problem is not None:
        raise InvalidPayload(_PIN_PROBLEMS[problem](length), code=f"base.pin_{problem}", fields={"pin": problem})
    credential = Credential.objects.select_for_update().filter(username=username).first()
    if credential is not None and credential.pin_hash and not check_password(data.current, credential.pin_hash):
        raise PermissionDenied(
            gettext("That is not your current PIN. Type it right to set a new one."), code="base.pin_current_wrong"
        )
    if any(check_password(data.pin, other.pin_hash) for other, _ in queries.access.pin_people(ctx.scope.key, exclude=username)):
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
    return queries.people.person_label(ctx.actor)[:150] if hasattr(ctx.actor, "get_username") else str(ctx.actor)[:150]


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
    device = queries.devices.device_of(ctx.request, for_update=True)
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
    here = queries.devices.device_of(ctx.request)
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
    ids = list(queries.devices.unused_devices(queries.devices.device_of(ctx.request)).select_for_update().values_list("pk", flat=True))
    _remove_devices(ids)
    record_event(ctx, events.DEVICES_PRUNED, {"removed": len(ids)})
    return {"removed": len(ids)}


def _remove_devices(ids: list) -> None:
    """End the sessions on the devices ``ids`` on every host (their tabs wake and leave) and forget the devices."""
    if not ids:
        return
    _end_sessions(SessionOwner.objects.filter(device_id__in=ids))
    TrustedDevice.objects.filter(pk__in=ids).delete()

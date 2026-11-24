"""The business's PIN pad (``base.access.settings_update``) and the person's profile (``base.profile.*``).
"""

import base64
import binascii
import hashlib
import io

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.validators import validate_email
from django.db import IntegrityError
from django.utils.translation import gettext, pgettext_lazy
from live.assistant import choice_label
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import AI, atomic, operation
from live.outbox import record_event
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from base import access, chosen_language, events, queries
from base.media import AVATARS_FOLDER
from base.models.access import AccessSettings
from base.models.profile import Profile
from base.operations import hub_id
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas.access import AccessSettingsIn, AccessSettingsOut, AccessSettingsUpdateIn
from base.schemas.profile import (
    AvatarIn,
    AvatarOut,
    AvatarRemoveIn,
    PreferencesIn,
    PreferencesOut,
    ProfileIn,
    ProfileOut,
    ProfileUpdateIn,
)
from base.services.devices import _actor_label
from base.storage import hub_prefix


# The controls of the «PIN pad» card of Settings › General, by its words.
SHOW_PIN_PAD = pgettext_lazy("pin pad", "Show PIN pad")
ASK_AGAIN = pgettext_lazy("pin pad", "Ask again after inactivity")
UNTIL_SIGNING_OUT = pgettext_lazy("pin pad", "Until signing out")
MINUTES = pgettext_lazy("pin pad", "%(n)s min")
PIN_DIGITS = pgettext_lazy("pin pad", "PIN digits")
DIGITS = pgettext_lazy("pin pad", "%(n)s digits")


def _pin_pad_summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The card as the «PIN pad» card of Settings › General would read after the change: each of its controls that the
    change sets, with the value it will show. The minutes only show when it asks again after inactivity."""
    sent = {name: value for name, value in arguments.items() if value is not None}
    now = queries.access.access_settings()
    policy = sent.get("pin_policy", now.pin_policy)
    lines = []
    if "pin_policy" in sent:
        lines.append(_pin_pad_line("pin_pad", SHOW_PIN_PAD, policy != access.NEVER))
    if sent.keys() & {"pin_policy", "pin_inactivity_minutes"} and policy != access.NEVER:
        minutes = sent.get("pin_inactivity_minutes", now.pin_inactivity_minutes)
        again = MINUTES % {"n": minutes} if policy == access.ALWAYS else UNTIL_SIGNING_OUT
        lines.append(_pin_pad_line("ask_again", ASK_AGAIN, again))
    if "pin_length" in sent:
        lines.append(_pin_pad_line("pin_length", PIN_DIGITS, DIGITS % {"n": sent["pin_length"]}))
    return lines or fields


def _pin_pad_line(name: str, label, value) -> dict:
    if isinstance(value, bool):
        return {"name": name, "label": str(label), "kind": "bool", "value": value}
    return {"name": name, "label": str(label), "kind": "text", "value": str(value)}


@operation(
    "base.access.settings_update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=AccessSettingsUpdateIn,
    output=AccessSettingsOut,
    ai={
        "description": (
            "Changes how the business asks who is at the till, as the «PIN pad» card of Settings › General: «Show "
            "PIN pad» on or off (off is pin_policy never) and «Ask again after inactivity»: 1, 5, 10, 15 or 30 min "
            "(pin_policy always with those pin_inactivity_minutes) or «Until signing out» (pin_policy per_shift); and "
            "PINs of 4 or 6 digits. With the PIN pad on, each person enters with their own PIN and every sale carries "
            "their name. Read access.settings first and say how it is now by those names; to ask again after "
            "inactivity, ask the person how many minutes when they have not said it."
        ),
        "risk": "high",
        "summary": _pin_pad_summary,
        "asks": {
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
    },
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
    return queries.access.access_settings_get(ctx, AccessSettingsIn())


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
    user = queries.profile.signed_in(ctx)
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
    return queries.profile.profile_get(ctx, ProfileIn())


def _preferences_summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The card: each preference that is sent, an empty one by the choice «My profile» names it with (the business's),
    since a blank datum does not show."""
    return [
        {**field, "kind": "text", "value": str(choice_label("base", "profile", field["name"], ""))}
        if field["value"] == ""
        else field
        for field in fields
        if field["value"] is not None
    ]


@operation(
    "base.profile.preferences_set",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=VIEW_HOME,
    input=PreferencesIn,
    output=PreferencesOut,
    ai={
        "description": (
            "Sets the person's own language (Spanish, English or the business's) and appearance. Send only what they "
            "asked to change: what is not sent stays as it is; an empty value goes back to the business's."
        ),
        "risk": "normal",
        "summary": _preferences_summary,
        "asks": {
            "en": ("switch me to English", "put the app in dark mode", "change my language to Spanish"),
            "es": ("ponme el idioma en inglés", "quiero el modo oscuro", "cámbiame la apariencia a clara"),
        },
    },
)
def preferences_set(ctx: OperationContext, data: PreferencesIn) -> dict:
    """«Preferences»: what is sent is saved as chosen and applied at once; empty = the business's. They follow the
    person on any device of the hub (the language from their next entry on another one)."""
    user = queries.profile.signed_in(ctx)
    profile = _profile(user)
    changes = data.model_dump(exclude_none=True)
    for field, value in changes.items():
        setattr(profile, field, value)
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    language = queries.profile.language_of(user, ctx.scope.key) or settings.LANGUAGE_CODE
    if "language" in changes:
        chosen_language.choose(ctx.request, language)
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
    user = queries.profile.signed_in(ctx)
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
    return {"avatar_url": queries.profile.avatar_url(ctx, name)}


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
    user = queries.profile.signed_in(ctx)
    profile = _profile(user)
    profile.avatar = ""
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    return {"avatar_url": ""}

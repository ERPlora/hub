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
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import AI, atomic, operation
from live.outbox import record_event
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from base import events, queries
from base.media import AVATARS_FOLDER
from base.models import AccessSettings, Profile
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
    user = queries.profile.signed_in(ctx)
    profile = _profile(user)
    profile.language, profile.theme_mode, profile.palette = data.language, data.theme_mode, data.palette
    profile.ui_scale = data.ui_scale
    profile.save()
    record_event(ctx, events.PROFILE_UPDATED, {})
    language = queries.profile.language_of(user, ctx.scope.key) or settings.LANGUAGE_CODE
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

"""The person's profile (``base.profile.get``): its language, its appearance and its avatar."""

from typing import Any

from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Unauthorized
from live.operations import AI, operation

from base.models import Hub, Membership
from base.models.profile import Profile
from base.operations import hub_id
from base.permissions import VIEW_HOME
from base.schemas.profile import ProfileIn, ProfileOut
from base.storage import media_url

from .access import access_settings, has_pin


def chosen_language(user) -> str:
    """The language a person chose in «My profile»; empty while it is the business's."""
    return Profile.objects.filter(username=user.get_username()).values_list("language", flat=True).first() or ""


def language_of(user, slug: str) -> str:
    """The language a person works in on ``slug``: their «My profile» choice, else the business's."""
    return chosen_language(user) or Hub.objects.filter(slug=slug).values_list("language", flat=True).first() or ""


@operation(
    "base.profile.get",
    kind="query",
    permission=VIEW_HOME,
    input=ProfileIn,
    output=ProfileOut,
    ai=AI(
        description="Reads the person's own profile in this hub: name, contact email, language and appearance.",
        asks={
            "en": ("what email is on my profile?", "show me my profile"),
            "es": ("¿qué correo tengo en mi perfil?", "¿con qué nombre salgo yo?"),
        },
    ),
)
def profile_get(ctx: OperationContext, data: ProfileIn) -> dict[str, Any]:
    """«My profile»: always the profile of whoever asks; without a row, the account's name."""
    user = signed_in(ctx)
    profile = Profile.objects.filter(username=user.get_username()).first()
    role = Membership.objects.filter(user=user, host=ctx.scope.key).values_list("role", flat=True).first() or ""
    return {
        "first_name": profile.first_name if profile else user.first_name,
        "last_name": profile.last_name if profile else user.last_name,
        "contact_email": profile.contact_email if profile else "",
        "avatar_url": avatar_url(ctx, profile.avatar) if profile and profile.avatar else "",
        "language": profile.language if profile else "",
        "theme_mode": profile.theme_mode if profile else "",
        "palette": profile.palette if profile else "",
        "ui_scale": profile.ui_scale if profile else 100,
        "role": role,
        "has_pin": has_pin(user),
        "pin_length": access_settings().pin_length,
    }


def signed_in(ctx: OperationContext):
    """The person of the session, or 401: «My profile» and one's own PIN are nobody's without one."""
    if ctx.actor is None or not hasattr(ctx.actor, "get_username"):
        raise Unauthorized(gettext("Sign in to see your profile."), code="base.sign_in_required")
    return ctx.actor


def avatar_url(ctx: OperationContext, name: str) -> str:
    return media_url(hub_id(ctx.scope), name)


def appearance_of(user) -> dict[str, str | int]:
    """The appearance a person chose in «My profile», for the shell to paint on any device they enter;
    empty mode and palette, the business's."""
    chosen = Profile.objects.filter(username=user.get_username()).values("theme_mode", "palette", "ui_scale").first()
    if chosen:
        return {"theme_mode": chosen["theme_mode"], "palette": chosen["palette"], "ui_scale": chosen["ui_scale"]}
    return {"theme_mode": "", "palette": "", "ui_scale": 100}

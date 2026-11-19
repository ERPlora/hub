"""The booking page's logo (``apps.online_booking.logo``): its upload, and the check that what the settings save is
one of this business's uploads."""

from django.core.files.storage import storages
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import INTERNAL, operation

from apps.online_booking.logo import FOLDER, NOT_AN_UPLOAD, LogoOut
from base import public_images
from base.operations import hub_id
from base.schemas.public_images import ImageUploadIn
from base.storage import hub_prefix


# Not an assistant tool: a file the Settings screen uploads.
@operation(
    "online_booking.settings.upload_logo",
    kind="command",
    permission="online_booking.manage_settings",
    input=ImageUploadIn,
    output=LogoOut,
    expose_api=True,
    ai=INTERNAL,
)
def upload_logo(ctx: OperationContext, data: ImageUploadIn) -> dict:
    """Keep the logo; the page shows it once the settings save it."""
    kept = public_images.keep(ctx, FOLDER, data)
    return {"id": kept.name, "url": kept.url}


def check_logo(ctx: OperationContext, name: str) -> None:
    """A logo the settings take: none, or one uploaded to ``ctx``'s business (422 on ``logo`` otherwise)."""
    if name and not storages["hub_files"].exists(f"{hub_prefix(hub_id(ctx.scope))}/{FOLDER}{name}"):
        raise InvalidPayload(str(NOT_AN_UPLOAD), fields={"logo": str(NOT_AN_UPLOAD)})

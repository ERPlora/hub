"""The service's image (SERVICE-F34, F35; base.images): a picture of the library or a photo of its own, kept under its
hub's prefix.
"""

from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.service import events
from apps.service.models import Service
from apps.service.queries.catalog import find_service, load_service
from apps.service.schemas.catalog import ServiceOut
from apps.service.schemas.service_images import ServiceImageIn, ServiceImageUploadIn
from apps.service.services.writes import _apply
from base import images

#: Where a service's own photos are kept under its hub's prefix: the folder ``members_media`` serves (apps.py).
PHOTOS = "service/services/"


@operation(
    "service.service.set_image",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_service",
    input=ServiceImageIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Set the image («foto») a service shows on the till («ponle foto al corte de señora»), named by "
        "its id or its name: an image of ERPlora's shared library by its reference (catalog:<folder>/<name>, from service.service.suggest_image or "
        "base.catalog_image.search), or empty to show none (its initials).",
        "risk": "normal",
        "asks": {
            "en": ("put the second picture on the manicure service", "use that drawing as the beard trim's photo"),
            "es": ("ponle al tinte la foto que me has propuesto", "usa la segunda imagen para el servicio de manicura"),
        },
    },
)
def set_image(ctx: OperationContext, data: ServiceImageIn) -> dict:
    """SERVICE-F34: an image of the library or none; anything else (a photo of its own too, which only its upload
    writes) is refused before anything changes. The photo of its own it let go is deleted once this is saved."""
    service = find_service(data.id, data.service, lock=True)
    images.check(ctx, data.image)
    _change_image(ctx, service, data.image)
    return load_service(service.id, ctx.scope)


@operation(
    "service.service.upload_image",
    kind="command",
    permission="service.change_service",
    input=ServiceImageUploadIn,
    output=ServiceOut,
    expose_api=True,
    ai={
        "description": "Not an assistant tool (it takes the photo the person picks in the service's form): keeps a "
        "photo of the service, a JPG, PNG or WebP of 2 MB at most, as its image.",
        "risk": "normal",
    },
)
def upload_image(ctx: OperationContext, data: ServiceImageUploadIn) -> dict:
    """SERVICE-F35: the photo becomes a 512 × 512 WebP of its own (``base.images``), within the plan's space, and
    takes the place of the one the service had, which is deleted once this is saved."""
    webp = images.to_webp(images.decode(data.data_base64, language=ctx.language), language=ctx.language)
    service = find_service(data.id, data.service, lock=True)
    _change_image(ctx, service, images.keep_photo(ctx, PHOTOS, webp))
    return load_service(service.id, ctx.scope)


def _change_image(ctx: OperationContext, service: Service, image: str) -> None:
    """Show ``image`` on ``service`` (no change, no event); the photo of its own it let go is deleted once saved.
    Archiving keeps it (SERVICE-F05 restores the service with it)."""
    if service.image == image:
        return
    previous = service.image
    _apply(service, {"image": image}, ctx)
    service.save(update_fields=["image", "updated_by", "updated_at"])
    record_event(ctx, events.SERVICE_UPDATED, {"id": str(service.id)})
    images.let_go(ctx, previous)

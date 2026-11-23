"""The shared image library (``base.catalog_image.*``), named in the business's language."""

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy
from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.operations import AI, operation

from base import image_catalog
from base.models import Hub
from base.permissions import VIEW_HOME
from base.schemas.catalog_images import CatalogImageOut, CatalogImagePage, CatalogImageRefIn, CatalogImageSearchIn


# ── The shared image library (base.image_catalog) ──────────────────────────────────────────────────────────────────


LIBRARY_UNAVAILABLE = gettext_lazy("The image library could not be loaded.")

# A reference reads like words («catalog:hospitality/paella_mixta»), so the rule against writing ids in an answer does
# not stop the model from listing it beside each title.
BY_TITLE_ALONE = (
    "Name each image by its title alone and ask which one; its reference (catalog:<folder>/<name>) only goes "
    "to the tool that sets it, never in the answer, not in a table either."
)


def image_suggestion(set_image: str) -> str:
    """The end of what the model reads of a read that proposes images for a record's photo: what it brings, that it
    sets none and that ``set_image`` sets the one the person picks."""
    return (
        "the best matches for its name first, each with its title and its reference. It never sets one: set the one "
        f"the person picks with {set_image}. {BY_TITLE_ALONE}"
    )


def image_library(ctx: OperationContext) -> image_catalog.Library:
    """The shared image library, or the 503 ``base.image_library_unavailable`` in ``ctx``'s language when its manifest
    cannot be read: an empty answer would say «no image» when the truth is «not now». Inventory, Services and Combos
    ask it too, so the person reads the same sentence from every screen."""
    try:
        return image_catalog.library()
    except image_catalog.LibraryUnavailable:
        with translation.override(ctx.language):
            raise OperationError(
                str(LIBRARY_UNAVAILABLE), code="base.image_library_unavailable", status=503
            ) from None


def business_language(ctx: OperationContext) -> str:
    """The language the business works in, as erplora.com registered it (Settings › Business), else the deployment's:
    what its products and services are named in, so what the library's images are titled in on its screens."""
    language = Hub.objects.filter(slug=ctx.scope.key).values_list("language", flat=True).first()
    return language or settings.LANGUAGE_CODE


@operation(
    "base.catalog_image.search",
    kind="query",
    permission=VIEW_HOME,
    input=CatalogImageSearchIn,
    output=CatalogImagePage,
    ai=AI(
        description=(
            "Finds an image for a product, a service or a set menu in ERPlora's shared image library by what it is "
            "called, in Spanish or English («café con leche», «women's haircut»), the best match first, each with its "
            "title and the reference that sets it as the image of a product, a service or a set menu. Empty: the whole "
            f"library by title. {BY_TITLE_ALONE}"
        ),
        asks={
            "en": (
                "find a picture of a cappuccino",
                "is there an image for a women's haircut?",
                "look for a burger photo in the library",
            ),
            "es": (
                "búscame una foto de café con leche",
                "¿hay alguna imagen de corte de pelo de mujer?",
                "encuéntrame un dibujo de hamburguesa",
            ),
        },
    ),
)
def catalog_image_search(ctx: OperationContext, data: CatalogImageSearchIn) -> dict:
    """The library is everyone's: who may see the hub's Home may look an image up (the screens that set one need their
    own app's permission). Any language matches; titled in the business's (INVENTORY-F30: in English when it is not
    Spanish)."""
    language = business_language(ctx)
    found = image_library(ctx).search(data.query, language, folder=data.folder)
    return {
        "rows": [image.row(language) for image in found[data.offset : data.offset + data.limit]],
        "total": len(found),
        "limit": data.limit,
        "offset": data.offset,
    }


@operation(
    "base.catalog_image.get",
    kind="query",
    permission=VIEW_HOME,
    database=False,
    input=CatalogImageRefIn,
    output=CatalogImageOut,
    ai=AI(
        description=(
            "Says which image of the shared library a reference (catalog:<folder>/<name>) names: its title in the "
            "person's language and where it is served."
        ),
        asks={
            "en": ("which picture is catalog:drinks/espresso?", "what's that library image called?"),
            "es": ("¿qué foto es catalog:bebidas/espresso?", "¿cómo se llama esa imagen de la biblioteca?"),
        },
    ),
)
def catalog_image_get(ctx: OperationContext, data: CatalogImageRefIn) -> dict:
    """What the assistant's card says of an image a write sets (``refers``): its title in the person's language (the
    card's), never the raw reference."""
    from base.images import IMAGE_UNKNOWN

    parsed = image_catalog.parse_reference(data.reference)
    image = image_library(ctx).get(*parsed) if parsed else None
    if image is None:
        with translation.override(ctx.language):
            raise NotFound(str(IMAGE_UNKNOWN), code="base.image_unknown")
    return image.row(ctx.language)

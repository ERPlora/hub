"""The editor: ``website.site.get`` (the draft and what is published), ``website.site.preview`` (the draft
rendered as visitors would see it, with a fresh catalog), ``website.qr.get`` (the QR of the hub's address, or of
that address right at its catalog) and ``website.catalog.categories`` (what its catalog may show); and what the
assistant's card reads to name the images and the categories a save keeps.
"""

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.website import reviews
from apps.website.models import Image, Site
from apps.website.qr import qr_file
from apps.website.queries.catalog import SOURCES, _service_categories, _source_on, read_catalog
from apps.website.render import local_day, render_site
from apps.website.schemas import (
    CategoriesIn,
    CategoriesOut,
    CategoryIn,
    CategoryOut,
    Content,
    ImageIn,
    ImageNameOut,
    ImageRef,
    NoIn,
    PreviewOut,
    QrIn,
    QrOut,
    SiteOut,
    Theme,
)
from base.catalog_groups import product_categories
from base.operations import business_currency, business_name
from base.qr import public_url
from base.registry import hub_by_slug

IMAGE_NOT_FOUND = _("This image was not uploaded to this business's website: upload it again.")
CATEGORY_NOT_FOUND = _("This category is not in Inventory or Services.")

#: The parts of the content that hold one image (the gallery holds a list of them).
IMAGE_FIELDS = (("topbar", "logo"), ("hero", "cover"), ("about", "image"))
#: What the site keeps of its content leaves out each image's name: every read writes it anew from the upload, so what
#: was kept and published before the names were read compares as it always did.
NOT_KEPT = {
    **{section: {field: {"name"}} for section, field in IMAGE_FIELDS},
    "gallery": {"images": {"__all__": {"name"}}},
}


def image_refs(content: Content) -> Iterator[tuple[str, ImageRef]]:
    """Each image the content names, with the path of its field (the 422's key)."""
    for section, field in IMAGE_FIELDS:
        ref = getattr(getattr(content, section), field)
        if ref is not None:
            yield f"content.{section}.{field}", ref
    for index, ref in enumerate(content.gallery.images):
        yield f"content.gallery.images.{index}", ref


def kept(content: Content) -> dict[str, Any]:
    """``content`` as the site keeps it."""
    return content.model_dump(mode="json", exclude=NOT_KEPT)


def current_site() -> Site:
    """The business's saved site, or the factory one (unsaved: classic, empty, never published) while nobody saved it."""
    return Site.objects.first() or Site()


def draft(site: Site) -> dict[str, Any]:
    """The draft as the editor and the publication read it: template, theme and content, validated and complete."""
    return {
        "template": site.template,
        "theme": Theme.model_validate(site.theme or {}).model_dump(),
        "content": kept(Content.model_validate(site.content or {})),
    }


def image_name(image: Image) -> str:
    """The name of the file ``image`` was uploaded with; one uploaded before it was kept, by its format and size («PNG
    1200 × 800»)."""
    kind = image.content_type.rpartition("/")[2].upper()
    return image.filename or f"{kind} {image.width} × {image.height}"


def with_image_names(content: dict[str, Any]) -> dict[str, Any]:
    """``content`` with each image named as the person calls it; one that is no upload of the business, by none."""
    valid = Content.model_validate(content)
    refs = [ref for _path, ref in image_refs(valid)]
    images = Image.objects.in_bulk({ref.id for ref in refs})
    for ref in refs:
        ref.name = image_name(images[ref.id]) if ref.id in images else ""
    return valid.model_dump(mode="json")


def _has_changes(site: Site, now: dict[str, Any]) -> bool:
    """Whether the draft holds something visitors do not see: a saved draft never published, or one that moved on."""
    if site._state.adding:
        return False
    if not site.published_version:
        return True
    return any(site.published_content.get(field) != value for field, value in now.items())


def site_out(ctx: OperationContext, site: Site) -> dict[str, Any]:
    now = draft(site)
    return {
        **now,
        "content": with_image_names(now["content"]),
        "published_version": site.published_version,
        "published_at": site.published_at,
        "is_live": site.is_live,
        "has_changes": _has_changes(site, now),
        "updated_at": site.updated_at,
        "public_url": public_url(ctx.scope.key, ctx.request),
        "reviews": _reviews_status(ctx.scope.key, now["content"], site.reviews_snapshot),
    }


def _reviews_status(slug: str, content: dict, snapshot: dict | None) -> dict[str, Any]:
    """Whether Google's reviews of the draft's place are there (the editor's note), hidden or not."""
    valid = Content.model_validate(content)
    state, payload = reviews.state(slug, valid.reviews.place_ref, list(valid.location.address_lines), snapshot)
    return {
        "state": state,
        "rating": payload.get("rating") if payload else None,
        "count": payload.get("count", 0) if payload else 0,
        "fetched_at": payload.get("fetched_at") if payload else None,
    }


def shown_reviews(slug: str, content: dict, snapshot: dict | None) -> dict | None:
    """Google's reviews ``content``'s page shows, as kept (never asking Google): ``None`` when its section is hidden,
    names no place, or nothing was read for it."""
    valid = Content.model_validate(content)
    if valid.reviews.hidden:
        return None
    return reviews.read(slug, valid.reviews.place_ref, list(valid.location.address_lines), snapshot)


@operation(
    "website.site.get",
    kind="query",
    permission="website.view",
    input=NoIn,
    output=SiteOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me the website",
                "is my web page online?",
                "which version of the website is published?",
            ),
            "es": (
                "¿mi página web ya está en internet?",
                "dime qué pone ahora en la web del negocio",
                "¿la web tiene algo pendiente de publicar?",
            ),
        },
        "description": "The business's website: its template, colours and the content of each section as it is being "
        "edited, which version is published, whether it is online and whether the draft has unpublished changes."
    },
)
def get_site(ctx: OperationContext, data: NoIn) -> dict:
    return site_out(ctx, current_site())


# Not an assistant tool (no ``ai=``): an HTML page for the editor's frame; the assistant reads website.site.get.
# Not an assistant tool: the page as HTML, for the screen's preview.
@operation(
    "website.site.preview",
    kind="query",
    permission="website.manage",
    input=NoIn,
    output=PreviewOut,
    expose_api=True,
    ai=INTERNAL,
)
def preview_site(ctx: OperationContext, data: NoIn) -> dict:
    site = current_site()
    now = draft(site)
    catalog = read_catalog(ctx, Content.model_validate(now["content"]).catalog)
    html = render_site(
        now["template"],
        now["theme"],
        now["content"],
        ctx.language,
        name=business_name(ctx.scope) or ctx.scope.key,
        currency=business_currency(ctx.scope),
        catalog=catalog,
        preview=True,
        today=business_day(ctx.scope),
        reviews=shown_reviews(ctx.scope.key, now["content"], site.reviews_snapshot),
    )
    return {"html": html}


def business_day(scope: Scope) -> str:
    """Today (``mon`` … ``sun``) where ``scope``'s business is: in its hub's time zone, Spain's without one."""
    hub = hub_by_slug(scope.key) if scope.kind == "host" else None
    return local_day(hub.timezone if hub else "")


# Not an assistant tool: an image the screen shows and prints.
@operation(
    "website.qr.get",
    kind="query",
    permission="website.view",
    input=QrIn,
    output=QrOut,
    expose_api=True,
    ai=INTERNAL,
)
def get_qr(ctx: OperationContext, data: QrIn) -> dict:
    return qr_file(ctx.scope.key, ctx.request, data.format, data.target)


@operation(
    "website.catalog.categories",
    kind="query",
    permission="website.manage",
    input=CategoriesIn,
    output=CategoriesOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which categories can the website's catalog show?",
                "what categories can I choose for the catalog on my web page?",
            ),
            "es": (
                "¿qué categorías se pueden enseñar en la página web?",
                "¿qué categorías de servicios puede mostrar el catálogo de la web?",
            ),
        },
        "description": "The categories of Inventory's products or Services' services the website's catalog can show.",
    },
)
def list_categories(ctx: OperationContext, data: CategoriesIn) -> dict:
    if not _source_on(ctx.scope, data.source):
        return {"categories": []}
    reader = replace(ctx, permissions=ctx.permissions | SOURCES[data.source])
    rows = _service_categories(reader) if data.source == "service" else product_categories(reader)
    return {"categories": [{"id": row.id, "name": row.name} for row in rows]}


# What the assistant's card reads to name a record a save keeps (hub#679): no tool, no route, nothing live.


@operation(
    "website.image.get",
    kind="query",
    permission="website.view",
    input=ImageIn,
    output=ImageNameOut,
    expose_api=False,
    ai=INTERNAL,
)
def get_image(ctx: OperationContext, data: ImageIn) -> dict:
    """An image of this business's website by the name of its file; one uploaded before it was kept, by its format and
    size («PNG 1200 × 800»)."""
    image = Image.objects.filter(id=data.id).first()
    if image is None:
        raise NotFound(str(IMAGE_NOT_FOUND), code="website.image_not_found")
    return {"id": image.id, "name": image_name(image)}


@operation(
    "website.category.get",
    kind="query",
    permission="website.manage",
    input=CategoryIn,
    output=CategoryOut,
    expose_api=False,
    ai=INTERNAL,
)
def get_category(ctx: OperationContext, data: CategoryIn) -> dict:
    """A category the catalog can show, by its name: among Inventory's or Services' (the ones on in the business), as
    the editor lists them (``website.catalog.categories``)."""
    for source in SOURCES:
        if not _source_on(ctx.scope, source):
            continue
        reader = replace(ctx, permissions=ctx.permissions | SOURCES[source])
        rows = _service_categories(reader) if source == "service" else product_categories(reader)
        found = next((row for row in rows if row.id == data.id), None)
        if found is not None:
            return {"id": found.id, "name": found.name}
    raise NotFound(str(CATEGORY_NOT_FOUND), code="website.category_not_found")

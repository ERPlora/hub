"""Write operations of the website app: one operation = one transaction, with its event in the outbox.

- ``website.site.save`` keeps the draft (template, theme, content); the images it names must be uploads of this hub,
  and their URLs are written here, never taken from the client.
- ``website.site.publish`` copies the draft to what visitors see, with the catalog's snapshot, under a new version,
  and puts it online; after the COMMIT the previous version's cached page goes.
- ``website.site.unpublish`` takes it offline (``/`` jumps to the login again); publishing again goes on from the
  next version.
- ``website.image.upload`` keeps an image (jpeg, png or webp, 5 MB and 8000 px a side at most, checked with Pillow)
  in the hub file store under its content hash.
- Google's reviews of the reviews section's place (``apps.website.reviews``) are asked after the COMMIT that names a
  new place (a save) or that publishes (what was kept is dropped first), never inside a transaction; the public home
  asks too when nothing is kept (:func:`refresh_reviews`). A fresh answer is kept in the site's row.

Every write acts on the site of the request's hub only (``hub_id``, phase 1: the tables are shared, models.py) and
locks its row first, so two editors never interleave a save and a publication; the first save or publication of a hub
creates its row, and another one at the same moment waits for it rather than failing on the duplicate.
"""

import base64
import binascii
import hashlib
import io
import uuid
from collections.abc import Iterator
from functools import partial
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import InvalidPayload
from live.operations import operation
from live.outbox import record_event
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from apps.website import events, reviews
from apps.website.models import ACTOR_MAX_LENGTH, Image, Site
from apps.website.queries import draft, forget_cached, read_catalog, site_out
from apps.website.schemas import (
    MAX_IMAGE_BYTES,
    Content,
    ImageOut,
    ImageRef,
    ImageUploadIn,
    NoIn,
    PublicationOut,
    SaveIn,
    SiteOut,
)
from apps.website.storage import image_key, image_url
from base.operations import business_currency, hub_id

#: The longest side of an image the website takes, in pixels.
MAX_IMAGE_SIDE = 8000
#: What Pillow calls each type the website takes.
PILLOW_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
#: The parts of the content that hold one image (the gallery holds a list of them).
IMAGE_FIELDS = (("topbar", "logo"), ("hero", "cover"), ("about", "image"))

IMAGE_NOT_FOUND = _("This image was not uploaded to this business's website: upload it again.")
NOT_BASE64 = _("The file did not arrive whole: choose it again.")
EMPTY_FILE = _("The file is empty.")
TOO_HEAVY = _("The image may weigh 5 MB at most.")
NOT_THAT_TYPE = _("This file is not a %(type)s image.")
TOO_LARGE = _("The image may be %(side)s pixels a side at most.")


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH] if ctx.actor is not None else ""


def _locked_site(hub: uuid.UUID) -> tuple[Site, bool]:
    """``hub``'s site, locked until the COMMIT, and whether this call created it.

    ``get_or_create`` first: a first write of the hub at the same moment as this one makes its INSERT wait for the
    other's COMMIT, and then reads the other's row instead of failing on the duplicate."""
    _site, created = Site.objects.get_or_create(hub_id=hub)
    return Site.objects.select_for_update().get(hub_id=hub), created


def _image_refs(content: Content) -> Iterator[tuple[str, ImageRef]]:
    """Each image the content names, with the path of its field (the 422's key)."""
    for section, field in IMAGE_FIELDS:
        ref = getattr(getattr(content, section), field)
        if ref is not None:
            yield f"content.{section}.{field}", ref
    for index, ref in enumerate(content.gallery.images):
        yield f"content.gallery.images.{index}", ref


def _with_image_urls(hub: uuid.UUID, content: Content) -> Content:
    """``content`` with each image's URL written from its upload; 422 for an image that is no upload of ``hub``."""
    refs = list(_image_refs(content))
    keys = dict(Image.objects.filter(hub_id=hub, id__in={ref.id for _path, ref in refs}).values_list("id", "key"))
    refused: dict[str, str] = {}
    for path, ref in refs:
        ref.url = image_url(hub, keys[ref.id]) if ref.id in keys else ""
        if not ref.url:
            refused[path] = str(IMAGE_NOT_FOUND)
    if refused:
        raise InvalidPayload(str(IMAGE_NOT_FOUND), fields=refused)
    return content


@operation(
    "website.site.save",
    kind="command",
    permission="website.manage",
    input=SaveIn,
    output=SiteOut,
    expose_api=True,
    ai={
        "description": "Saves the website's whole draft, which replaces the one kept: read it first with "
        "website.site.get, change only what was asked and send everything back (a section left out goes back to "
        "empty). It holds the template (classic, modern, minimal or bold), the theme (a palette by its id, optionally "
        "with the owner's own primary and accent colours over it in custom, null for the palette's own, and the "
        "page's mode: light, dark or auto) and the content of each section: the top bar's name, the hero's title "
        "and tagline, about us (Markdown text), the catalog's source, the gallery (up to 12 photos already uploaded, "
        "by id, in their order), the Google reviews (the business's Google Maps link or Place ID in place_ref; the "
        "Hub reads the rating and reviews from Google itself), contact (phone, WhatsApp, email, social links and the "
        "opening hours, one row per day with up to three intervals HH:MM-HH:MM), location (address lines and an "
        "https:// map link) and the footer's line; about, catalog, gallery, reviews, contact and location can be "
        "hidden. Visitors see it only once it is published.",
        "risk": "normal",
    },
)
def save_site(ctx: OperationContext, data: SaveIn) -> dict:
    hub = hub_id(ctx.scope)
    site, created = _locked_site(hub)
    content = _with_image_urls(hub, data.content)
    new = {"template": data.template, "theme": data.theme.model_dump(), "content": content.model_dump(mode="json")}
    place = reviews_place(new["content"])
    if place is not None and place != reviews_place(site.content or {}):
        transaction.on_commit(partial(refresh_reviews, ctx.scope, new["content"]), robust=True)
    if created or draft(site) != new:
        site.template, site.theme, site.content = new["template"], new["theme"], new["content"]
        site.updated_by = _actor(ctx)
        site.save()
        record_event(ctx, events.SITE_UPDATED, {"id": str(site.id)})
    return site_out(ctx, site)


@operation(
    "website.site.publish",
    kind="command",
    permission="website.manage",
    input=NoIn,
    output=PublicationOut,
    expose_api=True,
    ai={
        "description": "Publishes the website's draft: from now on, whoever opens the business's address sees it, with "
        "the catalog as it is now.",
        "risk": "normal",
    },
)
def publish_site(ctx: OperationContext, data: NoIn) -> dict:
    hub = hub_id(ctx.scope)
    site, _created = _locked_site(hub)
    now = draft(site)
    content = _with_image_urls(hub, Content.model_validate(now["content"]))
    previous = site.published_version
    site.published_content = {
        **now,
        "content": content.model_dump(mode="json"),
        "catalog": read_catalog(ctx, content.catalog),
    }
    site.published_version = previous + 1
    site.published_at = timezone.now()
    site.is_live = True
    site.updated_by = _actor(ctx)
    site.save()
    record_event(ctx, events.SITE_PUBLISHED, {"id": str(site.id), "version": site.published_version})
    transaction.on_commit(partial(forget_cached, ctx.scope.key, previous, business_currency(ctx.scope)), robust=True)
    transaction.on_commit(partial(refresh_reviews, ctx.scope, site.published_content["content"], again=True), robust=True)
    return _publication(site)


@operation(
    "website.site.unpublish",
    kind="command",
    permission="website.manage",
    input=NoIn,
    output=PublicationOut,
    expose_api=True,
    ai={
        "description": "Takes the website offline: the business's address goes back to the team's sign-in page until "
        "it is published again. Nothing is lost.",
        "risk": "normal",
    },
)
def unpublish_site(ctx: OperationContext, data: NoIn) -> dict:
    # A hub that never saved its site has nothing online: no row is created for it.
    hub = hub_id(ctx.scope)
    site = Site.objects.select_for_update().filter(hub_id=hub).first() or Site(hub_id=hub)
    if site.is_live:
        site.is_live = False
        site.updated_by = _actor(ctx)
        site.save()
        record_event(ctx, events.SITE_UNPUBLISHED, {"id": str(site.id), "version": site.published_version})
        transaction.on_commit(
            partial(forget_cached, ctx.scope.key, site.published_version, business_currency(ctx.scope)), robust=True
        )
    return _publication(site)


# Google's reviews


def reviews_place(content: dict) -> tuple[str, list[str]] | None:
    """The reviews section's place in ``content`` (the owner's input and the address it is searched with), or
    ``None`` when the section is hidden or names none."""
    valid = Content.model_validate(content)
    if valid.reviews.hidden or not valid.reviews.place_ref:
        return None
    return valid.reviews.place_ref, list(valid.location.address_lines)


def refresh_reviews(scope: Scope, content: dict, *, again: bool = False) -> dict | None:
    """Google's reviews of ``content``'s place on ``scope``'s hub: those kept, or asked now when nothing is (``again``:
    what is kept is dropped first). Never inside a transaction: after a COMMIT, or from the public home. A fresh
    answer is kept in the site's row too, so a flushed cache or a later failure still shows it."""
    place = reviews_place(content)
    if place is None:
        return None
    ref, address = place
    if again:
        reviews.forget(scope.key, ref, address)
    asked = reviews.cached(scope.key, ref, address) is None
    payload = reviews.load(scope.key, ref, address)
    if asked and payload is not None:
        Site.objects.filter(hub_id=hub_id(scope)).update(reviews_snapshot=payload)
    return payload


def _publication(site: Site) -> dict[str, Any]:
    return {"published_version": site.published_version, "published_at": site.published_at, "is_live": site.is_live}


# Images


def _refuse_file(message: str) -> InvalidPayload:
    return InvalidPayload(message, fields={"data_base64": message})


def _decoded(data: ImageUploadIn) -> bytes:
    try:
        raw = base64.b64decode(data.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise _refuse_file(str(NOT_BASE64)) from None
    if not raw:
        raise _refuse_file(str(EMPTY_FILE))
    if len(raw) > MAX_IMAGE_BYTES:
        raise _refuse_file(str(TOO_HEAVY))
    return raw


def _measured(raw: bytes, content_type: str) -> tuple[int, int]:
    """The image's width and height, once Pillow read it whole as the type it claims to be."""
    not_that_type = str(NOT_THAT_TYPE) % {"type": PILLOW_FORMATS[content_type]}
    try:
        with PILImage.open(io.BytesIO(raw)) as image:
            image_format, (width, height) = image.format, image.size
            if image_format != PILLOW_FORMATS[content_type]:
                raise _refuse_file(not_that_type)
            if max(width, height) > MAX_IMAGE_SIDE:
                raise _refuse_file(str(TOO_LARGE) % {"side": MAX_IMAGE_SIDE})
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, PILImage.DecompressionBombError):
        raise _refuse_file(not_that_type) from None
    return width, height


# Not an assistant tool (no ``ai=``): it takes the file in base64, up to 5 MB; the editor uploads it.
@operation(
    "website.image.upload",
    kind="command",
    permission="website.manage",
    input=ImageUploadIn,
    output=ImageOut,
    expose_api=True,
)
def upload_image(ctx: OperationContext, data: ImageUploadIn) -> dict:
    hub = hub_id(ctx.scope)
    raw = _decoded(data)
    width, height = _measured(raw, data.content_type)
    sha = hashlib.sha256(raw).hexdigest()
    key = image_key(hub, sha, data.content_type)
    image = Image.objects.filter(key=key, hub_id=hub).first()
    if image is None:
        try:
            with transaction.atomic():
                image = Image.objects.create(
                    hub_id=hub,
                    key=key,
                    sha256=sha,
                    content_type=data.content_type,
                    width=width,
                    height=height,
                    size=len(raw),
                )
        except IntegrityError:
            # The same file, uploaded at the same moment by someone else: theirs is ours.
            image = Image.objects.get(key=key, hub_id=hub)
    store = storages["hub_files"]
    if not store.exists(key):
        store.save(key, ContentFile(raw))
    record_event(ctx, events.IMAGE_UPLOADED, {"id": str(image.id)})
    return {
        "id": image.id,
        "url": image_url(hub, image.key),
        "content_type": image.content_type,
        "width": image.width,
        "height": image.height,
        "size": image.size,
    }

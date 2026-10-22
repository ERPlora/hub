"""Read operations of the website app (``READ ONLY``) and the helpers its writes and its public home share.

- **The editor**: ``website.site.get`` (the draft and what is published), ``website.site.preview`` (the draft
  rendered as visitors would see it, with a fresh catalog) and ``website.qr.get`` (the QR of the hub's address).
- **The public reads** (no session, ``permission=None``): ``website.public.site``, ``website.public.catalog`` and
  ``website.public.reviews`` answer only while the module is on in the hub (404 ``app_inactive`` otherwise) and the hub's own site is published
  and live (404 ``website.not_published`` otherwise), the same guard ``/`` applies (``public_home.is_published``,
  through :func:`live_version`), and count each visitor (``base.throttle``: 60 a minute per hub and address, then
  429 ``base.rate_limited``). The catalog is read live and kept a minute per hub, version and language; the reviews
  are those kept (``apps.website.reviews``: a read never asks Google).
- **The catalog** (``read_catalog``): Inventory's products on sale or Services' offered services, read by their
  operations' names with a context that may read them (as ``apps.flow`` does), only while that app is on in the hub
  (``base.relay.active_apps``, the website's own guard); an app that is off or not there leaves the catalog empty,
  never an error.
- ``published_page`` and ``live_version`` are what ``public_home`` reads; ``page_cache_key`` and
  ``catalog_cache_key`` name what is cached, and ``forget_cached`` drops a version's entries.

Every read is of the request hub's own row (``hub_id``; phase 1: the tables are shared, models.py).
"""

import base64
import uuid
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, QuerySet
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import AppInactive, NotFound
from live.operations import get, operation, registry

from apps.website import reviews
from apps.website.models import Site
from apps.website.qr import CONTENT_TYPES, public_url, qr_image
from apps.website.render import BODY_SECTIONS, catalog_view, local_day, render_site, reviews_view
from apps.website.schemas import (
    DAYS,
    CatalogOut,
    CatalogSection,
    CategoriesIn,
    CategoriesOut,
    Content,
    NoIn,
    PreviewOut,
    PublicSiteOut,
    QrIn,
    ReviewsOut,
    QrOut,
    SiteOut,
    Theme,
)
from base import relay
from base.operations import hub_id
from base.registry import hub_by_slug
from base.throttle import RateLimited, allow, client_address

#: The app's label: what ``base.relay.active_apps`` names when the module is on in a hub.
WEBSITE = "website"
NOT_PUBLISHED = _("This website is not published.")
MODULE_OFF = _("The website is not on in this business.")
#: The public reads a visitor may make per hub and address in a window.
PUBLIC_LIMIT = 60
PUBLIC_WINDOW = 60
#: How long the public catalog is kept, in seconds (the bundle refreshes it on every visit).
CATALOG_TTL = 60
#: How long a rendered page is kept, in seconds (a publication changes its key: no stale read).
PAGE_TTL = 3600
#: The most items a catalog shows (and reads).
MAX_ITEMS = 200
#: The page size of the other apps' lists.
PAGE = 100
#: Each source (its app's label) and what the delegated context may read of it.
SOURCES = {
    "service": frozenset({"service.view_service", "service.view_category"}),
    "inventory": frozenset({"inventory.view_product", "inventory.view_category"}),
}
#: A site visitors see: published at least once and online.
LIVE = Q(is_live=True, published_version__gt=0)
#: How Services' pricing reads on the page.
SERVICE_PRICE_KINDS = {"fixed": "fixed", "from": "from", "hourly": "hourly", "free": "free", "variable": "none"}


# The site


def current_site(hub: uuid.UUID) -> Site:
    """``hub``'s saved site, or the factory one (unsaved: classic, empty, never published) while nobody saved it."""
    return Site.objects.filter(hub_id=hub).first() or Site(hub_id=hub)


def draft(site: Site) -> dict[str, Any]:
    """The draft as the editor and the publication read it: template, theme and content, validated and complete."""
    return {
        "template": site.template,
        "theme": Theme.model_validate(site.theme or {}).model_dump(),
        "content": Content.model_validate(site.content or {}).model_dump(mode="json"),
    }


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
        "description": "The business's website: its template, colours and the content of each section as it is being "
        "edited, which version is published, whether it is online and whether the draft has unpublished changes."
    },
)
def get_site(ctx: OperationContext, data: NoIn) -> dict:
    return site_out(ctx, current_site(hub_id(ctx.scope)))


# Not an assistant tool (no ``ai=``): an HTML page for the editor's frame; the assistant reads website.site.get.
@operation(
    "website.site.preview",
    kind="query",
    permission="website.manage",
    input=NoIn,
    output=PreviewOut,
    expose_api=True,
)
def preview_site(ctx: OperationContext, data: NoIn) -> dict:
    site = current_site(hub_id(ctx.scope))
    now = draft(site)
    catalog = read_catalog(ctx, Content.model_validate(now["content"]).catalog)
    html = render_site(
        now["template"],
        now["theme"],
        now["content"],
        ctx.language,
        hub=ctx.scope.key,
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


# Not an assistant tool (no ``ai=``): its answer is an image in base64; the editor downloads it.
@operation(
    "website.qr.get",
    kind="query",
    permission="website.view",
    input=QrIn,
    output=QrOut,
    expose_api=True,
)
def get_qr(ctx: OperationContext, data: QrIn) -> dict:
    url = public_url(ctx.scope.key, ctx.request)
    return {
        "format": data.format,
        "url": url,
        "content_type": CONTENT_TYPES[data.format],
        "filename": f"website-qr-{ctx.scope.key}.{data.format}",
        "content_base64": base64.b64encode(qr_image(url, data.format)).decode("ascii"),
    }


@operation(
    "website.catalog.categories",
    kind="query",
    permission="website.manage",
    input=CategoriesIn,
    output=CategoriesOut,
    expose_api=True,
    ai={"description": "The categories of Inventory's products or Services' services the website's catalog can show."},
)
def list_categories(ctx: OperationContext, data: CategoriesIn) -> dict:
    if not _source_on(ctx.scope, data.source):
        return {"categories": []}
    reader = replace(ctx, permissions=ctx.permissions | SOURCES[data.source])
    rows = _service_categories(reader) if data.source == "service" else _product_categories(reader)
    return {"categories": [{"id": row.id, "name": row.name} for row in rows]}


# The public reads


def _count_visitor(ctx: OperationContext) -> None:
    """One more public read of this visitor on this hub; 429 past the limit. Without a request (the platform), free."""
    if ctx.request is None:
        return
    key = f"website:public:{ctx.scope.key}:{client_address(ctx.request)}"
    if not allow(key, limit=PUBLIC_LIMIT, window=PUBLIC_WINDOW):
        raise RateLimited()


def _live(scope: Scope) -> QuerySet[Site]:
    """The live publication of ``scope``'s hub: the one guard of every public path, the API's reads and ``/``.

    404 ``app_inactive`` while the module is off in the hub (phase 1: every installed app is on,
    ``base.relay.active_apps``; phase 2: the hub's activation), 404 for a scope that is no hub; then only that hub's
    row, and only while it is published and online."""
    if WEBSITE not in relay.active_apps(scope):
        raise AppInactive(str(MODULE_OFF))
    return Site.objects.filter(LIVE, hub_id=hub_id(scope))


def _live_site(scope: Scope) -> Site:
    site = _live(scope).first()
    if site is None:
        raise NotFound(str(NOT_PUBLISHED), code="website.not_published")
    return site


def published_page(scope: Scope) -> dict[str, Any] | None:
    """What the public home paints: ``scope``'s live publication (version, template, theme, content, catalog), or
    ``None`` when its visitors see none."""
    try:
        site = _live(scope).first()
    except AppInactive, NotFound:
        return None
    if site is None:
        return None
    return {
        **site.published_content,
        "version": site.published_version,
        "published_at": site.published_at,
        "reviews_snapshot": site.reviews_snapshot,
    }


def live_version(scope: Scope) -> int:
    """The version of ``scope``'s live publication, or 0 when its visitors see none (the public home's cheap check)."""
    try:
        return _live(scope).values_list("published_version", flat=True).first() or 0
    except AppInactive, NotFound:
        return 0


def _without_hidden(content: dict) -> dict:
    """``content`` with each hidden section back to its defaults (still hidden): nothing hidden leaves the Hub."""
    valid = Content.model_validate(content)
    for name in BODY_SECTIONS:
        if getattr(valid, name).hidden:
            setattr(valid, name, type(getattr(valid, name))(hidden=True))
    return valid.model_dump(mode="json")


# The visitors' anonymous reads are no assistant tools (no ``ai=``): the team's assistant reads website.site.get.
@operation(
    "website.public.site",
    kind="query",
    permission=None,
    input=NoIn,
    output=PublicSiteOut,
    expose_api=True,
)
def public_site(ctx: OperationContext, data: NoIn) -> dict:
    _count_visitor(ctx)
    site = _live_site(ctx.scope)
    published = site.published_content
    return {
        "version": site.published_version,
        "published_at": site.published_at,
        "template": published["template"],
        "theme": published["theme"],
        "content": _without_hidden(published["content"]),
    }


@operation(
    "website.public.catalog",
    kind="query",
    permission=None,
    input=NoIn,
    output=CatalogOut,
    expose_api=True,
)
def public_catalog(ctx: OperationContext, data: NoIn) -> dict:
    _count_visitor(ctx)
    site = _live_site(ctx.scope)
    key = catalog_cache_key(ctx.scope.key, site.published_version, ctx.language)
    cached = cache.get(key)
    if cached is not None:
        return cached
    section = Content.model_validate(site.published_content["content"]).catalog
    if section.hidden:
        section = CatalogSection(hidden=True)
    with translation.override(ctx.language):
        view = catalog_view(read_catalog(ctx, section)) or {"source": None, "show_prices": True, "groups": []}
    cache.set(key, view, CATALOG_TTL)
    return view


@operation(
    "website.public.reviews",
    kind="query",
    permission=None,
    input=NoIn,
    output=ReviewsOut,
    expose_api=True,
)
def public_reviews(ctx: OperationContext, data: NoIn) -> dict:
    _count_visitor(ctx)
    site = _live_site(ctx.scope)
    payload = shown_reviews(ctx.scope.key, site.published_content["content"], site.reviews_snapshot)
    with translation.override(ctx.language):
        view = reviews_view(payload)
    return {"available": True, **view} if view else {"available": False}


# The cache


def page_cache_key(slug: str, version: int, lang: str, day: str) -> str:
    """The rendered page of ``slug``'s publication ``version`` in ``lang`` on ``day`` (the opening hours mark today),
    for this deploy's bundle."""
    return f"website:home:{slug}:{version}:{lang}:{day}:{settings.APP_VERSION}"


def catalog_cache_key(slug: str, version: int, lang: str) -> str:
    return f"website:catalog:{slug}:{version}:{lang}"


def forget_cached(slug: str, version: int) -> None:
    """Drop the page and the catalog of ``slug``'s publication ``version`` in every language and on every day (after a
    COMMIT)."""
    languages = [code for code, _name in settings.LANGUAGES]
    cache.delete_many(
        [page_cache_key(slug, version, lang, day) for lang in languages for day in DAYS]
        + [catalog_cache_key(slug, version, lang) for lang in languages]
    )


# The catalog, from the other apps


def read_catalog(ctx: OperationContext, section: CatalogSection) -> dict[str, Any]:
    """The snapshot of ``section``'s source: ``{source, show_prices, groups: [{name, items}]}``.

    Read by the source's operations with ``ctx`` allowed to read it (and nothing else); empty when the section has
    no source or the source's app is not on in the hub.
    """
    snapshot: dict[str, Any] = {"source": section.source, "show_prices": section.show_prices, "groups": []}
    if section.source is None or not _source_on(ctx.scope, section.source):
        return snapshot
    reader = replace(ctx, permissions=ctx.permissions | SOURCES[section.source])
    wanted = {str(category_id) for category_id in section.category_ids}
    groups = _service_groups(reader) if section.source == "service" else _product_groups(reader)
    snapshot["groups"] = [
        {"name": name, "items": items}
        for category_id, name, items in groups
        if items and (not wanted or category_id in wanted)
    ]
    return snapshot


def _source_on(scope: Scope, source: str) -> bool:
    """Whether the catalog's ``source`` (an app's label) is on in ``scope``'s hub, as the website's own guard asks."""
    return source in relay.active_apps(scope)


def _rows(ctx: OperationContext, name: str, limit: int = MAX_ITEMS, **params: Any) -> Iterator[Any]:
    """Every row of the list operation ``name`` (page by page), up to ``limit``."""
    if name not in registry:
        return
    op = get(name)
    offset = 0
    while offset < limit:
        page = op(ctx, op.input(limit=min(PAGE, limit - offset), offset=offset, **params))
        yield from page.rows
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


def _service_categories(ctx: OperationContext) -> list[Any]:
    return list(_rows(ctx, "service.category.list", sort="sort_order"))


def _product_categories(ctx: OperationContext) -> list[Any]:
    return sorted(_rows(ctx, "inventory.category.list"), key=lambda row: (row.order, row.name.lower()))


def _service_groups(ctx: OperationContext) -> list[tuple[str, str, list[dict]]]:
    """Services' offered services by category, in the categories' order; those without one last."""
    order = {str(row.id): position for position, row in enumerate(_service_categories(ctx))}
    grouped: dict[str, tuple[str, list[dict]]] = {}
    for row in _rows(ctx, "service.service.list_for_sale"):
        category_id = str(row.category_id) if row.category_id else ""
        kind = SERVICE_PRICE_KINDS.get(row.pricing_type, "none")
        item = {"name": row.name, "price": row.price, "price_kind": kind, "minutes": row.duration_minutes}
        grouped.setdefault(category_id, (row.category_name or "", []))[1].append(item)
    return _ordered(grouped, order)


def _product_groups(ctx: OperationContext) -> list[tuple[str, str, list[dict]]]:
    """Inventory's products on sale under each of their categories, in the categories' order; those without one last."""
    categories = _product_categories(ctx)
    order = {str(row.id): position for position, row in enumerate(categories)}
    names = {str(row.id): row.name for row in categories}
    links: dict[str, list[str]] = {}
    for link in _rows(ctx, "inventory.product_category.list", limit=MAX_ITEMS * 5):
        links.setdefault(str(link.product_id), []).append(str(link.category_id))
    grouped: dict[str, tuple[str, list[dict]]] = {}
    for row in _rows(ctx, "inventory.product.list_for_sale"):
        item = {"name": row.name, "price": row.price, "price_kind": "fixed" if row.price else "none", "minutes": None}
        for category_id in [cid for cid in links.get(str(row.id), []) if cid in names] or [""]:
            grouped.setdefault(category_id, (names.get(category_id, ""), []))[1].append(item)
    return _ordered(grouped, order)


def _ordered(grouped: dict[str, tuple[str, list[dict]]], order: dict[str, int]) -> list[tuple[str, str, list[dict]]]:
    """The groups in their categories' order; one whose category is unknown (none, or past the list) last."""
    ranked = sorted(grouped.items(), key=lambda entry: (entry[0] == "", order.get(entry[0], len(order)), entry[1][0]))
    return [(category_id, name, items) for category_id, (name, items) in ranked]

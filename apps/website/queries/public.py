"""The public reads (no session, ``permission=None``): ``website.public.site``, ``website.public.catalog`` and
``website.public.reviews`` answer only while the module is on in the hub (404 ``app_inactive`` otherwise) and the
hub's own site is published and live (404 ``website.not_published`` otherwise), the same guard ``/`` applies
(``public_home.is_published``, through :func:`live_version`), and count each visitor (``base.throttle``: 60 a minute
per hub and address, then 429 ``base.rate_limited``). The catalog is read live and kept a minute per hub, version,
language and currency; the reviews are those kept (``apps.website.reviews``: a read never asks Google).

``published_page`` and ``live_version`` are what ``public_home`` reads; ``page_cache_key`` and ``catalog_cache_key``
name what is cached, and ``forget_cached`` drops a version's entries.

The prices are in the business's currency, asked of ``base`` (``base.operations.business_currency``, BASE-F50) when
they are painted, never kept with the snapshot: it is in every key of what is cached, so a business whose country
(hence its currency) changes on erplora.com is never shown the old one until an entry expires.
"""

from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q, QuerySet
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope, system_context
from live.errors import AppInactive, NotFound
from live.operations import INTERNAL, operation

from apps.website.models import Site
from apps.website.queries.catalog import read_catalog
from apps.website.queries.editor import shown_reviews
from apps.website.render import BODY_SECTIONS, catalog_view, reviews_view
from apps.website.schemas import DAYS, CatalogOut, CatalogSection, Content, NoIn, PublicSiteOut, ReviewsOut
from base.apps_on import active_apps
from base.operations import business_currency
from base.throttle import RateLimited, allow, client_address

#: The app's label: what ``base.apps_on.active_apps`` names when the module is on in a hub.
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
#: A site visitors see: published at least once and online.
LIVE = Q(is_live=True, published_version__gt=0)


def _count_visitor(ctx: OperationContext) -> None:
    """One more public read of this visitor on this hub; 429 past the limit. Without a request (the platform), free."""
    if ctx.request is None:
        return
    key = f"website:public:{ctx.scope.key}:{client_address(ctx.request)}"
    if not allow(key, limit=PUBLIC_LIMIT, window=PUBLIC_WINDOW):
        raise RateLimited()


def _live(scope: Scope) -> QuerySet[Site]:
    """The live publication of ``scope``'s hub: the one guard of every public path, the API's reads and ``/``.

    404 ``app_inactive`` while the module is off in the hub (``base.apps_on.active_apps``); then its site, and only
    while it is published and online."""
    if WEBSITE not in active_apps(scope):
        raise AppInactive(str(MODULE_OFF))
    return Site.objects.filter(LIVE)


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
# Not an assistant tool: the public website's read, for its visitors.
@operation(
    "website.public.site",
    kind="query",
    permission=None,
    input=NoIn,
    output=PublicSiteOut,
    expose_api=True,
    ai=INTERNAL,
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


# Not an assistant tool: the public website's read, for its visitors.
@operation(
    "website.public.catalog",
    kind="query",
    permission=None,
    input=NoIn,
    output=CatalogOut,
    expose_api=True,
    ai=INTERNAL,
)
def public_catalog(ctx: OperationContext, data: NoIn) -> dict:
    _count_visitor(ctx)
    site = _live_site(ctx.scope)
    currency = business_currency(ctx.scope)
    key = catalog_cache_key(ctx.scope.key, site.published_version, ctx.language, currency)
    cached = cache.get(key)
    if cached is not None:
        return cached
    with translation.override(ctx.language):
        view = catalog_view(_published_catalog(ctx, site.published_content["content"]), currency) or {
            "source": None,
            "show_prices": True,
            "groups": [],
        }
    cache.set(key, view, CATALOG_TTL)
    return view


def _published_catalog(ctx: OperationContext, content: dict) -> dict[str, Any]:
    """What the catalog of the published ``content`` shows now: a hidden one, nothing."""
    section = Content.model_validate(content).catalog
    return read_catalog(ctx, CatalogSection(hidden=True) if section.hidden else section)


def live_catalog(scope: Scope, content: dict) -> dict[str, Any]:
    """What the catalog of the published ``content`` shows now, for a page that nothing refreshes (``public_home``)."""
    return _published_catalog(system_context(scope), content)


# Not an assistant tool: the public website's read, for its visitors.
@operation(
    "website.public.reviews",
    kind="query",
    permission=None,
    input=NoIn,
    output=ReviewsOut,
    expose_api=True,
    ai=INTERNAL,
)
def public_reviews(ctx: OperationContext, data: NoIn) -> dict:
    _count_visitor(ctx)
    site = _live_site(ctx.scope)
    payload = shown_reviews(ctx.scope.key, site.published_content["content"], site.reviews_snapshot)
    with translation.override(ctx.language):
        view = reviews_view(payload)
    return {"available": True, **view} if view else {"available": False}


# The cache


def page_cache_key(slug: str, version: int, lang: str, day: str, currency: str, *, own_domain: bool = False) -> str:  # noqa: PLR0913
    """The rendered page of ``slug``'s publication ``version`` in ``lang`` on ``day`` (the opening hours mark today),
    priced in ``currency`` (the business's), for this deploy's bundle; ``own_domain``, the page painted for its own
    domain, which is another page (``public_home``).

    The slug is the hash tag (``{<slug>}``) of the page's and the catalog's keys: :func:`forget_cached` drops them in
    one call, which the Valkey cluster accepts only for keys of one slot (``base/cache.py``)."""
    where = ":own-domain" if own_domain else ""
    return f"website:home:{{{slug}}}:{version}:{lang}:{day}:{currency}:{settings.APP_VERSION}{where}"


def catalog_cache_key(slug: str, version: int, lang: str, currency: str) -> str:
    return f"website:catalog:{{{slug}}}:{version}:{lang}:{currency}"


def forget_cached(slug: str, version: int, currency: str) -> None:
    """Drop the page and the catalog of ``slug``'s publication ``version`` priced in ``currency`` (the business's) in
    every language and on every day (after a COMMIT). What was kept in another currency, before the business's
    country changed, is never read again (its key names that currency) and expires."""
    languages = [code for code, _name in settings.LANGUAGES]
    cache.delete_many(
        [
            page_cache_key(slug, version, lang, day, currency, own_domain=own_domain)
            for lang in languages
            for day in DAYS
            for own_domain in (False, True)
        ]
        + [catalog_cache_key(slug, version, lang, currency) for lang in languages]
    )

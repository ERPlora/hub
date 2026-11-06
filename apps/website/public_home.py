"""The website's side of ``base.public_home``: ``/`` of a hub whose site is published, for a visitor without a session.

``base`` loads this module only when ``apps.website`` is installed and calls :func:`is_published` (once per request)
and, if it says so, :func:`respond`. The page is :func:`apps.website.render.render_site` of the live publication, in
the language the visitor's browser asks for (``Accept-Language`` only, never a cookie), kept in the cache under the
hub, the publication's version, the language, the business's day (the opening hours mark today, in the hub's time
zone), the business's currency (its prices': its country's, ``base.business.currency_of`` of the registry row the host
loaded, what ``base.business.get`` answers, with no transaction of its own per visitor) and the deploy
(``queries.page_cache_key``, an hour): a publication or a new country changes the key, so a stale page is never
served. The response sets no cookie, carries the public CSP
(``csp.public_policy``: no nonce) and may be kept a minute by the browser, varying on ``Accept-Language`` and on
``Cookie``: «Sign in» comes back to ``/`` with a session, which must get the shell, never the page kept for the
visitor. Only the hub's own site is shown, under the same guard as the public API (``queries.live_version``). Google's
reviews are asked when the page is rendered and nothing is kept for its place (``services.refresh_reviews``; a failure
is kept 10 minutes and the site's last good answer shows meanwhile).

On the business's own domain (HUBS-F17, ``request.custom_domain``) only the page and its images are there, neither
``/auth`` nor ``/api``, so it is another page, kept apart: «Log in» goes to the business's own address, the page's script
asks nothing of the API (``data-ep-static``), so its catalog is read when it is painted and it is kept what the API keeps
that catalog, a minute, and it names no address for its reports. With nothing to show it is not found: there is no
sign-in to send a visitor to.

On both addresses the page tells search engines which one is its main address (``rel="canonical"``, hub#818): the
business's own domain while the door opens its website there, else its address on erplora.com. There is no redirect:
the erplora.com address is still the team's way in. A page is kept with the main address it names, and one kept before
the domain changed is painted again, so it never names the address of before.
"""

from django.core.cache import cache
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.cache import patch_vary_headers
from django.utils.translation import get_supported_language_variant
from django.utils.translation.trans_real import parse_accept_lang_header
from live.context import Scope

from apps.website import queries, services
from apps.website.csp import own_domain_policy, public_policy
from apps.website.qr import public_url
from apps.website.render import local_day, render_site
from base import custom_domains
from base.business import currency_of

#: What the browser may keep the page for: a minute, then it asks again (and the Hub answers from its cache).
CACHE_CONTROL = "public, max-age=60"
#: Where a visitor goes if the site went offline between the check and the page: the team's sign-in.
OFFLINE_FALLBACK = "/auth/login"


def _scope(hub) -> Scope:
    """The scope of ``hub``'s host, as ``base.operations`` builds it for a request on it."""
    return Scope("host", hub.slug)


def is_published(hub) -> bool:
    """Whether ``hub``'s visitors see its site: the module on there and a live publication of its own."""
    return queries.live_version(_scope(hub)) > 0


def respond(request: HttpRequest) -> HttpResponse:
    """The live publication's page for ``request.hub``, from the cache or rendered once."""
    slug, scope = request.hub.slug, _scope(request.hub)
    own_domain = bool(getattr(request, "custom_domain", ""))
    language, today = visitor_language(request), local_day(request.hub.timezone)
    currency = currency_of(request.hub.country)
    version = queries.live_version(scope)
    main = main_address(request.hub)
    html = _kept(queries.page_cache_key(slug, version, language, today, currency, own_domain=own_domain), main)
    if html is None:
        page = queries.published_page(scope)
        if page is None:
            if own_domain:
                raise Http404("This business has no website to show.")
            return HttpResponseRedirect(OFFLINE_FALLBACK)
        # Google is asked here only when nothing is kept for the place (at most 5 s a call); then what is kept.
        services.refresh_reviews(scope, page["content"])
        html = render_site(
            page["template"],
            page["theme"],
            page["content"],
            language,
            hub=slug,
            currency=currency,
            catalog=queries.live_catalog(scope, page["content"]) if own_domain else page.get("catalog"),
            today=today,
            reviews=queries.shown_reviews(slug, page["content"], page.get("reviews_snapshot")),
            hub_address=public_url(slug) if own_domain else "",
            canonical=main,
        )
        cache.set(
            queries.page_cache_key(slug, page["version"], language, today, currency, own_domain=own_domain),
            {"main": main, "html": html},
            queries.CATALOG_TTL if own_domain else queries.PAGE_TTL,
        )
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = CACHE_CONTROL
    patch_vary_headers(response, ["Accept-Language", "Cookie"])
    response._csp_config = own_domain_policy() if own_domain else public_policy()
    return response


def main_address(hub) -> str:
    """The address ``hub``'s page tells search engines is its main one: its own domain while the door opens its website
    there (``base.custom_domains.served_on``), else its address on erplora.com."""
    domain = custom_domains.served_on(hub)
    return f"https://{domain}/" if domain else public_url(hub.slug)


def _kept(key: str, main: str) -> str | None:
    """The page kept under ``key`` if it names ``main`` as its main address; one kept before the domain changed is not."""
    kept = cache.get(key)
    return kept["html"] if kept is not None and kept["main"] == main else None


def visitor_language(request: HttpRequest) -> str:
    """The first language of ``Accept-Language`` the Hub speaks, or its source language."""
    for code, _quality in parse_accept_lang_header(request.headers.get("Accept-Language", "")):
        if code == "*":
            continue
        try:
            return get_supported_language_variant(code)
        except LookupError:
            continue
    return get_supported_language_variant("en")

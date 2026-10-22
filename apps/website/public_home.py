"""The website's side of ``base.public_home``: ``/`` of a hub whose site is published, for a visitor without a session.

``base`` loads this module only when ``apps.website`` is installed and calls :func:`is_published` (once per request)
and, if it says so, :func:`respond`. The page is :func:`apps.website.render.render_site` of the live publication, in
the language the visitor's browser asks for (``Accept-Language`` only, never a cookie), kept in the cache under the
hub, the publication's version, the language, the business's day (the opening hours mark today, in the hub's time
zone) and the deploy (``queries.page_cache_key``, an hour): a publication changes the key, so a stale page is never
served. The response sets no cookie, carries the public CSP
(``csp.public_policy``: no nonce) and may be kept a minute by the browser, varying on ``Accept-Language`` and on
``Cookie``: «Sign in» comes back to ``/`` with a session, which must get the shell, never the page kept for the
visitor. Only the hub's own site is shown, under the same guard as the public API (``queries.live_version``).
"""

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.cache import patch_vary_headers
from django.utils.translation import get_supported_language_variant
from django.utils.translation.trans_real import parse_accept_lang_header
from live.context import Scope

from apps.website import queries
from apps.website.csp import public_policy
from apps.website.render import local_day, render_site

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
    language, today = visitor_language(request), local_day(request.hub.timezone)
    html = cache.get(queries.page_cache_key(slug, queries.live_version(scope), language, today))
    if html is None:
        page = queries.published_page(scope)
        if page is None:
            return HttpResponseRedirect(OFFLINE_FALLBACK)
        html = render_site(
            page["template"],
            page["theme"],
            page["content"],
            language,
            hub=slug,
            catalog=page.get("catalog"),
            today=today,
        )
        cache.set(queries.page_cache_key(slug, page["version"], language, today), html, queries.PAGE_TTL)
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = CACHE_CONTROL
    patch_vary_headers(response, ["Accept-Language", "Cookie"])
    response._csp_config = public_policy()
    return response


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

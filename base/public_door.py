"""The hub's public door: the pages an app gives the business's customers, without a session, on the hub's own host
(``/p/<slug>/<page>``, beside the files of ``/p/media`` and ``/p/catalog``).

An app gives a page by naming it in its ``LiveAppConfig``: ``public_pages = {"<page>": "<permission>"}``, its path under
``/p/<slug>/`` and the one permission of its own that whoever opens it holds. A permission of another app's, or one the
app does not declare, opens nothing: the door hands it to anybody. Two views serve a page, only on the host of a
business that has the app on and only when ``<slug>`` is that business's own (``request.hub``, the host gate): the
business is never read from the address, so another's slug is not found.

- ``GET /p/<slug>/<page>``: the SPA's HTML (``base.spa.shell``), whose route of the same path paints the page, with the
  business's money (``public-door``) for its prices: a visitor has no session to ask for it.
- ``POST /p/<slug>/api/<operation>``: an operation of that app asking exactly the page's permission, run in this process
  as nobody signed in, with that permission and nothing else, whoever is signed in. Its input is the JSON body, never the
  query string, which servers log (a customer's personal link travels in it); its answer, the operation's output or the
  API's single error envelope in the visitor's language. Django's CSRF check guards it: the page's HTML set the cookie
  its script sends back.
"""

from dataclasses import dataclass

import pydantic
from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from live.context import OperationContext, Scope
from live.database_cut import retrying
from live.errors import OperationError
from live.meta import all_live_app_configs
from live.ninja import install_error_handlers
from live.operations import Operation, registry
from ninja import NinjaAPI
from ninja.errors import ValidationError

from base import business, spa
from base.activation import off_apps

#: Where an app names its pages without a session, in its ``LiveAppConfig``.
PUBLIC_PAGES = "public_pages"
#: The block of the page's HTML with the business's money.
DOOR_BLOCK_ID = "public-door"

# The hub API's own answer to a failure, for the door's calls: the single envelope, a 422 per field, the visitor's language.
_failures = NinjaAPI(urls_namespace="public-door", docs_url=None, openapi_url=None)
install_error_handlers(_failures)


@dataclass(frozen=True)
class Page:
    """A page an app gives: the app, and the permission whoever opens it holds."""

    app: str
    permission: str


def pages() -> dict[str, Page]:
    """Every page the installed apps give, by its path; one naming a permission that is not its app's own is left out."""
    given = {}
    for config in all_live_app_configs():
        for path, permission in getattr(config, PUBLIC_PAGES, {}).items():
            if permission.startswith(f"{config.label}.") and permission in config.permissions:
                given[path] = Page(config.label, permission)
    return given


@require_safe
def open_page(request: HttpRequest, slug: str, name: str) -> HttpResponse:
    _opened(request, slug, pages().get(name))
    currency = business.currency_of(request.hub.country)
    money = {"currency": currency, "currency_decimals": business.currency_decimals(currency)}
    return spa.shell(request, blocks={DOOR_BLOCK_ID: money})


@never_cache
@require_POST
def call(request: HttpRequest, slug: str, operation: str) -> HttpResponse:
    op = registry.get(operation)
    try:
        page = _opened(request, slug, _page_of(op))
        data = op.input.model_validate_json(request.body or b"{}")
        answer = retrying(request, lambda: op(_visitor(request, page), data))
    except pydantic.ValidationError as invalid:
        # Located in the body, as ninja locates a route's: the envelope names each field by its own name.
        located = [{**error, "loc": ("body", *error["loc"])} for error in invalid.errors()]
        return _failures.on_exception(request, ValidationError(located))
    except (OperationError, Http404) as refused:
        return _failures.on_exception(request, refused)
    return JsonResponse(answer.model_dump(mode="json"))


def _opened(request: HttpRequest, slug: str, page: Page | None) -> Page:
    """``page``, if this host's business is ``slug`` and has the page's app on; else not found."""
    hub = getattr(request, "hub", None)
    if page is None or hub is None or slug != hub.slug or page.app in off_apps(Scope("host", hub.slug)):
        raise Http404("No such page.")
    return page


def _page_of(op: Operation | None) -> Page | None:
    """The page of ``op``'s app whose permission ``op`` asks exactly: the only operations the door runs."""
    if op is None:
        return None
    return next(
        (page for page in pages().values() if op.permission == page.permission and op.name.startswith(f"{page.app}.")),
        None,
    )


def _visitor(request: HttpRequest, page: Page) -> OperationContext:
    """Nobody signed in, holding the page's permission and nothing more, in the host's business. The request goes with
    it: the operation counts its visitor by it."""
    return OperationContext(
        scope=Scope("host", request.hub.slug),
        actor=None,
        permissions=frozenset({page.permission}),
        language=getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE,
        request=request,
    )

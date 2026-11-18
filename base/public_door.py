"""The hub's public door: the pages an app gives the business's customers, without a session, on the hub's own host
(``/p/<slug>/<page>``, beside the files of ``/p/media`` and ``/p/catalog``).

An app gives a page by naming it in its ``LiveAppConfig``: ``public_pages = {"<page>": "<permission>"}``, its path under
``/p/<slug>/`` and the one permission of its own that whoever opens it holds. A permission of another app's, or one the
app does not declare, opens nothing: the door hands it to anybody. Two views serve a page, only on the host of a
business that has the app on and only when ``<slug>`` is that business's own (``request.hub``, the host gate): the
business is never read from the address, so another's slug is not found.

- ``GET /p/<slug>/<page>``: the SPA's HTML (``base.spa.shell``), whose route of the same path paints the page, with the
  business's money (``public-door``) for its prices: a visitor has no session to ask for it.
- ``POST /p/<slug>/api/<operation>``: an operation asking exactly the page's permission (one of that app's), run in
  this process as nobody signed in, with that permission and nothing else, whoever is signed in. Its input is the JSON
  body, never the query string, which servers log (a customer's personal link travels in it); its answer, the
  operation's output or the API's single error envelope in the visitor's language. Django's CSRF check guards it: the
  page's HTML set the cookie its script sends back.
"""

from dataclasses import dataclass

import pydantic
from django.conf import settings
from django.core import checks
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

# The hub API's own answer to a failure, for the door's calls: the single envelope, a 422 per field, in the visitor's
# language.
_failures = NinjaAPI(urls_namespace="public-door", docs_url=None, openapi_url=None)
install_error_handlers(_failures)


@dataclass(frozen=True)
class Page:
    """A page an app gives: the app, and the permission whoever opens it holds."""

    app: str
    permission: str


def pages() -> dict[str, Page]:
    """Every page the installed apps give, by its path; what ``base.E020`` refuses is left out."""
    return {
        path: Page(config.label, permission)
        for config in all_live_app_configs()
        if not _problems(config)
        for path, permission in getattr(config, PUBLIC_PAGES, {}).items()
    }


@checks.register("base")
def check_public_pages(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E020``: an app declares in ``public_pages`` a dict of its pages, each with a permission of its own that
    it declares, and no page another app gives."""
    return [
        checks.Error(
            f"{config.label}'s {PUBLIC_PAGES} {problem}.",
            hint=f'An app gives pages of its own: {PUBLIC_PAGES} = {{"<page>": "<label>.<permission>"}}.',
            obj=config,
            id="base.E020",
        )
        for config in all_live_app_configs()
        for problem in _problems(config)
    ]


def _problems(config) -> list[str]:
    """What is wrong with the pages ``config`` declares (none declared: nothing)."""
    declared = getattr(config, PUBLIC_PAGES, {})
    if not isinstance(declared, dict) or not all(isinstance(item, str) for pair in declared.items() for item in pair):
        return ['is not a dict of "<page>": "<permission>"']
    others = {
        path: other.label
        for other in all_live_app_configs()
        if other is not config and isinstance(getattr(other, PUBLIC_PAGES, {}), dict)
        for path in getattr(other, PUBLIC_PAGES, {})
    }
    problems = [
        f"opens {path!r} with {permission!r}, not a permission of {config.label}'s own"
        for path, permission in declared.items()
        if not permission.startswith(f"{config.label}.") or permission not in config.permissions
    ]
    return problems + [f"gives {path!r}, and {others[path]} gives it too" for path in declared if path in others]


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
    """The page whose permission ``op`` asks exactly: the only operations the door runs."""
    if op is None:
        return None
    return next((page for page in pages().values() if op.permission == page.permission), None)


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

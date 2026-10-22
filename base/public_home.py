"""A hub's public website on ``/`` (round 2026-10-21): what ``base`` knows of the ``website`` module.

On a hub's host, ``/`` is the SPA's route. A visitor without a session who loads it (GET or HEAD) gets the hub's
published website instead of the jump to the SaaS's login, with no cookie at all; staff still enter by the page's
«Sign in» (``/auth/login``). Everything else is as before: a session gets the shell, any other path jumps to the
login, and without the module, or without a published site, ``/`` jumps to the login too. The two hooks are
``base.middleware.SaasLoginRequiredMiddleware`` (it lets ``/`` through) and ``base.spa.spa`` (it hands it to
:func:`respond`).

The contract the module implements, in ``apps/website/public_home.py`` (imported only when ``apps.website`` is
installed, and only on the first request that asks):

- ``is_published(hub: base.models.Hub) -> bool``: whether ``hub`` has a published site. Cheap (it runs on every
  anonymous load of ``/``); it never raises for a hub without a site, it says ``False``.
- ``respond(request: HttpRequest) -> HttpResponse``: the published site's page for ``request.hub`` (the hub the
  host gate left on the request, ``base.middleware.HubHostRequiredMiddleware``). Called only for an anonymous GET or
  HEAD of ``/`` after ``is_published`` said ``True`` on the same request. It sets no cookie and owns its
  ``Cache-Control``, ``Vary`` and CSP.

:func:`website_enabled` asks once per request: the gate and the view share the answer.
"""

from importlib import import_module
from types import ModuleType

from django.apps import apps
from django.http import HttpRequest, HttpResponse

#: The ``INSTALLED_APPS`` entry of the module, and the module that implements the contract above.
WEBSITE_APP = "apps.website"
PROVIDER_MODULE = "apps.website.public_home"
#: Where the answer of :func:`website_enabled` is kept on the request.
_ANSWER_ATTR = "_base_website_enabled"


def _provider() -> ModuleType:
    """The website module's ``public_home`` (imported on first use: ``base`` never imports a module eagerly)."""
    return import_module(PROVIDER_MODULE)


def website_enabled(request: HttpRequest) -> bool:
    """Whether ``request.hub`` has a published website: the module is installed and its provider says so."""
    answer = getattr(request, _ANSWER_ATTR, None)
    if answer is None:
        hub = getattr(request, "hub", None)
        answer = hub is not None and apps.is_installed(WEBSITE_APP) and bool(_provider().is_published(hub))
        setattr(request, _ANSWER_ATTR, answer)
    return answer


def respond(request: HttpRequest) -> HttpResponse:
    """The published website's page for ``request.hub`` (after :func:`website_enabled` said ``True``)."""
    return _provider().respond(request)

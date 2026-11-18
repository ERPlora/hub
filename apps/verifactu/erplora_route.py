"""Which route a business's records go by, and whether it may take ERPlora's, where ERPlora files on its behalf with
its own seal.

The route is worked out, never chosen: with an own certificate loaded and in force, the certificate; without one,
ERPlora's seal. Going live keeps the route of that moment in ``Config.route``, and from then on its production goes by
that one whatever happens to the certificate: what was filed with a seal is cancelled with the same one, and an own
route without its certificate waits instead of falling back to the seal. ERPlora's own hub always files with the seal.

The server's switch (``VERIFACTU_ERPLORA_ROUTE_ENABLED``) closes ERPlora's route to newcomers: asking for or sending
the signed authorisation and going live through it are refused, and only the own certificate takes a business to
production. Nothing that already files with the seal stops: testing (demos included) and a business already live
through it. ERPlora's own hub keeps it.
"""

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from live.context import Scope
from live.errors import Conflict

from apps.verifactu.models import Config, Environment
from base import operations as platform

#: What keeps a business on ERPlora's route from going live while the route is closed to it.
CLOSED = "own_certificate_required"
UNAVAILABLE = _("ERPlora does not file on behalf of businesses for now: file with your own certificate.")
OWN_CERTIFICATE_REQUIRED = _(
    "To go live, upload your own certificate: ERPlora does not file on behalf of businesses for now."
)


def available(scope: Scope | None) -> bool:
    return bool(settings.VERIFACTU_ERPLORA_ROUTE_ENABLED) or (scope is not None and platform.is_platform_hub(scope))


def route_for(config: Config, environment: str, scope: Scope | None, has_certificate: bool) -> str:
    """The route the records of ``environment`` go by: ERPlora's seal on ERPlora's own hub; the route fixed on going
    live for the production of a business already live; otherwise the own certificate while a valid one is uploaded
    (``has_certificate``), and the seal without one."""
    if scope is not None and platform.is_platform_hub(scope):
        return Config.Route.ERPLORA
    if environment == Environment.PRODUCTION and config.environment == Environment.PRODUCTION:
        return config.route
    return Config.Route.OWN if has_certificate else Config.Route.ERPLORA


def closed(config: Config, route: str, scope: Scope | None) -> bool:
    """Whether ``route`` is ERPlora's and closed to ``scope``'s business, which is not live through it yet."""
    return route == Config.Route.ERPLORA and config.environment != Environment.PRODUCTION and not available(scope)


def refuse_unavailable(scope: Scope) -> None:
    if not available(scope):
        raise Conflict(str(UNAVAILABLE), code="verifactu.erplora_route_unavailable")

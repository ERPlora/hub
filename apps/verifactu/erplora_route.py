"""Whether a business may take ERPlora's route, where ERPlora files on its behalf with its own seal.

The server's switch (``VERIFACTU_ERPLORA_ROUTE_ENABLED``) closes it to newcomers: choosing it, asking for or sending
the signed authorisation and going live through it are refused, and only the own certificate takes a business to
production. Nothing that already files with the seal stops: testing (demos included) and a business already live
through it, whose cancellations the AEAT only takes with the seal that filed the record. ERPlora's own hub keeps it.
"""

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from live.context import Scope
from live.errors import Conflict

from apps.verifactu.models import Config
from base import operations as platform

#: What keeps a business on ERPlora's route from going live while the route is closed to it.
CLOSED = "own_certificate_required"
UNAVAILABLE = _("ERPlora does not file on behalf of businesses for now: file with your own certificate.")
OWN_CERTIFICATE_REQUIRED = _(
    "To go live, upload your own certificate and choose it as the sending route: ERPlora does not file on behalf of "
    "businesses for now."
)


def available(scope: Scope) -> bool:
    return bool(settings.VERIFACTU_ERPLORA_ROUTE_ENABLED) or platform.is_platform_hub(scope)


def closed(config: Config, scope: Scope) -> bool:
    """Whether ``config``'s route is ERPlora's and closed to ``scope``'s business."""
    return config.route == Config.Route.ERPLORA and not available(scope)


def refuse_unavailable(scope: Scope) -> None:
    if not available(scope):
        raise Conflict(str(UNAVAILABLE), code="verifactu.erplora_route_unavailable")


def refuse_choosing(config: Config, route: str, scope: Scope) -> None:
    """Refuse moving to ERPlora's route while it is closed; staying on it changes nothing and is no new entry."""
    if route == Config.Route.ERPLORA and config.route != route:
        refuse_unavailable(scope)


def refuse_going_live(config: Config, scope: Scope) -> None:
    if closed(config, scope):
        raise Conflict(str(OWN_CERTIFICATE_REQUIRED), code="verifactu.own_certificate_required")


def live_problem(config: Config, scope: Scope) -> str:
    """What ERPlora's route lacks for ``scope``'s business to go live through it: being open to it, then the
    approved authorisation."""
    if not available(scope):
        return CLOSED
    if config.representation_status != Config.Representation.APPROVED:
        return "representation_not_approved"
    return ""

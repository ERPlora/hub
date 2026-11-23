"""What keeps a business from going live now (VERIFACTU-F08), as ``verifactu.config.go_live`` refuses it: the write
runs it before switching, and the assistant before drawing its card (``verifactu.config.check_go_live``), so a person is
never asked to confirm what the write would refuse after their yes."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.operations import INTERNAL, operation

from apps.verifactu import erplora_route
from apps.verifactu.models import Config, Environment
from apps.verifactu.schemas.config import ConfigOut
from apps.verifactu.schemas.fields import NoInput
from base import operations as platform

from .config import config_out
from .country import refuse_outside_spain
from .reads import VIEW
from .route import ISSUER_MISSING, config_row, going_live_problem, issuer_configured, production_open, route_problem

REPRESENTATION_NOT_APPROVED = _(
    "For ERPlora to file in production, ERPlora still has to approve your signed authorisation."
)
PRODUCTION_CLOSED = _(
    "Going live is not open on this server yet: ERPlora opens it when the real submission is ready."
)
HUB_NOT_ACTIVE = _(
    "Your ERPlora account has a pending payment or is suspended: settle it in your ERPlora account to go live."
)
OWN_CERTIFICATE_UNREADABLE = _(
    "Your own certificate cannot be opened on this server: upload it again in VeriFactu → Configuration → My "
    "certificate."
)
OWN_CERTIFICATE_UNTESTED = _(
    "The AEAT's test environment has not accepted your own certificate yet: it is tried with the next record that "
    "goes out in testing. Issue a sale or an invoice and go live once it is accepted."
)
OWN_CERTIFICATE_REJECTED = _(
    "The AEAT's test environment refused your own certificate: upload another one in VeriFactu → Configuration → My "
    "certificate."
)
GATEWAY_UNAVAILABLE = _(
    "ERPlora's sending gateway is not configured on this server: nothing could reach the AEAT."
)
GO_LIVE_FORBIDDEN = _(
    "A demo business cannot go live: it always files in the AEAT's test environment."
)
PLATFORM_FIXED = _(
    "ERPlora's own business files in the AEAT environment of its server: its environment cannot be switched."
)

#: What keeps the route of that moment from filing in production, as the refusal going live raises (VERIFACTU-F04,
#: F08). A closed server is not the route's: it is refused first.
_ROUTE_REFUSALS = {
    "own_certificate_unreadable": OWN_CERTIFICATE_UNREADABLE,
    "own_certificate_untested": OWN_CERTIFICATE_UNTESTED,
    "own_certificate_rejected": OWN_CERTIFICATE_REJECTED,
    "gateway_unavailable": GATEWAY_UNAVAILABLE,
    "representation_not_approved": REPRESENTATION_NOT_APPROVED,
    erplora_route.CLOSED: erplora_route.OWN_CERTIFICATE_REQUIRED,
}


def _route_refusal(config: Config, scope: Scope) -> Conflict | None:
    problem = route_problem(config, Environment.PRODUCTION, scope) or going_live_problem(config, scope)
    if problem not in _ROUTE_REFUSALS:
        return None
    return Conflict(str(_ROUTE_REFUSALS[problem]), code=f"verifactu.{problem}")


def refuse_on_the_platform_hub(ctx: OperationContext) -> None:
    """ERPlora's own hub files where its deployment does (``queries.route.effective_environment``): no switch moves it."""
    if platform.is_platform_hub(ctx.scope):
        raise Conflict(str(PLATFORM_FIXED), code="verifactu.platform_fixed")


def refuse_going_live(ctx: OperationContext, config: Config) -> None:
    """Raises why ``ctx``'s business cannot go live from ``config`` now, in this order: outside Spain, ERPlora's own
    hub, a server not open for real, a demo, no issuer in Invoicing, the route and the ERPlora account. A business
    already live is refused nothing: going live again changes nothing."""
    refuse_outside_spain(ctx)
    refuse_on_the_platform_hub(ctx)
    if config.environment == Environment.PRODUCTION:
        return
    if not production_open():
        raise Conflict(str(PRODUCTION_CLOSED), code="verifactu.production_closed")
    if platform.is_demo_hub(ctx.scope):
        raise Conflict(str(GO_LIVE_FORBIDDEN), code="verifactu.go_live_forbidden")
    if not issuer_configured():
        raise Conflict(str(ISSUER_MISSING), code="verifactu.issuer_missing")
    refusal = _route_refusal(config, ctx.scope)
    if refusal is not None:
        raise refusal
    if config.hub_status != Config.HubStatus.ACTIVE:
        raise Conflict(str(HUB_NOT_ACTIVE), code="verifactu.hub_not_active")


@operation(
    "verifactu.config.check_go_live",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=ConfigOut,
    ai=INTERNAL,
)
def check_go_live(ctx: OperationContext, data: NoInput) -> ConfigOut:
    """The configuration ``verifactu.config.go_live`` would switch, once nothing keeps the business from going live."""
    config = config_row()
    refuse_going_live(ctx, config)
    return config_out(config, ctx)

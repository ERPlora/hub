"""VeriFactu's configuration (``verifactu.config.*``): going live and back to testing, the ERPlora account's
photo, and ERPlora's own hub following its deployment."""


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.operations import operation

from base import operations as platform
from apps.verifactu import erplora_route
from apps.verifactu.models import Config, Environment, Record
from apps.verifactu.queries.config import config_out
from apps.verifactu.queries.country import refuse_outside_spain
from apps.verifactu.queries.route import (
    effective_environment,
    issuer_configured,
    production_open,
    route_problem,
    sending_route,
)
from apps.verifactu.schemas.config import ConfigOut, ConfigSyncIn, ConfigSyncOut
from apps.verifactu.schemas.fields import NoInput

from .authorisation import _representation_step
from .sending import _back_in_the_queue
from .writes import CONFIGURE, ISSUER_MISSING, _changed, _config

REPRESENTATION_NOT_APPROVED = _(
    "For ERPlora to file in production, ERPlora still has to approve your signed authorisation."
)
PRODUCTION_CLOSED = _(
    "Going live is not open on this server yet: ERPlora opens it when the real submission is ready."
)
HUB_NOT_ACTIVE = _(
    "Your ERPlora account has a pending payment or is suspended: settle it in your ERPlora account to go live."
)
PRODUCTION_HAS_RECORDS = _(
    "It cannot go back to testing: this business already has records in production."
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
PLATFORM_ONLY = _("Only ERPlora's own business follows the environment of its server.")


#: What keeps the route of that moment from filing in production, as the refusal ``go_live`` raises
#: (VERIFACTU-F04, F08). A closed server is not the route's: ``go_live`` refuses it first.
_ROUTE_REFUSALS = {
    "own_certificate_unreadable": OWN_CERTIFICATE_UNREADABLE,
    "own_certificate_untested": OWN_CERTIFICATE_UNTESTED,
    "own_certificate_rejected": OWN_CERTIFICATE_REJECTED,
    "gateway_unavailable": GATEWAY_UNAVAILABLE,
    "representation_not_approved": REPRESENTATION_NOT_APPROVED,
    erplora_route.CLOSED: erplora_route.OWN_CERTIFICATE_REQUIRED,
}


def _route_refusal(config: Config, scope: Scope) -> Conflict | None:
    problem = route_problem(config, Environment.PRODUCTION, scope)
    if problem not in _ROUTE_REFUSALS:
        return None
    return Conflict(str(_ROUTE_REFUSALS[problem]), code=f"verifactu.{problem}")


def _refuse_on_the_platform_hub(ctx: OperationContext) -> None:
    """ERPlora's own hub files where its deployment does (``queries.route.effective_environment``): no switch moves it."""
    if platform.is_platform_hub(ctx.scope):
        raise Conflict(str(PLATFORM_FIXED), code="verifactu.platform_fixed")


@operation(
    "verifactu.config.go_live",
    kind="command",
    permission=CONFIGURE,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "Go live: from now on every VeriFactu record goes to the real AEAT. It needs the server opened for "
        "it by ERPlora, a business that is not a demo, Invoicing's issuer, a route ready for production (the own valid certificate, or ERPlora's "
        "approved signed authorisation) and an active ERPlora account; it cannot "
        "go back once a production record is sealed.",
        "risk": "high",
        "asks": {
            "en": (
                "file for real with the AEAT from now on",
                "with the signed authorisation, take VeriFactu out of testing",
            ),
            "es": (
                "con la autorización firmada, pasa al envío real a Hacienda",
                "quiero remitir de verdad a la AEAT a partir de ahora",
            ),
        },
    },
)
def go_live(ctx: OperationContext, data: NoInput) -> ConfigOut:
    refuse_outside_spain(ctx)
    _refuse_on_the_platform_hub(ctx)
    config = _config()
    if config.environment == Environment.PRODUCTION:
        return config_out(config, ctx)
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
    # The route of this moment is kept: from now on production goes by it, whatever happens to the certificate.
    config.route = sending_route(config, Environment.PRODUCTION, ctx.scope)
    config.environment = Environment.PRODUCTION
    config.production_since = timezone.now()
    _changed(ctx, config, "went_live", fields=["environment", "route"])
    return config_out(config, ctx)


@operation(
    "verifactu.config.back_to_testing",
    kind="command",
    permission=CONFIGURE,
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "Go back to the AEAT's test environment; only while no VeriFactu record was sealed in production.",
        "risk": "high",
        "asks": {
            "en": (
                "go back to the AEAT's test environment",
                "put VeriFactu back in testing",
            ),
            "es": (
                "regresa al entorno de pruebas de la AEAT",
                "deja VeriFactu otra vez en pruebas",
            ),
        },
    },
)
def back_to_testing(ctx: OperationContext, data: NoInput) -> ConfigOut:
    _refuse_on_the_platform_hub(ctx)
    config = _config()
    if config.environment == Environment.TESTING:
        return config_out(config, ctx)
    if Record.objects.filter(environment=Environment.PRODUCTION).exists():
        raise Conflict(
            str(PRODUCTION_HAS_RECORDS), code="verifactu.production_has_records"
        )
    config.environment = Environment.TESTING
    config.production_since = None
    _changed(ctx, config, "back_to_testing", fields=["environment"])
    return config_out(config, ctx)


@operation(
    "verifactu.config.sync",
    kind="command",
    permission="verifactu.sync_config",
    input=ConfigSyncIn,
    output=ConfigSyncOut,
    ai={
        "description": "System only: the platform hands over the ERPlora account's VeriFactu block (the signed "
        "authorisation's state, the business's status) with its version; "
        "an equal or older version is ignored.",
        "risk": "high",
    },
)
def sync_config(ctx: OperationContext, data: ConfigSyncIn) -> ConfigSyncOut:
    config = _config()
    if config.synced_version is not None and data.version <= config.synced_version:
        return ConfigSyncOut(applied=False, version=config.synced_version)
    if data.hub_id is not None:
        config.hub_id = data.hub_id
    if data.representation is not None:
        if data.representation.status != config.representation_status:
            _representation_step(ctx, config, data.representation)
        config.representation_status = data.representation.status
        config.representation_updated_at = data.representation.updated_at
        config.representation_reason = data.representation.reason
    if data.hub_status is not None:
        config.hub_status = data.hub_status
    config.synced_version = data.version
    config.synced_at = timezone.now()
    _back_in_the_queue()
    _changed(
        ctx, config, "account_synced", {"version": data.version}, fields=["account"]
    )
    return ConfigSyncOut(applied=True, version=data.version)


# ── ERPlora's own hub ───────────────────────────────────────────────────────────────────────────


@operation(
    "verifactu.config.follow_deployment",
    kind="command",
    # Declared by no role: only the system holds it (``manage.py create_platform_hub``).
    permission="verifactu.follow_deployment",
    input=NoInput,
    output=ConfigOut,
    ai={
        "description": "System only: ERPlora's own business takes the AEAT environment of its server (prod: production; "
        "pre: testing), the one its records file in anyway; refused for any other business.",
        "risk": "high",
    },
)
def follow_deployment(ctx: OperationContext, data: NoInput) -> ConfigOut:
    if not platform.is_platform_hub(ctx.scope):
        raise Conflict(str(PLATFORM_ONLY), code="verifactu.platform_only")
    config = _config()
    environment = effective_environment(ctx, config)
    if config.environment == environment:
        return config_out(config, ctx)
    if environment == Environment.TESTING and Record.objects.filter(
        environment=Environment.PRODUCTION
    ).exists():
        raise Conflict(
            str(PRODUCTION_HAS_RECORDS), code="verifactu.production_has_records"
        )
    config.environment = environment
    went_live = environment == Environment.PRODUCTION
    config.production_since = timezone.now() if went_live else None
    _changed(
        ctx,
        config,
        "went_live" if went_live else "back_to_testing",
        fields=["environment"],
    )
    return config_out(config, ctx)

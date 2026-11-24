"""VeriFactu's configuration (``verifactu.config.*``): going live and back to testing, the ERPlora account's
photo, and ERPlora's own hub following its deployment."""


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation

from base import operations as platform
from apps.verifactu.models import Environment, Record
from apps.verifactu.queries.config import config_out
from apps.verifactu.queries.going_live import refuse_going_live, refuse_on_the_platform_hub
from apps.verifactu.queries.route import effective_environment, sending_route
from apps.verifactu.schemas.config import ConfigOut, ConfigSyncIn, ConfigSyncOut
from apps.verifactu.schemas.fields import NoInput

from .authorisation import _representation_step
from .sending import _back_in_the_queue
from .writes import CONFIGURE, _changed, _config

PRODUCTION_HAS_RECORDS = _(
    "It cannot go back to testing: this business already has records in production."
)
PLATFORM_ONLY = _("Only ERPlora's own business follows the environment of its server.")


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
        "check": "verifactu.config.check_go_live",
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
    config = _config()
    refuse_going_live(ctx, config)
    if config.environment == Environment.PRODUCTION:
        return config_out(config, ctx)
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
    refuse_on_the_platform_hub(ctx)
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

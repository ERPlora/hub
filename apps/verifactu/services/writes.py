"""What every write of VeriFactu shares: the permissions it asks, the message of a missing issuer, the person
who acts, the audit trail's entry, the configuration's row and the chain's head, locked, and a change of the
configuration recorded."""


from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.outbox import record_event

from apps.verifactu import events
from apps.verifactu.models import Chain, Config, Event, SendControl

ISSUER_MISSING = _("Set up the issuer first in Invoicing → Issuer.")

CONFIGURE = "verifactu.configure"
TRANSMIT = "verifactu.transmit_record"


def _actor(ctx: OperationContext) -> str:
    actor = ctx.actor
    return str(getattr(actor, "username", None) or actor or "")[:128]


def _event(  # noqa: PLR0913
    ctx: OperationContext,
    kind: str,
    key: str,
    params: dict,
    *,
    severity: str = "info",
    record=None,
    environment="",
) -> Event:
    event = Event(
        kind=kind,
        severity=severity,
        message_key=key,
        params=params,
        record=record,
        environment=environment,
        actor=_actor(ctx),
    )
    event.search_text = event.compose_search_text()
    event.save()
    return event


def _config(lock: bool = True) -> Config:
    """The configuration row, created on first use."""
    Config.objects.bulk_create([Config(singleton=True)], ignore_conflicts=True)
    queryset = Config.objects.select_for_update() if lock else Config.objects
    return queryset.get(singleton=True)


def _lock_chain(issuer_nif: str, environment: str) -> Chain:
    """The chain's head, locked until the COMMIT (created with its send control on first use)."""
    Chain.objects.bulk_create(
        [Chain(issuer_nif=issuer_nif, environment=environment)], ignore_conflicts=True
    )
    SendControl.objects.bulk_create(
        [SendControl(issuer_nif=issuer_nif, environment=environment)],
        ignore_conflicts=True,
    )
    return Chain.objects.select_for_update().get(
        issuer_nif=issuer_nif, environment=environment
    )


def _changed(
    ctx, config: Config, key: str, params: dict | None = None, *, fields: list[str]
) -> None:
    config.updated_by = _actor(ctx)
    config.save()
    _event(
        ctx,
        Event.Kind.CONFIG_CHANGED,
        key,
        params or {},
        environment=config.environment,
    )
    record_event(ctx, events.CONFIG_CHANGED, {"fields": fields})

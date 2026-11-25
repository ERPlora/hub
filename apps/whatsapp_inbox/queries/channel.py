"""The business's WhatsApp number: whether anything can be sent now, its state and this month's messages,
and erplora.com's plans."""

from django.conf import settings
from live.context import OperationContext, Scope
from live.operations import operation

from apps.whatsapp_inbox import clock, gateway
from apps.whatsapp_inbox.models import Channel
from apps.whatsapp_inbox.schemas.channel import ChannelGetIn, ChannelOut
from base.saas_store import plans_url


def channel(scope: Scope) -> Channel | None:
    """The number of the business of ``scope``, or ``None`` before erplora.com spoke of it."""
    return Channel.objects.first()


def send_blocked(row: Channel | None) -> str | None:
    """Why nothing can be sent now: no connected number, no SaaS to send through, the month spent."""
    if row is None or row.status != Channel.Status.CONNECTED:
        return "not_connected"
    if not gateway.configured():
        return "unconfigured"
    if row.cap_reached(clock.allowance_month()):
        return "cap_reached"
    return None


@operation(
    "whatsapp_inbox.channel.get",
    kind="query",
    permission="whatsapp_inbox.view",
    input=ChannelGetIn,
    output=ChannelOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is our WhatsApp number connected?",
                "how many WhatsApp messages have we sent this month?",
                "how much of the plan's WhatsApp allowance is left?",
            ),
            "es": (
                "¿tenemos conectado el número de WhatsApp?",
                "¿cuánto consumo de WhatsApp llevamos este mes?",
                "¿cuánto cupo de WhatsApp nos queda en el plan?",
            ),
        },
        "description": "The business's WhatsApp number as erplora.com reports it (connected or not) and the "
        "messages sent this month against the plan's allowance."
    },
)
def channel_get(ctx: OperationContext, data: ChannelGetIn) -> dict:
    row = channel(ctx.scope) or Channel()
    month = clock.allowance_month()
    return {
        "status": row.status,
        "phone_number": row.phone_number,
        "display_name": row.display_name,
        "monthly_limit": row.monthly_limit,
        "monthly_usage": row.monthly_usage if row.usage_month == month else 0,
        "cap_reached": row.cap_reached(month),
        "synced_at": row.synced_at,
        "manage_url": str(getattr(settings, "SAAS_URL", "") or ""),
        "plans_url": plans_url(ctx.scope.key),
    }

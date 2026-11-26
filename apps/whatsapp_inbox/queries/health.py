"""Whether the business's number is connected, in the words of the Home's health row."""

from live.context import OperationContext
from live.operations import INTERNAL, operation

from apps.whatsapp_inbox.models.channel import Channel
from apps.whatsapp_inbox.queries.channel import channel
from apps.whatsapp_inbox.schemas.health import ChannelHealthIn, ChannelHealthOut

STATES = {Channel.Status.CONNECTED: "ok", Channel.Status.RECONNECT_NEEDED: "no_signal"}


# Not an assistant tool: whatsapp_inbox.channel.get already tells it whether the number is connected.
@operation(
    "whatsapp_inbox.channel.health",
    kind="query",
    permission="whatsapp_inbox.view",
    input=ChannelHealthIn,
    output=ChannelHealthOut,
    ai=INTERNAL,
)
def channel_health(ctx: OperationContext, data: ChannelHealthIn) -> dict:
    row = channel(ctx.scope)
    return {"state": STATES.get(row.status, "not_configured") if row else "not_configured"}

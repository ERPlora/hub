"""What ``whatsapp_inbox.channel.health`` answers: whether the business's number is connected."""

from typing import Literal

from ninja import Field, Schema


class ChannelHealthIn(Schema):
    pass


class ChannelHealthOut(Schema):
    state: Literal["ok", "no_signal", "not_configured"] = Field(
        description="ok: erplora.com reports the number connected; no_signal: WhatsApp asks to reconnect it; "
        "not_configured: no number is connected."
    )

"""Schemas of the messages of a conversation: their list, how one reads and the reference to one."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.whatsapp_inbox.schemas.fields import A_MESSAGE, MESSAGE, ConversationPageIn, Page
from base.sensitive import CUSTOMER_CONTACT


class MessageListIn(ConversationPageIn):
    pass


class MessageOut(Schema):
    id: UUID = Field(description="The message's id.")
    conversation_id: UUID = Field(description="Its conversation.")
    direction: Literal["inbound", "outbound"] = Field(
        description="inbound (customer) or outbound (business)."
    )
    origin: Literal["customer", "phone_app", "hub"] = Field(
        description="customer, phone_app (the owner's WhatsApp Business app) or hub (sent from here)."
    )
    source: Literal["live", "history"] = Field(
        description="live, or history brought by connecting the number."
    )
    kind: str = Field(
        description="Meta's type: text, image, audio, video, document, sticker, location, template…"
    )
    body: str = Field(description="The text.")
    media_url: str = Field(description="The attachment, at erplora.com.")
    media_mime_type: str = Field(description="The attachment's type.")
    media_filename: str = Field(description="The attachment's file name.")
    media_caption: str = Field(description="The attachment's caption.")
    template_name: str = Field(description="The template used, for a template message.")
    status: Literal["received", "queued", "sending", "sent", "delivered", "read", "failed"] = Field(
        description="Where it is."
    )
    error_code: str = Field(description="Meta's error code when it was not delivered.")
    error_message: str = Field(description="Meta's reason when it was not delivered.")
    wa_message_id: str | None = Field(description="WhatsApp's id of the message; none while it has not left.")
    reply_to: str = Field(description="WhatsApp's id of the message it answers.")
    reply_id: str = Field("", description="The id of the option the customer tapped, for a button or list reply.")
    sent_by_name: str = Field(description="Who sent it from the Hub.")
    sent_at: datetime = Field(description="When it was said.")
    status_at: datetime | None = Field(description="When its status last changed.")


class MessagePage(Page[MessageOut]):
    pass


class MessageGetOut(MessageOut):
    """A message with what an automation needs to answer it: its conversation's exact number, her name and the options
    last offered to her."""

    phone: str | None = Field(
        None,
        description="Its conversation's number, exactly in international format (+34600111222).",
        json_schema_extra=CUSTOMER_CONTACT,
    )
    display_name: str = Field(
        description="What to call the customer: her card's name, her WhatsApp profile's or, with neither, her number "
        "(masked to whoever does not see the customers' contact details)."
    )
    can_send: bool = Field(
        description="Whether anything can be sent now (the number connected and the month's messages not spent)."
    )
    options: str = Field(
        description="What the business last wrote her from the Hub in the 24 hours before this message, where the "
        "options she may be answering by their number («the 2nd») were offered; empty when it wrote her nothing."
    )


class MessageRefIn(Schema):
    id: UUID = Field(title=MESSAGE, description="The message's id.", json_schema_extra=A_MESSAGE)

"""Schemas of the business's WhatsApp number: what erplora.com reports of it and connecting it from Settings."""

from datetime import datetime
from typing import Annotated, Literal

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints

from apps.whatsapp_inbox.schemas.fields import _text
from apps.whatsapp_inbox.schemas.templates import HeaderFormat, TemplateCategory

#: E.164 or nothing (the business's own number before it is connected).
E164_OR_EMPTY = r"^(\+[1-9]\d{6,14})?$"

#: Meta's verdicts erplora.com reports (``DRAFT`` is the Hub's own: Meta never had it).
MetaTemplateStatus = Literal["APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED", "DELETED"]


class SyncTemplateIn(Schema):
    name: _text(512, 1) = Field(description="The template's name at Meta.")
    language: _text(15, 1) = Field(description="Its language code.")
    category: TemplateCategory = Field(
        "UTILITY", description="UTILITY, MARKETING or AUTHENTICATION."
    )
    status: MetaTemplateStatus = Field("APPROVED", description="Meta's verdict.")
    header_format: HeaderFormat | None = Field(
        None, description="Its header: none, TEXT, IMAGE, VIDEO, DOCUMENT or LOCATION; TEXT when missing and there is a header text."
    )
    header: _text(200) = Field("", description="Its header text.")
    body: _text(4096) = Field("", description="Its body with {{n}} placeholders.")
    body_examples: list[_text(1024)] = Field(default_factory=list, max_length=100, description="The examples Meta holds.")
    footer: _text(200) = Field("", description="Its footer.")
    buttons: list[dict] = Field(
        default_factory=list, max_length=10, description="Meta's buttons: {type, text, url?, phone_number?}."
    )
    variables: int = Field(
        0, ge=0, le=100, description="How many variables the body takes."
    )
    rejected_reason: _text(500) = Field(
        "", description="Meta's reason for a rejection."
    )
    meta_id: _text(64) = Field("", description="Meta's id of the template.")


class ChannelSyncIn(Schema):
    version: int = Field(
        ge=0,
        description="erplora.com's version of this state; an older one is ignored.",
    )
    status: Literal["not_connected", "connected", "reconnect_needed"] = Field(
        description="The number's state."
    )
    phone_number: Annotated[str, StringConstraints(strip_whitespace=True, pattern=E164_OR_EMPTY)] = Field(
        "", description="The business's number, E.164 (+34910000000), empty while not connected."
    )
    display_name: _text(200) = Field("", description="The name WhatsApp shows for it.")
    monthly_limit: int = Field(
        0, ge=0, description="Messages the plan includes each month; 0 = none (never «unlimited»)."
    )
    monthly_usage: int = Field(
        0, ge=0, description="Messages sent this month, as erplora.com counts them."
    )
    usage_month: Annotated[
        str, StringConstraints(pattern=r"^(\d{4}-(0[1-9]|1[0-2]))?$")
    ] = Field("", description="The month that figure counts, YYYY-MM.")
    templates: list[SyncTemplateIn] | None = Field(
        None,
        max_length=1000,
        description="Every template of the account; null leaves them as they are.",
    )


class ChannelSyncOut(Schema):
    applied: bool = Field(
        description="False when an equal or newer version was already here."
    )
    version: int = Field(description="The version the Hub holds now.")


class ChannelGetIn(Schema):
    pass


class ChannelOut(Schema):
    status: Literal["not_connected", "connected", "reconnect_needed"] = Field(
        description="The number's state."
    )
    phone_number: str = Field(description="The business's number.")
    display_name: str = Field(description="The name WhatsApp shows for it.")
    monthly_limit: int = Field(
        description="Messages the plan includes each month; 0 = none (never «unlimited»)."
    )
    monthly_usage: int = Field(
        description="Messages sent this month (0 when erplora.com has not counted this month yet)."
    )
    cap_reached: bool = Field(
        description="Whether this month's messages are spent: always when the plan includes none (once "
        "erplora.com said so)."
    )
    synced_at: datetime | None = Field(description="When erplora.com last reported.")
    manage_url: str = Field(
        description="Where the number is connected and managed: erplora.com."
    )
    plans_url: str = Field(
        description="Where the plan is upgraded for more WhatsApp messages: erplora.com's plans; empty when "
        "this server is not linked to erplora.com."
    )


# ── Connecting the number from Settings (WHATSAPP_INBOX-F01, F02; erplora.com's doors 10–12) ────

#: An id of Meta (an account, a number, a portfolio): digits only.
META_ID = r"^\d{1,50}$"
META_ID_OR_EMPTY = r"^\d{0,50}$"


class ChannelPrepareIn(Schema):
    pass


class ChannelPrepareOut(Schema):
    available: bool = Field(
        description="Whether Meta's window (WhatsApp Embedded Signup) can be opened from Settings now."
    )
    reason: Literal["not_configured", "window_unavailable", "popups_blocked"] | None = Field(
        None,
        description="Why not: WhatsApp is not set up on erplora.com (not_configured), erplora.com has no page "
        "to bring Meta's answer back (window_unavailable), or this Hub's pages cut the windows they open "
        "(popups_blocked).",
    )
    app_id: str = Field("", description="The id of ERPlora's app at Meta (public).")
    config_id: str = Field("", description="The id of the Embedded Signup configuration (public).")
    graph_version: str = Field("", description="The version of Meta's Graph API, e.g. v25.0.")
    redirect_uri: str = Field(
        "", description="erplora.com's page Meta's window returns the one-time code to (https)."
    )


class ChannelConnectIn(Schema):
    code: _text(2048, 1) = Field(
        title=gettext_noop("Meta connection code"),
        description="The one-time code Meta's window returned (it lasts 30 seconds).",
    )
    event: Annotated[str, StringConstraints(pattern=r"^FINISH[A-Z_]{0,58}$")] = Field(
        "FINISH",
        title=gettext_noop("How Meta's window finished"),
        description="How Meta's window finished (FINISH, or FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING for a "
        "number of the WhatsApp Business app); a window cancelled or failed connects nothing.",
    )
    waba_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=META_ID)] = Field(
        title=gettext_noop("WhatsApp Business account"),
        description="The WhatsApp Business account chosen in Meta's window.",
    )
    phone_number_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=META_ID_OR_EMPTY)] = Field(
        "",
        title=gettext_noop("Your number"),
        description="The number chosen in Meta's window (empty: the account's only number).",
    )
    business_id: Annotated[str, StringConstraints(strip_whitespace=True, pattern=META_ID_OR_EMPTY)] = Field(
        "", title=gettext_noop("Business portfolio at Meta"), description="The business portfolio at Meta."
    )


class ChannelConnectOut(Schema):
    connected: bool = Field(description="Whether erplora.com connected the number.")
    phone_number: str = Field(description="The connected number, E.164.")
    display_name: str = Field(description="The name WhatsApp shows for it.")
    history_requested: bool = Field(
        description="For a number of the WhatsApp Business app: whether its contacts and chats were asked of Meta."
    )


class ChannelDisconnectIn(Schema):
    pass


class ChannelDisconnectOut(Schema):
    disconnected: bool = Field(
        description="False when erplora.com had no number connected for this business."
    )

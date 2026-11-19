"""Schemas of «Report a problem» (``base.support.report``) and the pass to erplora.com (``base.saas_pass.create``)."""

from typing import Literal

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field


class SupportReportIn(Schema):
    """What the person writes to erplora.com's support from «Report a problem», with the limits of erplora.com's own
    form for it; the account, the business and the browser go with it on their own."""

    subject: str = Field(max_length=150, title=gettext_noop("Report subject"))
    description: str = Field(max_length=5000, title=gettext_noop("What happened?"))
    #: The hub's screen the person was on, as the SPA's router knew it.
    page: str | None = Field(default=None, max_length=500, title=gettext_noop("Screen"))


class SupportReportOut(Schema):
    #: Where support answers: the account's email, as erplora.com says.
    reply_to: str


class SaasPassIn(Schema):
    #: Where the pass leads on erplora.com: this business's plan or this business (ACCOUNTS-F29 of the SaaS).
    next: Literal["plan", "business"] = Field(title=gettext_noop("Where to go"))


class SaasPassOut(Schema):
    #: erplora.com's door with the signed pass: it opens for a minute, once.
    url: str


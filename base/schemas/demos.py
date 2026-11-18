"""Schemas of the demos (``base.demo.*``): those of ``POST /internal/demos`` and
``POST /internal/demos/{slug}/codes``, as the SaaS's ``hubs.hub_client.create_demo`` and ``create_demo_code`` send
and read them."""

import datetime as dt
from uuid import UUID

from ninja import Schema
from pydantic import Field


#: A browser of the SaaS, as the SaaS names it to the Hub: the sha256 (hex) of a random token of its session.
SESSION_KEY_PATTERN = r"^[0-9a-f]{64}$"


class DemoCreateIn(Schema):
    """``POST /internal/demos``: a demo for this browser; ``vertical`` is only noted, never seeded."""

    session_key: str = Field(pattern=SESSION_KEY_PATTERN)
    vertical: str | None = Field(None, max_length=63)
    language: str = Field("", max_length=8)


class DemoOut(Schema):
    """The browser's demo; ``created`` says whether this call made it (202, ``requested``) or it was the live one
    (200); ``status`` is the registry's (``ready`` once its database is made)."""

    id: UUID
    slug: str
    status: str
    expires_at: dt.datetime
    created: bool


class DemoCodeIn(Schema):
    """``POST /internal/demos/{slug}/codes``: a one-time code into ``slug`` for the browser that owns it."""

    slug: str = Field(max_length=63)
    session_key: str = Field(pattern=SESSION_KEY_PATTERN)
    language: str = Field("", max_length=8)


class DemoCodeOut(Schema):
    code: str
    expires_at: dt.datetime


class DemoSlugIn(Schema):
    slug: str = Field(max_length=63)


class DemoStatusOut(Schema):
    """A demo of the registry: ``ready`` while it lasts, ``expired`` once ended, ``purged`` once the reaper came."""

    slug: str
    status: str
    expires_at: dt.datetime | None


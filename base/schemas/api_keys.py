"""Schemas of the business's API keys (``base.api_key.*``) and its API's documentation (``base.api_doc.*``)."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field

from base.schemas.assistant import names


# ── People and permissions: the business's API keys and its API's documentation ───────────────────────────────────


class ApiKeyListIn(Schema):
    """No input: the keys of the business of the request."""


#: What a key may do on an app (``base.api_actions``).
Action = Literal["read", "create", "update", "delete"]
#: Per app (its id), or ``"*"`` for every app of the business, also the ones it adds later: the actions given there.
Scopes = dict[str, list[Action]]


class ApiKeyOut(Schema):
    id: UUID
    name: str
    prefix: str = Field(description="The token's first characters, to tell it apart; never the whole token.")
    scopes: Scopes = Field(description='What it may do: per app, or "*" for every app, the actions given there.')
    rate_per_minute: int
    created_by: str
    created_at: dt.datetime
    rotated_at: dt.datetime | None
    last_used_at: dt.datetime | None
    revoked_at: dt.datetime | None


class ApiAppOut(Schema):
    """An app this business has that publishes operations, and what a key may do on it."""

    id: str
    name: str
    actions: list[Action] = Field(description="What it publishes: read for its queries; create, update and delete.")


class ApiKeyListOut(Schema):
    keys: list[ApiKeyOut]
    apps: list[ApiAppOut]
    grantable: Scopes = Field(
        description='The most who asks may give a key: per app, and on "*" (every app), what they may do there.'
    )


class ApiKeyCreateIn(Schema):
    name: str = Field(max_length=80)
    rate_per_minute: int = Field(60, ge=1, le=10_000)
    scopes: Scopes = Field(
        description='What it may do: per app, or "*" for every app, the actions given there; never more than who '
        "makes it may do."
    )


class ApiKeyIdIn(Schema):
    id: UUID = Field(title=gettext_noop("API key"), json_schema_extra=names("base.api_key.detail"))


class ApiKeyTokenOut(Schema):
    """A key just made or rotated, with its whole token: the only time it is shown."""

    key: ApiKeyOut
    token: str


class ApiKeyRevokeOut(Schema):
    key: ApiKeyOut



# ── People and permissions: the API's documentation ────────────────────────────────────────────────────────────────


class ApiDocIn(Schema):
    """No input."""


class ApiDocOut(Schema):
    document: dict = Field(description="The OpenAPI document of what this business's apps publish.")
    apps: list[ApiAppOut] = Field(description="The apps in it (its tags), by name.")


class ApiDocSettingsIn(Schema):
    """No input."""


class ApiDocSettingsOut(Schema):
    docs_enabled: bool
    can_change: bool = Field(description="Whether who asks may change it (who runs the business).")


class ApiDocSettingsUpdateIn(Schema):
    docs_enabled: bool


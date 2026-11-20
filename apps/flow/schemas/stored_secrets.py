"""Schemas of the secrets a call reads (``flow.secret.*``, FLOW-F26): set by name and never shown again."""

import datetime as dt
from typing import Annotated
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, SecretStr, StringConstraints

from apps.flow.models import SECRET_NAME_RE
from apps.flow.schemas.fields import In

SecretName = Annotated[str, StringConstraints(pattern=SECRET_NAME_RE)]
D_SECRET_NAME = "The secret's name: upper case letters, digits and _, up to 64 (`STRIPE_KEY`)."


class SecretListIn(In):
    pass


class SecretSetIn(In):
    # A refused value is never echoed in an error (the 422 says why, never what).
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: SecretName = Field(description=D_SECRET_NAME)
    value: Annotated[SecretStr, Field(min_length=1, max_length=4096)] = Field(
        title=gettext_noop("Value"),
        description="The value, typed by the person on the screen; it is never shown again."
    )


class SecretRefIn(In):
    name: SecretName = Field(description=D_SECRET_NAME)


class SecretOut(Schema):
    id: UUID
    name: str
    created_at: dt.datetime
    updated_at: dt.datetime
    updated_by: str


class SecretPageOut(Schema):
    rows: list[SecretOut]
    available: bool = Field(description="Whether this server can keep and use secrets (it has its key).")

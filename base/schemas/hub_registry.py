"""Schemas of the hub's registry (``base.hub.*``), the bodies of the SaaS's ``/internal/hubs/{id}`` calls:
``HubRegistryIn`` is ``hubs.queries.hub_registry`` of the SaaS, ``HubOut`` what the Hub answers to it."""

import datetime as dt
from typing import Annotated, Any, Literal
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import DomainNameValidator
from django.http.request import validate_host
from ninja import Schema
from pydantic import AfterValidator, Field

from base.schemas.people import HubRole


class HubRegistryIn(Schema):
    """``PUT /internal/hubs/{id}``: what the SaaS registers a business with."""

    id: UUID
    slug: str
    name: str = Field("", max_length=120)
    country: str = Field("", max_length=2)
    timezone: str = Field("", max_length=64)
    language: str = Field("", max_length=8)
    vertical: str | None = Field(None, max_length=63)


class HubOut(Schema):
    """A hub of the registry, as ``/internal/hubs/{id}`` answers it; ``status`` ``ready`` is what the SaaS waits for."""

    id: UUID
    slug: str
    status: str
    is_demo: bool
    expires_at: dt.datetime | None
    ready_at: dt.datetime | None
    state_version: int


class HubMaintenanceOut(Schema):
    """A database upgrade pauses provisioning platform-wide; ``None`` on ``HubGetOut`` once it is lifted."""

    frozen: bool
    reason: str
    since: dt.datetime | None


class HubGetOut(HubOut):
    """The signed status poll: the registry row plus the real maintenance state, never a guessed timeout, and when the
    business's move asked for its night starts (``None`` without one), never where it goes."""

    maintenance: HubMaintenanceOut | None
    move_scheduled_for: dt.datetime | None


class HubRegisterOut(HubOut):
    #: Whether this call created the row (``202``) or updated it (``200``); not sent to the SaaS.
    created: bool


class MemberIn(Schema):
    """One person of the business as the photo lists them (``hubs.queries`` of the SaaS: its accepted members)."""

    user_id: UUID
    role: HubRole
    email: str | None = None
    name: str | None = None


#: The longest a domain name can be (RFC 1035) and what ``Hub.custom_domain`` keeps; ``DomainNameValidator`` lets 255 by.
MAX_DOMAIN_LENGTH = 253


def custom_domain_of_photo(value: str | None) -> str | None:
    """The domain a photo names, lowercase and without a final dot: a host name of a public domain, in its ASCII form,
    that the Hub does not answer already (``ALLOWED_HOSTS``), or it would put a website on another business's host."""
    if value is None or value == "":
        # Nothing named, as null or absent: never a domain, and refusing it would refuse the whole photo.
        return None
    domain = value.lower().removesuffix(".")
    if len(domain) > MAX_DOMAIN_LENGTH or domain.endswith("."):
        raise ValueError("not a domain name in its ASCII form")
    try:
        DomainNameValidator(accept_idna=False)(domain)
    except DjangoValidationError:
        raise ValueError("not a domain name in its ASCII form") from None
    if domain.rpartition(".")[2].isdigit():
        raise ValueError("an IP address is no domain")
    if validate_host(domain, settings.ALLOWED_HOSTS):
        raise ValueError("a host the Hub already answers")
    return domain


class HubStateIn(Schema):
    """``PUT /internal/hubs/{id}/state``: the SaaS's photo (``photo``, as it came) and the parts the Hub applies."""

    id: UUID
    version: int = Field(ge=0)
    status: Literal["active", "past_due", "suspended"] | None = None
    verifactu: dict[str, Any] | None = None
    whatsapp: dict[str, Any] | None = None
    members: list[MemberIn] | None = None
    custom_domain: Annotated[str | None, AfterValidator(custom_domain_of_photo)] = None
    photo: dict[str, Any]


class HubStateOut(Schema):
    applied: bool
    version: int



class HubGetIn(Schema):
    id: UUID


class HubCancelIn(Schema):
    id: UUID


class HubRestoreIn(Schema):
    id: UUID


class HubCutFinishIn(Schema):
    """The last step of the cut of a business that shared a database (``base.tenancy.cut``): its database made, its rows copied
    (``copied``: rows per table, none when it was made again) and seeded with the SaaS's photo of ``seeded_version``."""

    id: UUID
    mode: Literal["recreate", "copy_all"]
    database: str
    schema_apps: dict[str, str]
    copied: dict[str, int]
    dump: str = ""
    seeded_version: int | None = None


class HubCutFinishOut(Schema):
    """``done``: the business now works on its own database; false when a newer photo came while it was seeded (the
    cut applies it and asks again)."""

    done: bool


class HubSeedLocalIn(Schema):
    """``manage.py seed_local_hubs``: the local hubs to leave ready (``a`` and ``b``), each with a database of its own
    (``requested``, the command makes it)."""

    slugs: list[str]


class SeededHub(Schema):
    slug: str
    outcome: Literal["created", "ready_again", "already_ready", "requested"]


class HubSeedLocalOut(Schema):
    hubs: list[SeededHub]


class HubsBySlugIn(Schema):
    slugs: list[str]


class HubStatusOut(Schema):
    slug: str
    #: The registry's status, or ``None`` when no row has this slug.
    status: str | None


class HubsBySlugOut(Schema):
    hubs: list[HubStatusOut]


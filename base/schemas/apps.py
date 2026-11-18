"""Schemas of the business's apps (``base.app.*``)."""

from typing import Literal

from ninja import Schema
from pydantic import Field

from base.schemas.assistant import names


# ── Apps ───────────────────────────────────────────────────────────────────────────────────────────────────────


class AppListIn(Schema):
    """No input: the business's apps, all of them (the modules of the deployment, a short fixed list)."""


class AppOut(Schema):
    """A module as the Apps screen paints it, with the business's right to it."""

    id: str
    name: str
    icon: str
    category: str
    category_label: str
    summary: str
    #: Bought on erplora.com (``premium``): no price here, the Store has it.
    premium: bool
    #: Where its right comes from: ``free``, ``plan``, ``purchase``, ``required`` (with an app that needs it) or
    #: ``missing``.
    right: Literal["free", "plan", "purchase", "required", "missing"]
    #: ``on``, ``off`` (the business turned it off, or never on), ``blocked`` while the business has no right to it;
    #: in a hub with its own database, ``creating`` while its tables are made and ``failed`` when making them failed
    #: (tried again later, or by hand: ``base.app.retry``).
    state: Literal["on", "off", "blocked", "creating", "failed"]
    #: The business turned it on itself (what the plan's limit counts, also while it is being set up); what came along
    #: with another app is not.
    chosen: bool
    #: The first screen of its menu this person may open; ``None``: «Open» is not offered.
    path: str | None
    #: What it needs, transitively (it comes along with it), and the apps on that need it (they go off first).
    requires: list[str]
    required_by: list[str]
    #: Why turning it on (off) or off (on) is refused, in the reader's language: an app's own ``can_enable`` or
    #: ``can_disable``, base's for one the business's country requires on, and the apps it depends on (hub#618,
    #: hub#694, hub#997); ``None``: nothing refuses it.
    refusal: str | None
    #: The business's country requires it on, as the app declares it (``mandatory``, hub#997): «Mandatory in …», on or
    #: off; once on there, it never goes off.
    mandatory: bool


class AppListOut(Schema):
    apps: list[AppOut]
    #: The business's country by its name in the reader's language (a business without one is in Spain): what
    #: «Mandatory in …» says.
    country_name: str
    #: erplora.com's Store of this business's modules, where a paid one is bought (never inside the Hub).
    store_url: str
    #: erplora.com's plans of this business, where a higher limit is bought.
    plan_url: str
    #: How many apps the plan lets the business choose (``plan.max_apps`` of the SaaS's photo); ``None``: no limit.
    max_apps: int | None
    #: How many it chose and are on: what the limit counts (what came along with them does not).
    enabled: int


#: An app as the person names it (BASE-F23, F24; hub#539): ``base.queries.apps.find_app`` resolves it.
APP_SAID = (
    "The app: its name as the person says it (e.g. «Reservas»), or its id. A name that fits several apps is refused "
    "naming them: ask the person which one."
)


class AppRefIn(Schema):
    """``base.app.get``: one app of the business, by its name or its id."""

    app: str = Field(max_length=100, description=APP_SAID)


class AppRefOut(Schema):
    """Which app a name names: its id, its name in the reader's language and its state, as the Apps screen says it
    (``AppOut.state``: ``creating`` and ``failed`` while a hub's own database gets its tables)."""

    id: str
    name: str
    state: Literal["on", "off", "blocked", "creating", "failed"]


class AppChangeIn(Schema):
    """``base.app.enable`` and ``base.app.disable``: one app of the business, by its name or its id; the assistant's
    card names it as ``base.app.get`` reads it, never by its id."""

    app: str = Field(max_length=100, description=APP_SAID, json_schema_extra=names("base.app.get", by="app"))


class AppNameOut(Schema):
    id: str
    name: str


class AppChangeOut(Schema):
    """The app as it is now, and the apps that went on (or off) with it. ``creating``: its tables are being made in the
    hub's own database (202); the Apps screen follows it until it is on (``base.app.list``)."""

    app: str
    state: Literal["on", "off", "creating"]
    chosen: bool
    #: Turned on with it because it needs them, or off with it because nothing else needs them any more; by name.
    along: list[AppNameOut]
    already: bool = Field(
        description="It was on already (turning it on) or off already (turning it off): nothing went on or off."
    )


class AppActivationSettleIn(Schema):
    """The worker's step after making a hub's tables (``base.worker``): the apps it took and how it went."""

    apps: list[str] = Field(description="The apps whose tables it made, or tried to.")
    #: ``created``: ``ensure_schema`` ended; ``failed``: it raised (``error``, why); ``locked``: another run held the
    #: hub's schema; ``newer_code``: the request is of a newer code than the worker's.
    outcome: Literal["created", "failed", "locked", "newer_code"]
    error: str = ""


class AppActivationSettleOut(Schema):
    on: list[str]
    failed: list[str]
    waiting: list[str]


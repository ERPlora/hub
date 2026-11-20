"""Schemas of the Home (``base.setup.status``, ``base.widget.list``, ``base.system.cards``, ``base.notice.list``)."""

from typing import Any, Literal

from ninja import Schema
from pydantic import Field


# --- The Home: base.setup.status, base.widget.list ------------------------------------------------------------


class SetupStatusIn(Schema):
    """No input: the list of this hub, as the person of the request may be told about it."""


class SetupItemOut(Schema):
    key: str = Field(
        description="«<app>.<step>»: «base.apps», «base.mandatory.<app>» (turn on an app mandatory in the business's "
        "country), «base.team» or a module's own step."
    )
    app: str = Field(description="The app that declares the step («base» for the platform's).")
    state: Literal["done", "pending", "unavailable"] = Field(
        description="«unavailable»: ours, not the person's task (nothing could be turned on)."
    )
    level: Literal["legal", "functional", "recommended"] = Field(
        description="«legal» (needed to invoice) is base's list; else the module's «required»."
    )
    required: bool
    actionable: bool = Field(description="False: a pending ⛔ that the person cannot set up (an administrator must).")
    title: str
    description: str
    icon: str
    route: str = Field(description="The screen that completes it.")
    order: int


class SetupStatusOut(Schema):
    total: int
    pending: int
    unavailable: int
    blocking_pending: int = Field(description="Pending ⛔ steps: the invoice is refused until they are done.")
    items: list[SetupItemOut]


class WidgetListIn(Schema):
    """No input: the panels this person may put on the dashboard of this hub."""


class WidgetOut(Schema):
    key: str = Field(description="«<app>.<panel>».")
    app: str
    title: str
    icon: str
    category: str = Field(description="The group of the picker: the panel's own, or its app's name.")
    size: Literal["sm", "md", "lg"]
    default: bool = Field(description="On by default, before the person chooses.")
    kind: str | None = Field(description="How it renders without a component of its own (kpi, stat, sparkline…).")
    operation: str | None = Field(description="The query that feeds it, followed live by the SPA.")
    params: dict[str, Any]
    map: dict[str, str] = Field(description="Prop of the panel → field of the operation's result.")
    options: dict[str, Any] = Field(description="Literal props of the panel.")
    component: str | None = Field(description="A Vue component of the app's frontend/components/, without «.vue».")
    refresh_on: list[str]
    live: bool = Field(description="Its operation is a live query: the SPA follows it, else it asks once.")


class WidgetListOut(Schema):
    widgets: list[WidgetOut]


class SystemCardsIn(Schema):
    """No input: the cards the apps on in this hub put in System › «Usage and plan» for this person (hub#683)."""


class SystemCardOut(Schema):
    key: str = Field(description="«<app>.<card>».")
    app: str
    component: str = Field(description="The Vue component of the app's frontend/components/ that paints it, without .vue.")


class SystemCardsOut(Schema):
    cards: list[SystemCardOut]


class NoticeListIn(Schema):
    """No input: what the modules on tell this person's device, of the rows their queries give them."""


class DeviceNoticeOut(Schema):
    key: str = Field(description="«<app>.<notice>».")
    app: str
    id: str = Field(description="The id of what happened, as the module's row says it.")
    at: str = Field(description="The instant it happened, as the module's row says it: with key and id, told once.")
    title: str
    body: str = Field(description="Empty when none of its parts is filled in.")
    route: str = Field(description="The screen a tap opens; empty when a field of it is empty.")


class NoticeListOut(Schema):
    notices: list[DeviceNoticeOut] = Field(description="The newest first.")
    sources: list[str] = Field(
        description="«<app>.<notice>» of every notice this person hears, told or not: with none, nothing to ask for."
    )


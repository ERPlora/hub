"""Schemas of the system's status (``base.system.status``) and its event log (``base.event.list``)."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Schema


# ── System ─────────────────────────────────────────────────────────────────────────────────────────────────────


class SystemStatusIn(Schema):
    """No input: the status of the hub of the request."""


class SystemStatusOut(Schema):
    """``base.system.status``: what runs. No usage figures: one service runs every business, so CPU, memory and
    connections have no figure per business."""

    #: The release running: its commit, short (``APP_VERSION``); ``dev`` without one (local development).
    version: str
    #: When that release was published (``APP_RELEASED_AT``); ``None`` when it is not known, never made up.
    released_at: dt.datetime | None


class EventListIn(Schema):
    """No input: the last events between apps of the hub of the request."""


class EventLogEntryOut(Schema):
    """An event between apps as System › Logs shows it: when, how it went and where it went; never its content."""

    id: UUID
    at: dt.datetime
    level: Literal["info", "warning", "error"]
    #: The event's own name (``sale.sale.completed``).
    name: str
    #: The app that recorded it, and its name as the business knows it.
    app: str
    app_name: str
    #: What happened to it, in the person's language («Delivered to Invoicing.»).
    detail: str


class EventListOut(Schema):
    entries: list[EventLogEntryOut]


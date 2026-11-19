"""Schemas of the plan's usage (``base.plan.usage``) and the business's usage by day (``base.usage.list``)."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field


class PlanUsageIn(Schema):
    """No input: the plan of the business of the request."""


class LimitOut(Schema):
    #: How much is in use; ``None`` when the Hub does not count it (never a made-up figure).
    used: int | None
    #: The plan's limit; ``None`` when it has none (0 in the SaaS's plan) or the plan is not known.
    limit: int | None


class DatabaseUsageOut(Schema):
    """The size of the business's own database, as the last night measured it."""

    bytes: int | None = Field(description="Its size in bytes; None before the first night measured it.")
    day: dt.date | None = Field(description="The day (UTC) it was measured; None before the first night.")


class FilesUsageOut(Schema):
    """What the business's files and those of its apps take up, as the last night measured it, against its plan."""

    bytes: int | None = Field(description="What they take up, in bytes; None before the first night measured it.")
    day: dt.date | None = Field(description="The day (UTC) it was measured; None before the first night.")
    limit: int | None = Field(description="The space the plan includes, in bytes; None: no limit, or the plan is not known.")
    percent: int | None = Field(description="How much of that space they take up; None without a limit or a figure.")
    status: Literal["within", "near", "full"] | None = Field(
        description="Within the limit, close to it (from 80 %) or reached; None without a limit or a figure."
    )


class ConnectionsUsageOut(Schema):
    """The business's capacity: what it does at once in its database against what it really has."""

    peak_today: int | None = Field(description="The most connections at once today; None: not measured today yet.")
    limit: int | None = Field(
        description="What it really has at once: what its plan includes or, if less, what the service gives. None: the plan is not known."
    )
    busy_last_7_days: int | None = Field(
        description="The times in the last 7 days somebody got an error because there was no room; None: never counted yet."
    )
    busy_since: dt.date | None = Field(
        description="Since when they are counted, when that is less than the 7 days; otherwise None."
    )
    bigger_plan_gives_more: bool = Field(description="Whether a bigger plan would give it more at once.")


class RequestsUsageOut(Schema):
    """The requests the business has served this calendar month (UTC)."""

    this_month: int | None = Field(description="How many; None: never counted yet.")
    since: dt.date | None = Field(description="Since when they are counted, when that is after day 1; otherwise None.")


class ActivityUsageOut(Schema):
    """The people with activity in the business; the plan's places are ``people`` of the same answer."""

    active_now: int | None = Field(description="With activity in the last 5 minutes; None in a demo.")
    last_30_days: int | None = Field(description="In the 30 days the last night measured ends; None before the first night.")
    day: dt.date | None = Field(description="The day (UTC) that night measured; None before the first night.")


class PlanMeterOut(Schema):
    """What an app on says its plan includes this month, such as WhatsApp's messages."""

    key: str = Field(description="The app it is of.")
    label: str = Field(description="What it is called, in the person's language.")
    used: int | None = Field(description="How much of it is spent; None: not measured yet, or it could not be read.")
    limit: int | None = Field(description="How much the plan includes; 0: the plan includes none; None: as above.")
    available: bool = Field(description="False when its app could not be read now.")


class PlanUsageOut(Schema):
    """``base.plan.usage``: the plan's limits (the SaaS's photo, ``plan``) against what the business uses. A figure not
    measured yet comes as None, never as a zero."""

    #: Whether the Hub has the business's plan from erplora.com (a demo, or a business without a photo yet, has not).
    known: bool
    #: A demo: nothing of it is measured, and its data is deleted when it ends.
    demo: bool
    plan_slug: str | None = Field(description="The plan the business is on (free, starter…); None: not known.")
    people: LimitOut
    devices: LimitOut
    apps: LimitOut
    database: DatabaseUsageOut
    files: FilesUsageOut
    connections: ConnectionsUsageOut
    requests: RequestsUsageOut
    activity: ActivityUsageOut
    meters: list[PlanMeterOut]


class UsageListIn(Schema):
    """``GET /internal/usage``: the day (UTC) the SaaS asks for, and where its last page ended."""

    day: dt.date
    cursor: UUID | None = None


class UsageRowOut(Schema):
    id: UUID
    s3_bytes: int
    db_bytes: int
    active_users_1d: int
    active_users_30d: int
    #: What the day's serving tasks counted (``control.HubActivityDaily``); null: nothing counted that day.
    requests: int | None
    peak_connections: int | None
    busy_requests: int | None


class UsageListOut(Schema):
    """One page of the day's use (saas ``hubs/README.md``, «Contrato para el Hub»)."""

    day: dt.date
    hubs: list[UsageRowOut]
    next_cursor: str | None


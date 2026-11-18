"""The bell of the Home: ``base.bell.counters``."""

import datetime as dt

from live.meta import BellSeverity
from ninja import Schema
from pydantic import Field


class BellCountersIn(Schema):
    """No input: the counters above zero this person may see in this hub."""


class BellCounterOut(Schema):
    key: str = Field(description="«<app>.<counter>», or «base.failed_events».")
    app: str
    count: int
    route: str
    label: str
    icon: str
    severity: BellSeverity = Field(description="How grave it is; the gravest goes first.")
    title: str = Field(description="Its heading, with its number, in the person's language.")
    body: str | None = Field(description="One sentence with the consequence; none when the counter says none.")
    action_label: str = Field(description="The label of the button that leads to its route.")
    due: dt.datetime | None = Field(description="Its deadline; none when it has none.")


class BellCountersOut(Schema):
    counters: list[BellCounterOut]
    refresh_every: int | None = Field(
        default=None,
        description="Seconds after which the bell reads its counters again, for one whose figure moves as time passes; "
        "none: only when something changes.",
    )

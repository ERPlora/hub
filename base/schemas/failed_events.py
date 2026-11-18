"""Schemas of the failed events (``base.failed_event.*``)."""

import datetime as dt
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field

from base.schemas.assistant import names


class FailedEventListIn(Schema):
    """A page of the failed events of the hub of the request, newest first."""

    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class FailedEventOut(Schema):
    """A delivery the relay gave up on: which event, from which app to which, how many attempts and the last error."""

    #: The delivery's id: what is resent or discarded.
    id: UUID
    event_id: UUID
    name: str
    source_app: str
    source_app_name: str
    target_app: str
    target_app_name: str
    attempts: int
    occurred_at: dt.datetime
    #: The start of the last error, as the app said it (it may carry a customer's data: who runs the business only).
    last_error: str
    #: ``False`` when the app it was for is no longer on in this business: resending it would fail again.
    retryable: bool


class FailedEventListOut(Schema):
    items: list[FailedEventOut]
    #: How many failed events the hub has, beyond this page.
    total: int


class FailedEventIn(Schema):
    """A failed event of the hub of the request, by its id."""

    id: UUID = Field(title=gettext_noop("Failed event"), json_schema_extra=names("base.failed_event.detail"))


class FailedEventDiscardIn(Schema):
    id: UUID = Field(title=gettext_noop("Failed event"), json_schema_extra=names("base.failed_event.detail"))
    #: Why it is discarded (optional): kept with who and when.
    reason: str = Field(default="", max_length=500)


class FailedEventOutId(Schema):
    id: UUID


class FailedEventRetryAllIn(Schema):
    """No input: every failed event of the hub of the request that can be resent."""


class FailedEventCountOut(Schema):
    #: How many failed events went back to the queue.
    count: int


"""Schemas of a manager's approval (``base.approval.*``)."""

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field


# ── People and permissions: a manager's approval ───────────────────────────────────────────────────────────────────


class ApprovalIn(Schema):
    """A manager approves one refused command: their person and PIN, or their badge."""

    operation: str = Field(max_length=120)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$", description="The refused request's, from requires_elevation.")
    person: str | None = Field(None, max_length=64, description="The id of who approves, from base.approval.approvers.")
    pin: str | None = Field(None, max_length=16)
    badge: str | None = Field(None, max_length=128)


class ApprovalPassOut(Schema):
    """The pass of one use (header X-Elevation-Token), shown once, and who approved."""

    token: str
    approver: str
    expires_in: int = Field(description="Seconds the pass lasts.")


class ApprovalSpendIn(Schema):
    token: str = Field(max_length=128)
    operation: str = Field(max_length=120)
    fingerprint: str = Field(max_length=64)
    figures: dict[str, Any] = Field(
        default_factory=dict, description="The figures of the request its app's sentences name, kept on the record."
    )


class ApprovalSpentOut(Schema):
    spent: bool
    id: str
    approver: str


class ApproversIn(Schema):
    operation: str = Field(max_length=120)


class ApproverOut(Schema):
    id: str = Field(description="The person's id in the hub, to approve with their PIN.")
    name: str
    initials: str


class ApproversOut(Schema):
    people: list[ApproverOut]
    pin_length: Literal[4, 6] = Field(description="Digits of the business's PIN, for the pad.")


class ApprovalListIn(Schema):
    """No input."""


class ApprovalOut(Schema):
    id: UUID
    at: dt.datetime
    action: str = Field(description="What was approved, in words, with the figures of what was done.")
    operation_label: str = Field(description="What the action is called, without figures: the «Action» filter.")
    operation: str
    requested_by: str
    approved_by: str
    way: Literal["pin", "badge"]
    used: bool
    used_at: dt.datetime | None


class ApprovalListOut(Schema):
    approvals: list[ApprovalOut]


class ApprovalExportIn(Schema):
    """What Employees › Approvals keeps on screen: its search and its filters (BASE-F85); none, the whole record."""

    search: str = Field("", max_length=200, description="Words of the action, or of who approved or who asked.")
    at_from: dt.date | None = Field(None, description="From this day, in the business's time zone.")
    at_to: dt.date | None = Field(None, description="Up to this day, included.")
    operation: str = Field("", max_length=120, description="Only the approvals of this action.")
    way: Literal["pin", "badge"] | None = Field(None, description="Only those approved with a PIN or with a badge.")
    used: bool | None = Field(None, description="Only the used ones (true) or the unused ones (false).")


class ApprovalExportOut(Schema):
    filename: str
    content_type: str
    rows: int
    csv: str


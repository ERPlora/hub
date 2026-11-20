"""The queue of records waiting for the AEAT, and what a pass that sends them gives back."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.verifactu.schemas.fields import (
    SEARCH,
    Direction,
    EnvironmentCode,
    OptionalText,
    PageIn,
    RecordRefIn,
    StatusCode,
    TypeCode,
)


class QueueRowOut(Schema):
    id: UUID = Field(description="Id of the record.")
    invoice_number: str = Field(description="Number of its invoice.")
    record_type: TypeCode = Field(description="alta or anulacion.")
    environment: EnvironmentCode = Field(description="testing or production.")
    attempts: int = Field(description="Failed sends so far.")
    status: StatusCode = Field(description="pending or sent.")
    next_attempt_at: dt.datetime | None = Field(
        description="Next attempt; none while a refusal of the gateway waits for a change."
    )
    last_error: str = Field(
        description="Why the last attempt did not go, in the reader's language."
    )
    created_at: dt.datetime = Field(description="When it was sealed.")


class TransmitOut(Schema):
    chains: int = Field(description="Chains that were sent.")
    sent: int = Field(description="Records sent.")
    accepted: int = Field(description="Records the AEAT accepted.")
    accepted_with_errors: int = Field(
        description="Records the AEAT accepted with errors."
    )
    rejected: int = Field(description="Records the AEAT rejected.")
    waiting: int = Field(description="Records still waiting.")
    reason: str = Field(
        description="Why nothing could be sent, as a code (empty when it could)."
    )
    message: str = Field(description="That reason in the reader's language.")


class ContingencyListIn(PageIn):
    search: OptionalText(120) = Field(
        None, description=SEARCH + " Invoice number or the last error."
    )
    environment: EnvironmentCode | None = Field(
        None, description="Only testing or only production."
    )
    sort: Literal["next_attempt_at", "invoice_number", "attempts", "status", "created_at"] | None = Field(
        None, description="Column to sort by (the order they go out by default)."
    )
    dir: Direction = Field("asc", description="asc or desc.")


class ContingencyRetryIn(RecordRefIn):
    """A record of the queue to put out with the next pass."""

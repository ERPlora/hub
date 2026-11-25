"""Schemas of the reactions to Customers' events: what each reads from the event's payload."""

from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field

from apps.reservation.schemas.fields import Reaction


class MergedIn(Reaction):
    """``customer.customer.merged``: the card that stays and the one absorbed."""

    id: UUID | None = Field(None, description="The card that stays.")
    absorbed_id: UUID | None = Field(
        None,
        title=gettext_noop("Duplicate customer"),
        description="The card merged into it.",
    )


class CustomerEventIn(Reaction):
    """``customer.customer.erased``: the card whose personal data was erased."""

    id: UUID | None = Field(None, description="The erased customer's card.")

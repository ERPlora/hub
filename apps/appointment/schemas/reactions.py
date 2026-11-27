"""The reactions to other apps' events: their payloads."""

from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict


class Payload(Schema):
    """Another app's event payload: what this app reads of it (the rest is ignored)."""

    model_config = ConfigDict(extra="ignore")


class MergedIn(Payload):
    id: UUID = Field(description="The customer's card that stays.")
    absorbed_id: UUID = Field(title=gettext_noop("Duplicate customer"), description="The card merged into it.")


class CustomerEventIn(Payload):
    id: UUID = Field(description="The customer's card.")


class MemberEventIn(Payload):
    id: UUID = Field(description="The professional.")


class AtTheTill(Payload):
    actor: str = Field("", description="Who did it at the till, as the outbox keeps them; empty: the platform.")


class SaleFromAppointmentIn(AtTheTill):
    sale_id: UUID
    appointment_id: UUID


class SaleVoidedIn(AtTheTill):
    sale_id: UUID


class OrderVoidedIn(Payload):
    order_id: UUID


class ReactionOut(Schema):
    changed: int = Field(description="How many rows the reaction changed.")

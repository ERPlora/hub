"""Schemas of a card of a separate copy, as its recovery takes it (BASE-F114, hub#1285, hub#1356): what hung from it
there, and the card that comes back."""

from uuid import UUID

from ninja import Field, Schema

from apps.customer.schemas.cards import CustomerDetailOut, CustomerIn
from apps.customer.schemas.custom_fields import FieldIn
from apps.customer.schemas.fields import CustomerRefIn, _text
from apps.customer.schemas.groups import GroupIn
from apps.customer.schemas.tags import TagIn
from base.recovery import RecoveredOut


class GroupOfCopyIn(GroupIn):
    """A group of a card of the copy, as the copy held it: its id there, what the Groups screen's create takes, and
    whether it was offered on the cards."""

    id: UUID | None = Field(None, description="The group's id in the copy.")
    is_active: bool = Field(True, description="Whether the group was offered on the cards.")


class TagOfCopyIn(TagIn):
    """A tag of a card of the copy, as the copy held it: its id there, what the Tags screen's create takes, and whether
    it was offered on the cards."""

    id: UUID | None = Field(None, description="The tag's id in the copy.")
    is_active: bool = Field(True, description="Whether the tag was offered on the cards.")


class FieldValueOfCopyIn(FieldIn):
    """A card's value of an active custom field of the copy: the field's id there, the field as the Fields screen's
    create takes it, and the value."""

    id: UUID | None = Field(None, description="The field's id in the copy.")
    value: _text(10000) = Field(description="The card's value, as text.")


class HungInCopyIn(Schema):
    """What hung from a card in the copy, each named as the copy named it: the business makes its own ids, and the
    copy's tell what it still has."""

    groups: list[GroupOfCopyIn] = Field([], max_length=200, description="The card's groups in the copy.")
    tags: list[TagOfCopyIn] = Field([], max_length=200, description="The card's tags in the copy.")
    field_values: list[FieldValueOfCopyIn] = Field(
        [], max_length=200, description="The card's values of the copy's active custom fields."
    )


class CustomerRecoverIn(CustomerIn, HungInCopyIn):
    """A card of a separate copy the business no longer has: what ``customer.customer.create`` takes and what hung from
    it there."""


class CustomerRestoreIn(CustomerRefIn, HungInCopyIn):
    """A deleted card the business still holds, by its id, and what hung from it in a separate copy: what the business
    deleted since comes back with it."""


class CustomerRecoveredOut(CustomerDetailOut, RecoveredOut):
    """A card back from a separate copy, and the values of its custom fields it came back without, each with why."""

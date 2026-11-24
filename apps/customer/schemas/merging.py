"""Schema of merging a duplicate card into the one that stays."""

from uuid import UUID

from ninja import Field
from pydantic import field_validator

from apps.customer.schemas.fields import (
    ABSORBED_REF_MISSING,
    A_CUSTOMER,
    A_CUSTOMER_REFERENCE,
    CUSTOMER,
    DUPLICATE_CUSTOMER,
    CustomerRefIn,
    Reference,
    _named_unless,
)
from base.schemas.assistant import unless_given


class MergeIn(CustomerRefIn):
    """``id``/``customer`` is the card that stays; ``absorbed_id``/``absorbed`` the duplicate."""

    id: UUID | None = Field(
        None,
        title=CUSTOMER,
        description="The id of the card that stays.",
        json_schema_extra=A_CUSTOMER,
    )
    customer: Reference | None = Field(
        None,
        validate_default=True,
        description="The card that stays: its name (or a part of it), phone or email, when its id is not known.",
        json_schema_extra=unless_given(A_CUSTOMER_REFERENCE, "id"),
    )
    absorbed_id: UUID | None = Field(
        None,
        title=DUPLICATE_CUSTOMER,
        description="The duplicate's id: it is merged into the card that stays.",
        json_schema_extra=A_CUSTOMER,
    )
    absorbed: Reference | None = Field(
        None,
        validate_default=True,
        title=DUPLICATE_CUSTOMER,
        description="The duplicate's name (or a part of it), phone or email, when its id is not known.",
        json_schema_extra=unless_given(A_CUSTOMER_REFERENCE, "absorbed_id"),
    )

    _absorbed_named = field_validator("absorbed")(_named_unless("absorbed_id", ABSORBED_REF_MISSING))

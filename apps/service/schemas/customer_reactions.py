"""Schemas of what the vouchers sold do when a customer's card is merged or erased."""

from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.service.schemas.fields import In


class ReassignIn(In):
    """The payload of ``customer.customer.merged``."""

    id: UUID = Field(description="The customer's card that stays.")
    absorbed_id: UUID = Field(
        title=gettext_noop("Duplicate customer"), description="The card merged into it."
    )


class ReassignedOut(Schema):
    moved: int = Field(description="How many vouchers moved to the card that stays.")


class ForgetCustomerIn(In):
    """The payload of ``customer.customer.erased``."""

    id: UUID = Field(description="The customer's card whose personal data was erased.")


class ForgottenOut(Schema):
    erased: int = Field(description="How many vouchers of the card had a free text emptied.")

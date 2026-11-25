"""Who and what an appointment is for: the customer, the services and the professional, by their id or as a person says
them."""

from typing import Annotated
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field
from pydantic import ValidationInfo, field_validator

from apps.appointment.schemas.fields import A_CUSTOMER, A_SERVICE, MAX_SERVICES, In, Said

SAY_WHICH_CUSTOMER = _("Say which customer: her id, or her name, phone or email.")
SAY_WHICH_STAFF = _("Say which professional: their id, or their name.")
SAY_WHICH_SERVICE = _("Say which service: its id, or its name.")


def _named(value, info: ValidationInfo, id_field: str, message) -> object:
    """The name is required when the id is not given (and the id itself is valid)."""
    if value is None and id_field in info.data and info.data[id_field] is None:
        raise ValueError(str(message))
    return value


class ServiceRefIn(In):
    service_id: UUID | None = Field(None, description="The service's id.", json_schema_extra=A_SERVICE)
    service: Said | None = Field(
        None,
        validate_default=True,
        description="The service's name, when its id is not known (e.g. Haircut).",
        json_schema_extra={"name_of": "service_id"},
    )

    @field_validator("service")
    @classmethod
    def _service(cls, value, info: ValidationInfo):
        return _named(value, info, "service_id", SAY_WHICH_SERVICE)


class CustomerOf(In):
    customer_id: UUID | None = Field(None, description="The customer's card id.", json_schema_extra=A_CUSTOMER)
    customer: Said | None = Field(
        None,
        validate_default=True,
        description="The customer as a person says it: her name or a part of it, her phone or her email.",
    )

    @field_validator("customer")
    @classmethod
    def _customer(cls, value, info: ValidationInfo):
        return _named(value, info, "customer_id", SAY_WHICH_CUSTOMER)


class StaffOf(In):
    staff_id: UUID | None = Field(
        None, description="The professional's id (a staff member)."
    )
    staff: Said | None = Field(
        None,
        validate_default=True,
        description="The professional's name, when the id is not known (e.g. Ana).",
    )

    @field_validator("staff")
    @classmethod
    def _staff(cls, value, info: ValidationInfo):
        return _named(value, info, "staff_id", SAY_WHICH_STAFF)


Services = Annotated[
    list[ServiceRefIn],
    Field(min_length=1, max_length=MAX_SERVICES),
]
OptionalServices = Annotated[
    list[ServiceRefIn] | None,
    Field(min_length=1, max_length=MAX_SERVICES),
]


class ForCustomer(In):
    on_behalf_of_customer: bool = Field(
        False,
        title=gettext_noop("Asked by the customer"),
        description="True when the customer herself asks (WhatsApp, online): her ownership and the policy apply.",
    )
    customer_id: UUID | None = Field(
        None, description="The customer asking (with on_behalf_of_customer).", json_schema_extra=A_CUSTOMER
    )
    customer: Said | None = Field(
        None,
        validate_default=True,
        description="The customer asking, by name, phone or email.",
    )

    @field_validator("customer")
    @classmethod
    def _asking(cls, value, info: ValidationInfo):
        if (
            info.data.get("on_behalf_of_customer")
            and info.data.get("customer_id") is None
            and value is None
        ):
            raise ValueError(str(SAY_WHICH_CUSTOMER))
        return value

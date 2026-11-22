"""What every schema of the service app shares: limits, messages, titles, marks, field types, pages and
references."""

from typing import Annotated, Generic, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _, gettext_noop, pgettext_lazy
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, model_validator

from base.schemas import assistant

T = TypeVar("T")

#: Just under ten trillion minor units of the business's currency (ninety-nine billion with two decimals):
#: far above any price, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: A service lasts at most a day; a buffer, too.
MAX_MINUTES = 1440

SAY_WHICH_SERVICE = _("Say which service: its id, or its name.")
# Its own context: said as its siblings are («su id o su nombre»), not as Inventory says it.
SAY_WHICH_CATEGORY = pgettext_lazy("service", "Say which category: its id, or its name.")
SAY_WHICH_PACKAGE = _("Say which package: its id, or its name.")

#: How the Services screens name the data the models do not (the assistant's card names each datum by its title).
TAX_CATEGORY = gettext_noop("Tax category")
SERVICE = gettext_noop("Service")
CATEGORY = gettext_noop("Category")
PACKAGE = gettext_noop("Package")
ASSIGNMENT = gettext_noop("Professional of a service")
VOUCHER_SOLD = gettext_noop("Voucher sold")
VOUCHER_SESSION = gettext_noop("Voucher session")
VOUCHER_SESSIONS = gettext_noop("Voucher sessions")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a service, a category, a package and a customer by their names, a professional by their full
# name; who does what by the service and the professional; a voucher sold and its sessions by the package, the owner and
# the day it was sold or the service of the session, as two vouchers of one package may be told apart. The sale and its
# line, the appointment, the line of an open check and the refund or the void that gives sessions back are of apps
# Services does not require: its own read names them by theirs (``service.record.get``), the sale by its
# number, a line by what it charges, the appointment as Appointments' cards say it and a refund or a void by its sale.
A_SERVICE = assistant.names("service.service.get")
A_CATEGORY = assistant.names("service.category.get")
A_PACKAGE = assistant.names("service.package.get")
AN_ASSIGNMENT = assistant.names("service.assignment.get", name=("label",))
A_GRANT = assistant.names("service.grant.get", name=("label",))
A_SESSION = assistant.names("service.session.get", name=("label",))
A_MEMBER = assistant.names("staff.member.detail", name=("full_name",))
A_CUSTOMER = assistant.names("customer.customer.detail")
A_SALE = assistant.names("service.record.get", by="sale_id")
A_SALE_LINE = assistant.names("service.record.get", by="sale_line_id")
AN_APPOINTMENT = assistant.names("service.record.get", by="appointment_id")
A_CHECK_LINE = assistant.names("service.record.get", by="order_line_id")
A_RETURN = assistant.names("service.record.get", by="reference")
ONE_RECORD = _("Say one record, by its id.")


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(200, 1)
Said = _text(200, 1)
LongText = Annotated[str, StringConstraints(max_length=2000)]
Code = _text(64)
Note = _text(500)
Color = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^#[0-9a-fA-F]{6}$|^$")
]
Icon = _text(80)
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS, json_schema_extra={"money": True})]
Minutes = Annotated[int, Field(ge=1, le=MAX_MINUTES)]
Buffer = Annotated[int, Field(ge=0, le=MAX_MINUTES)]
Order = Annotated[int, Field(ge=0, le=1_000_000)]


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


def _named(value_id, said, message):
    if value_id is None and said is None:
        raise ValueError(str(message))


# References: by id, or as a person says it


class ServiceRefIn(In):
    id: UUID | None = Field(None, title=SERVICE, description="The service's id.", json_schema_extra=A_SERVICE)
    service: Said | None = Field(
        None,
        description="The service's name, when its id is not known (e.g. said aloud).",
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.service, SAY_WHICH_SERVICE)
        return self


class CategoryRefIn(In):
    id: UUID | None = Field(None, title=CATEGORY, description="The category's id.", json_schema_extra=A_CATEGORY)
    category: Said | None = Field(
        None, description="The category's name, when its id is not known."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.category, SAY_WHICH_CATEGORY)
        return self


class PackageRefIn(In):
    id: UUID | None = Field(None, title=PACKAGE, description="The package's id.", json_schema_extra=A_PACKAGE)
    package: Said | None = Field(
        None, description="The package's name, when its id is not known."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.package, SAY_WHICH_PACKAGE)
        return self


class ByIdIn(In):
    id: UUID = Field(description="The id of the record.")


class NoIn(In):
    pass


class RecordRefIn(In):
    """One record of Sales or Appointments a write of Services names, by its id: exactly one (``service.record.get``)."""

    sale_id: UUID | None = Field(None, description="A sale of Sales.")
    sale_line_id: UUID | None = Field(None, description="A line of a sale of Sales.")
    appointment_id: UUID | None = Field(None, description="An appointment of Appointments.")
    order_line_id: UUID | None = Field(None, description="A line of an open check of Sales.")
    reference: UUID | None = Field(None, description="A refund of Sales, or a sale it voided.")

    @model_validator(mode="after")
    def _one(self):
        return assistant.exactly_one(self, ONE_RECORD)


class DeletedOut(Schema):
    id: UUID

"""The record a write of Sales names, for the assistant's card: by its id (``sale.record.get``), the product of a new
line as the write finds it (``sale.order_line.check``) and the open check a void takes (``sale.order.check_void``)."""

from uuid import UUID

from ninja import Field, Schema
from pydantic import model_validator

from apps.sale.schemas.fields import ONE_RECORD, Closed, Said
from base.schemas.assistant import exactly_one


class RecordRefIn(Closed):
    """One record of Sales, or of an app it asks, that the assistant's card names by its id, or by the words a person
    says of it: exactly one (``sale.record.get``)."""

    department_id: UUID | None = Field(None, description="A section of the open price.")
    quick_note_id: UUID | None = Field(None, description="A quick note.")
    method_id: UUID | None = Field(None, description="A payment method.")
    order_id: UUID | None = Field(None, description="An open check.")
    line_id: UUID | None = Field(None, description="A line of an open check.")
    sale_line_id: UUID | None = Field(None, description="A line of a sale.")
    payment_id: UUID | None = Field(None, description="A tender of a sale.")
    refund_id: UUID | None = Field(None, description="A refund of a sale.")
    product_id: UUID | None = Field(None, description="A product of Inventory.")
    product: Said | None = Field(None, description="A product of Inventory by its SKU or name, as a person says it.")
    service_id: UUID | None = Field(None, description="A service of Services.")
    combo_id: UUID | None = Field(None, description="A menu of Menus.")
    dish_id: UUID | None = Field(None, description="A choice of a menu of Menus.")
    modifier_id: UUID | None = Field(None, description="An option of Modifiers.")
    staff_id: UUID | None = Field(None, description="A member of Staff.")
    appointment_id: UUID | None = Field(None, description="An appointment of Appointments.")
    grant_id: UUID | None = Field(None, description="A voucher sold, of Services.")

    @model_validator(mode="after")
    def _one(self):
        return exactly_one(self, ONE_RECORD)


class LineProductOut(Schema):
    """The product a new line names, found as the write that adds it finds it."""

    id: UUID = Field(description="The product's id.")
    name: str = Field(description="The product's name in the catalog.")


class CheckFoundOut(Schema):
    """The open check a void takes, once its person may void it."""

    id: UUID = Field(description="The open check's id.")

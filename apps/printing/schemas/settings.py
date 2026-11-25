"""Schemas of the printing settings (``printing.settings.*``)."""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema

from apps.printing.schemas.fields import Closed

class SettingsOut(Schema):
    print_receipt_on_sale: bool = Field(description="The receipt prints by itself when a sale is charged.")
    open_drawer_on_sale: bool = Field(description="The drawer opens with the receipt when a sale is charged.")
    receipt_copies: int = Field(description="Copies of each receipt, 1 to 3.")
    receipt_printer_id: UUID | None = Field(description="The printer of the receipts; none = the first active one.")
    kitchen_printer_id: UUID | None = Field(description="The printer of the kitchen; none = the first active one.")
    bar_printer_id: UUID | None = Field(description="The printer of the bar; none = the first active one.")
    label_printer_id: UUID | None = Field(description="The printer of the labels; none = the first active one.")
    updated_at: datetime | None = Field(description="When they were last saved; none = the factory values.")


class SettingsPatchIn(Closed):
    print_receipt_on_sale: bool | None = Field(None, description="Print the receipt by itself at checkout.")
    open_drawer_on_sale: bool | None = Field(None, description="Open the drawer with the receipt at checkout.")
    receipt_copies: int | None = Field(None, ge=1, le=3, description="Copies of each receipt, 1 to 3.")
    receipt_printer: str | None = Field(
        None, max_length=100, description="The receipts' printer by its id or name; null = the first active one."
    )
    kitchen_printer: str | None = Field(
        None, max_length=100, description="The kitchen's printer by its id or name; null = the first active one."
    )
    bar_printer: str | None = Field(
        None, max_length=100, description="The bar's printer by its id or name; null = the first active one."
    )
    label_printer: str | None = Field(
        None, max_length=100, description="The labels' printer by its id or name; null = the first active one."
    )

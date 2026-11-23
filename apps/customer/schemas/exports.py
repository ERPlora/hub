"""The customers' CSV export (CUSTOMER-F09): the filters it takes, the file it gives and its row, whose columns go in
order, each under the header the import reads.

A column marked with a data permission is left out of the file of whoever lacks it (``base.exports``)."""

from ninja import Field, Schema

from .cards import CustomerFilters
from .contact import EMAIL, PHONE


class CustomerExportRow(Schema):
    name: str = Field(description="Name.")
    email: str | None = EMAIL
    phone: str | None = PHONE
    tax_id: str = Field(description="Tax id.")
    company_name: str = Field(description="Company.")
    address: str = Field(description="Street and number.")
    city: str = Field(description="City.")
    postal_code: str = Field(description="Postal code.")
    country: str = Field(description="Country, ISO 3166 two-letter code.")
    lifecycle_stage: str = Field(description="Stage.")
    notes: str = Field(description="Internal notes.")
    source: str = Field(description="Where the customer came from.")
    is_active: str = Field(description="Whether the customer counts as active: true or false.")
    total_purchases: str = Field(description="How many purchases they made.")
    total_spent: str = Field(description="How much they spent, in the business's currency with its decimals.")
    last_purchase_at: str = Field(description="When they last bought.")
    created_at: str = Field(description="When the card was created.")
    groups: str = Field(description="Its groups, by name, separated by «; ».")
    tags: str = Field(description="Its tags, by name, separated by «; ».")


class CustomerExportIn(CustomerFilters):
    pass


class ExportOut(Schema):
    filename: str = Field(description="The file's name.")
    content_type: str = Field(description="The file's type.")
    rows: int = Field(description="How many customers it holds.")
    csv: str = Field(description="The file's contents, CSV with a header row.")

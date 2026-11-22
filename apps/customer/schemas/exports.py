"""The row of the customers' CSV export (CUSTOMER-F09): its columns in order, each under the header the import reads.

A column marked with a data permission is left out of the file of whoever lacks it (``base.exports``)."""

from ninja import Field, Schema

from base.sensitive import CUSTOMER_CONTACT


class CustomerExportRow(Schema):
    name: str = Field(description="Name.")
    email: str | None = Field(None, description="Email.", json_schema_extra=CUSTOMER_CONTACT)
    phone: str | None = Field(None, description="Phone, in international format.", json_schema_extra=CUSTOMER_CONTACT)
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

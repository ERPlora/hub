"""Schemas of the CSV export of the catalog."""

from ninja import Field, Schema

from base.sensitive import COSTS


class ExportOut(Schema):
    filename: str = Field(description="Name of the file.")
    content_type: str = Field(description="Media type.")
    content: str = Field(description="The CSV.")


class ProductRow(Schema):
    """A row of the product export: its columns in order, each under the header the import reads. A column marked
    with a data permission is left out of the file of whoever lacks it (``base.exports``)."""

    name: str
    sku: str
    price: str
    cost: str | None = Field(None, json_schema_extra=COSTS)
    stock: str
    threshold: str
    ean13: str
    description: str
    allergens: str
    unit: str
    tax_category: str
    active: str

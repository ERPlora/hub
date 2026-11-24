"""Schemas of the CSV export of the catalog."""

from ninja import Field, Schema

from base.schemas.assistant import A_HANDED_FILE
from base.sensitive import COSTS


class ExportOut(Schema):
    filename: str = Field(description="Name of the file.")
    content_type: str = Field(description="Media type.")
    content: str = Field(description="The CSV.", json_schema_extra=A_HANDED_FILE)


class ProductRow(Schema):
    """A row of the product export: its columns in order, each under the header the import reads. A column marked
    with a data permission is left out of the file of whoever lacks it (``base.exports``)."""

    name: str = Field(description="The product's name.")
    sku: str = Field(description="Its SKU.")
    price: str = Field(description="Its price, as the screen reads it.")
    cost: str | None = Field(None, description="Its cost, as the screen reads it.", json_schema_extra=COSTS)
    stock: str = Field(description="Its stock, in its unit.")
    threshold: str = Field(description="Its low-stock threshold.")
    ean13: str = Field(description="Its EAN-13, if it has one.")
    description: str = Field(description="Its description.")
    allergens: str = Field(description="Its allergens, by their names.")
    unit: str = Field(description="Its unit of measure.")
    tax_category: str = Field(description="The key of its tax category.")
    active: str = Field(description="Whether it is on sale.")

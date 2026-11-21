"""Schema of the CSV export of the catalog."""

from ninja import Field, Schema


class ExportOut(Schema):
    filename: str = Field(description="Name of the file.")
    content_type: str = Field(description="Media type.")
    content: str = Field(description="The CSV.")

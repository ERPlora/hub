"""Schema of a product's barcode label put in Printing's queue."""

from uuid import UUID

from ninja import Field, Schema


class PrintLabelOut(Schema):
    """The barcode label put in Printing's queue."""

    job_id: UUID = Field(description="The print job of the label, in Printing's queue.")
    printer_name: str | None = Field(
        description="The printer of the «Label» function that will print it; null: none has that function, so "
        "the label waits in the queue until one does."
    )

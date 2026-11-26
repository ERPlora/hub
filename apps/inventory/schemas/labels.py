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
    waits_for_device: bool = Field(
        description="True: nothing has come out yet, as no device that prints its printer is on now (none is set up in "
        "Printing › Devices, or the ones there gave no news in the last 90 s): it waits in the queue and prints once "
        "one is."
    )

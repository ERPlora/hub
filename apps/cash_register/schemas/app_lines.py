"""A line of what another app records in a session (Tips), as the session's summary and its X/Z report show it."""

from ninja import Field, Schema


class AppLine(Schema):
    app: str = Field(description="The app that recorded it, by its registry name (tip).")
    label: str = Field(
        description="The line as the detail and the X/Z report name it, in the reader's language (Tips in cash)."
    )
    amount: int = Field(
        description="In cents, with its sign: what was paid out of the drawer is negative.",
        json_schema_extra={"money": True, "signed": True},
    )

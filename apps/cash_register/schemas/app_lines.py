"""What another app records in a session (Tips): its lines, as the session's summary and its X/Z report show them, and
the mark of each movement it recorded."""

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


class AppMark(Schema):
    app: str = Field(description="The app that recorded it as its own (tip); empty = by hand, or a sale's.")
    app_name: str = Field(description="That app's name in the reader's language (Tips); empty without one.")

"""What removing a price from a list answers (``pricing.price_item.remove``)."""

from ninja import Field

from apps.pricing.schemas import DeletedOut


class PriceRemovedOut(DeletedOut):
    """The price removed, by its id, and what its article costs on that list now, read after removing it."""

    name: str = Field(description="The article's name.")
    price_now: int | None = Field(
        description="What the article costs on that list now, in cents, from the same quantity: a lower quantity of "
        "that list, on a customer group's list the general list's, or else the catalog's; null when it cannot be "
        "read (a service with Services off).",
        json_schema_extra={"money": True},
    )
    price_now_list: str | None = Field(description="The name of the list price_now comes from; null = the catalog's.")
    currency: str = Field(description="The currency of price_now (ISO 4217).")

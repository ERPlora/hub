"""The product's fields that came after the migration its recovery from a separate copy reads since: a copy made
before one of them still gives its products back, without it."""

from base.recovery import held_in_copy

#: Each a column of the product that ``inventory.product.recover`` takes, newer than the declaration's ``reads_since``.
LATER_PRODUCT_FIELDS = ("allergens",)


def later_product_fields(conn, table: str) -> tuple[str, ...]:
    """Those of :data:`LATER_PRODUCT_FIELDS` the copy's product ``table`` holds, through ``conn``, its direct
    connection."""
    return held_in_copy(conn, table, LATER_PRODUCT_FIELDS)

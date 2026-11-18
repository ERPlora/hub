"""What a product's row of a backup or a template carries only when the product has it: its image and its allergens.

``base.blueprint`` reads each product with ``inventory.product.list`` and loads it with
``inventory.product.bulk_create``. The allergens travel by their codes, which that import reads as it reads their
names; a file made before products had allergens has no such key and loads its products without any.
"""

from typing import Any


def optional_fields(product: Any) -> dict:
    """What a product of ``inventory.product.list`` adds to its row only when it has it."""
    fields: dict = {}
    if product.image:
        fields["image"] = product.image
    if product.allergens:
        fields["allergens"] = list(product.allergens)
    return fields


def allergens_cell(row: dict) -> dict:
    """The allergens of a product's row of a file as the cell ``inventory.product.bulk_create`` reads, or nothing.

    A list carries their codes and a text their names («Gluten, leche»); anything else brings none.
    """
    written = row.get("allergens")
    if isinstance(written, str):
        return {"allergens": written}
    if isinstance(written, list):
        return {"allergens": ", ".join(code for code in written if isinstance(code, str))}
    return {}

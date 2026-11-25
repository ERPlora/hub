"""What a product's row of a backup or a template carries only when the product has it: its image, its allergens,
being hidden from the website, being a service and a price that is not for one of its unit.

``base.blueprint`` reads each product with ``inventory.product.list`` and loads it with
``inventory.product.bulk_create``. The allergens travel by their codes, which that import reads as it reads their
names; a file made before products had allergens has no such key and loads its products without any. The type and what
the price refers to enter with that import too, so a product is never there at another price. The categories and the
marks, which that import does not take, load with ``inventory.product.update``.
"""

from typing import Any

#: The type a product is imported with when its row says none.
PHYSICAL = "physical"


def optional_fields(product: Any) -> dict:
    """What a product of ``inventory.product.list`` adds to its row only when it has it."""
    fields: dict = {}
    if product.image:
        fields["image"] = product.image
    if product.allergens:
        fields["allergens"] = list(product.allergens)
    if not product.show_on_website:
        fields["show_on_website"] = False
    if product.product_type != PHYSICAL:
        fields["product_type"] = product.product_type
    if product.price_quantity != 1:
        fields["price_quantity"] = f"{product.price_quantity.normalize():f}"
    if product.pricing_unit != product.unit:
        fields["pricing_unit"] = product.pricing_unit
    return fields


def allergens_cell(row: dict) -> dict:
    """The allergens of a product's row of a file as the cell ``inventory.product.bulk_create`` reads, or nothing.

    A list carries their codes and a text their names («Gluten, leche»); anything else brings none.
    """
    written = row.get("allergens")
    if isinstance(written, str):
        return {"allergens": written}
    if isinstance(written, list):
        return {"allergens": ", ".join(str(code) for code in written)}
    return {}


def category_names(row: dict) -> list[str]:
    """The categories a product's row lists by name; what is not a name is left out."""
    names = row.get("categories")
    return [name for name in names if isinstance(name, str) and name.strip()] if isinstance(names, list) else []


def marks(row: dict) -> dict:
    """The marks of a product's row that differ from those of a product just imported."""
    changes = {mark: False for mark in ("is_active", "show_on_website") if row.get(mark) is False}
    if isinstance(row.get("track_stock"), bool):
        changes["track_stock"] = row["track_stock"]
    return changes

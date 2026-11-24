"""Each item of the website's catalog, from a row of its source's sale list: Services' offered services and Inventory's
products on sale, a product with its photo, its description and its allergens' codes. The price is in the currency's
minor unit; the page prices it and names the allergens in the visitor's language (``render.catalog_view``)."""

from typing import Any

#: How Services' pricing reads on the page.
SERVICE_PRICE_KINDS = {"fixed": "fixed", "from": "from", "hourly": "hourly", "free": "free", "variable": "none"}


def service_item(row: Any) -> dict[str, Any]:
    """A row of ``service.service.list_for_sale``: its name, price and duration."""
    kind = SERVICE_PRICE_KINDS.get(row.pricing_type, "none")
    return {"name": row.name, "price": row.price, "price_kind": kind, "minutes": row.duration_minutes}


def product_item(row: Any) -> dict[str, Any]:
    """A row of ``inventory.product.list_for_sale``: its name, price, description, photo and allergens."""
    return {
        "name": row.name,
        "price": row.price,
        "price_kind": "fixed" if row.price else "none",
        "minutes": None,
        "description": row.description,
        "image_url": row.image_url,
        "allergens": list(row.allergens),
    }

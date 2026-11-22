"""What a separate copy of the business gives back to Price Lists (BASE-F114)."""

from psycopg import sql

from apps.inventory import queries as inventory_queries
from apps.inventory.models import Product
from apps.pricing.models import PriceItem
from apps.pricing.queries.other_apps import services_standing_for

#: What a price of a separate copy is read with: its id there, what ``pricing.price_item.add`` takes and its product's
#: SKU there (``None`` for a service's), each a column since ``0001_initial``.
PRICE_FIELDS = ("id", "price_list_id", "product_id", "service_id", "price", "min_quantity", "sku")


def prices_in_copy(conn) -> list[dict]:
    """Each price of a separate copy of the business that counts there (of a service, or of a product Inventory had not
    deleted: ``live_items``), with what ``PRICE_FIELDS`` names; nothing where the app's table is not there. ``conn`` is
    the copy's direct, read-only connection: it is read by its own SQL over the models' names, never the ORM."""
    item, product = PriceItem._meta, Product._meta
    if conn.execute("SELECT to_regclass(%s)", [item.db_table]).fetchone()[0] is None:
        return []

    def column(meta, field: str) -> sql.Identifier:
        return sql.Identifier(meta.get_field(field).column)

    read = sql.SQL(
        "SELECT {columns} FROM {items} i LEFT JOIN {products} p ON p.{product_pk} = i.{product_id}"
        " WHERE i.{product_id} IS NULL OR NOT p.{deleted} ORDER BY i.{item_pk}"
    ).format(
        columns=sql.SQL(", ").join(
            [
                *(
                    sql.SQL("i.{}").format(column(item, field))
                    for field in ("id", "price_list", "product", "service_id", "price", "min_quantity")
                ),
                sql.SQL("p.{}").format(column(product, "sku")),
            ]
        ),
        items=sql.Identifier(item.db_table),
        products=sql.Identifier(product.db_table),
        product_pk=column(product, "id"),
        product_id=column(item, "product"),
        deleted=column(product, "is_deleted"),
        item_pk=column(item, "id"),
    )
    return [dict(zip(PRICE_FIELDS, row, strict=True)) for row in conn.execute(read)]


def prices_not_in_business(prices: list[dict]) -> list[dict]:
    """The prices of a separate copy (``prices_in_copy``) the business no longer has, in their order, each as
    ``pricing.price_item.add`` takes it with its ``id`` there: its list, its one article (a product or a service), its
    price and its from quantity. Its product is the business's that stands for the copy's (Inventory's
    ``products_standing_for``), and its service too (Services', ``services_standing_for``). Not lacking: one the
    business still holds, nor one whose place (its list, its article and its from quantity) the business has taken
    again, at whatever price: that one stays as the business has it."""
    held = set(PriceItem.objects.filter(pk__in=[one["id"] for one in prices]).values_list("pk", flat=True))
    taken = set(
        PriceItem.objects.filter(price_list_id__in={one["price_list_id"] for one in prices}).values_list(
            "price_list_id", "product_id", "service_id", "min_quantity"
        )
    )
    here = inventory_queries.recovery.products_standing_for({one["product_id"]: one["sku"] for one in prices if one["product_id"]})
    serving = services_standing_for({one["service_id"] for one in prices if one["service_id"]})
    lacking = []
    for one in prices:
        product = here.get(one["product_id"], one["product_id"])
        service = serving.get(one["service_id"], one["service_id"])
        if one["id"] in held or (one["price_list_id"], product, service, one["min_quantity"]) in taken:
            continue
        lacking.append(
            {
                "id": one["id"],
                "price_list_id": one["price_list_id"],
                **({"product_id": product} if product else {"service_id": service}),
                "price": one["price"],
                "min_quantity": one["min_quantity"],
            }
        )
    return lacking

"""What a separate copy of the business gives back (BASE-F114, INVENTORY-F01, INVENTORY-F07)."""

from uuid import UUID

from psycopg import sql

from apps.inventory.models import Category, Product, ProductCategory
from apps.inventory.copy_columns import LATER_PRODUCT_FIELDS, later_product_fields
from apps.tax.models import TaxCategory
from base.recovery import brought_back

#: What ``inventory.category.recover`` takes of a category of a separate copy, each a column since ``0001_initial``,
#: and its tax category, by its key here.
CATEGORY_FIELDS = ("name", "slug", "description", "icon", "color", "order")

#: What ``inventory.product.recover`` takes of a product of a separate copy (``products_in_copy``) that every copy it
#: reads holds (``reads_since``), besides the later fields a copy may predate (``copy_columns``). Not its stock (a
#: count says today's, INVENTORY-F14) nor its «sold out» (a day's state).
PRODUCT_FIELDS = (
    "name",
    "sku",
    "ean13",
    "description",
    "product_type",
    "price",
    "cost",
    "low_stock_threshold",
    "unit",
    "price_quantity",
    "pricing_unit",
    "track_stock",
    "is_active",
    "image",
)


def categories_in_copy(conn) -> list[dict]:
    """Each live category of a separate copy of the business, with its ``id`` there, what its recover takes, its tax
    category's id there (``tax_category``) and the copy's live products in it (``product_ids``); nothing where the
    app's table is not there. ``conn`` is the copy's direct, read-only connection: it is read by its own SQL."""
    table = Category._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return []
    read = ("id", *CATEGORY_FIELDS, "tax_category")
    rows = conn.execute(_live_in_copy(Category, read))
    categories = [dict(zip(read, row, strict=True)) | {"product_ids": []} for row in rows]
    by_id = {one["id"]: one for one in categories}
    for _link_id, product_id, category_id in conn.execute(_live_links_in_copy()):
        by_id[category_id]["product_ids"].append(product_id)
    return categories


def products_in_copy(conn) -> list[dict]:
    """Each live product of a separate copy of the business, with its ``id`` there, what ``inventory.product.recover``
    takes, its tax category's id there (``tax_category``) and the ids of its live categories there
    (``category_ids``); and with every one, the copy's live categories by id (``copy_categories``), to tell its own from
    one the business made again with its name. Nothing where the app's table is not there. ``conn`` is the copy's
    direct, read-only connection: it is read by its own SQL over the models' names, never the ORM."""
    table = Product._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return []
    read = ("id", *PRODUCT_FIELDS, *later_product_fields(conn, table), "tax_category")
    copy_categories = category_names_in_copy(conn)
    products = [
        dict(zip(read, row, strict=True)) | {"category_ids": [], "copy_categories": copy_categories}
        for row in conn.execute(_live_in_copy(Product, read))
    ]
    by_id = {one["id"]: one for one in products}
    for _link_id, product_id, category_id in conn.execute(_live_links_in_copy()):
        by_id[product_id]["category_ids"].append(category_id)
    return products


def product_links_in_copy(conn) -> list[dict]:
    """Each link of a live product to a live category in a separate copy of the business, with its ``id`` there, the
    product's and the category's ids there; and with every one, the copy's live categories by id (``copy_categories``),
    to pair each with the business's as the categories' part does. Nothing where the links' table is not there.
    ``conn`` is the copy's direct, read-only connection: it is read by its own SQL over the models' names."""
    if conn.execute("SELECT to_regclass(%s)", [ProductCategory._meta.db_table]).fetchone()[0] is None:
        return []
    copy_categories = category_names_in_copy(conn)
    return [
        {"id": link_id, "product_id": product_id, "category_id": category_id, "copy_categories": copy_categories}
        for link_id, product_id, category_id in conn.execute(_live_links_in_copy())
    ]


def category_names_in_copy(conn) -> dict[UUID, str]:
    """The live categories of a separate copy of the business by id, with their name there: what pairs each with the
    business's (``categories_standing_for``). ``conn`` is the copy's direct, read-only connection."""
    return dict(conn.execute(_live_in_copy(Category, ("id", "name"))).fetchall())


def _live_in_copy(model, read: tuple[str, ...]) -> sql.Composed:
    """The ``read`` columns of the copy's live rows of ``model``, by id."""
    column = {field: sql.Identifier(model._meta.get_field(field).column) for field in (*read, "id", "is_deleted")}
    return sql.SQL("SELECT {} FROM {} WHERE NOT {} ORDER BY {}").format(
        sql.SQL(", ").join(column[field] for field in read),
        sql.Identifier(model._meta.db_table),
        column["is_deleted"],
        column["id"],
    )


def _live_links_in_copy() -> sql.Composed:
    """The copy's ``(link, product, category)`` links whose product and category are both live there; a deleted product
    keeps its links."""
    link, product, category = ProductCategory._meta, Product._meta, Category._meta

    def column(meta, field: str) -> sql.Identifier:
        return sql.Identifier(meta.get_field(field).column)

    return sql.SQL(
        "SELECT l.{link_pk}, l.{product_id}, l.{category_id} FROM {links} l"
        " JOIN {products} p ON p.{product_pk} = l.{product_id} JOIN {categories} c ON c.{category_pk} = l.{category_id}"
        " WHERE NOT p.{product_deleted} AND NOT c.{category_deleted} ORDER BY l.{product_id}, l.{category_id}"
    ).format(
        link_pk=column(link, "id"),
        product_id=column(link, "product"),
        category_id=column(link, "category"),
        links=sql.Identifier(link.db_table),
        products=sql.Identifier(product.db_table),
        categories=sql.Identifier(category.db_table),
        product_pk=column(product, "id"),
        category_pk=column(category, "id"),
        product_deleted=column(product, "is_deleted"),
        category_deleted=column(category, "is_deleted"),
    )


def categories_not_in_business(categories: list[dict]) -> list[dict]:
    """The categories of a separate copy (``categories_in_copy``) the business lacks, in their order, each as
    ``inventory.category.recover`` takes it here, with its ``id`` there: the key of its tax category, and the products
    of the copy in it that the business still holds deleted and will restore (``products_deleted_in_business``), so
    they come back inside it. One it still has live (renamed or not), or made again with its name, is not lacking."""
    held = _categories_held({one["id"]: one["name"] for one in categories})
    lacking = [one for one in categories if one["id"] not in held]
    keys = _tax_keys({one["tax_category"] for one in lacking})
    restorable = _restorable({product for one in lacking for product in one["product_ids"]})
    created = []
    for one in lacking:
        record = {field: one[field] for field in ("id", *CATEGORY_FIELDS)}
        if (key := keys.get(one["tax_category"])) is not None:
            record["tax_category_key"] = key
        record["product_ids"] = [product for product in one["product_ids"] if product in restorable]
        created.append(record)
    return created


def _categories_held(copy: dict[UUID, str]) -> dict[UUID, UUID]:
    """The business's live category that is each of the ``copy``'s (``{id there: name there}``): the same while it is
    live, renamed or not; else one made again with its name (the case and the spaces aside) that is none of the copy's,
    each standing for one only, the oldest made again for the copy's oldest."""
    held: dict[UUID, UUID] = {}
    made_again: dict[str, list[UUID]] = {}
    for pk, name in Category.objects.filter(is_deleted=False).order_by("created_at", "id").values_list("pk", "name"):
        if pk in copy:
            held[pk] = pk
        else:
            made_again.setdefault(_same_name(name), []).append(pk)
    for one in sorted(pk for pk in copy if pk not in held):
        if twins := made_again.get(_same_name(copy[one])):
            held[one] = twins.pop(0)
    return held


def product_links_not_in_business(links: list[dict]) -> list[dict]:
    """The links of a separate copy (``product_links_in_copy``) a category brought back lacks, in their order, each as
    ``inventory.product_category.add`` takes it here, with its ``id`` there: the copy's category is no longer live here
    and its place is taken by one a recovery brought back (``_categories_held``, the same pairing as the categories'
    part); the product is one the business keeps live, out of it. A category the business kept, or made again by
    hand, stays as the business has it, and a product's other categories are never touched."""
    if not links:
        return []
    standing = categories_standing_for(links[0]["copy_categories"])
    wanted = [(one, standing[one["category_id"]]) for one in links if one["category_id"] in standing]
    asked = {one["product_id"] for one, _here in wanted}
    live = set(Product.objects.filter(pk__in=asked, is_deleted=False).values_list("pk", flat=True))
    back = set(standing.values())
    linked = set(ProductCategory.objects.filter(product__in=asked, category__in=back).values_list("product", "category"))
    return [
        {"id": one["id"], "product_id": one["product_id"], "category_id": here}
        for one, here in wanted
        if one["product_id"] in live and (one["product_id"], here) not in linked
    ]


def categories_standing_for(copy: dict[UUID, str]) -> dict[UUID, UUID]:
    """The business's category that stands for each of a separate copy's it no longer holds live, as ``{id there: id
    here}``: the live one with its name that a recovery brought back (``brought_back``), paired as the categories' part
    pairs them (``_categories_held``), which is why ``copy`` is every live category of the copy, by name
    (``category_names_in_copy``). One the business made again by hand is its own, set up as it chose: it stands for
    none. A category still live here is itself, and is not in the result. For the apps whose records hang from a
    category to give each back to the category it is now."""
    stand_ins = {there: here for there, here in _categories_held(copy).items() if there != here}
    back = {
        pk
        for pk, created_by in Category.objects.filter(pk__in=stand_ins.values()).values_list("pk", "created_by")
        if brought_back(created_by)
    }
    return {there: here for there, here in stand_ins.items() if here in back}


def _same_name(name: str) -> str:
    """A name as two that are the same compare: single spaces, the case aside."""
    return " ".join(name.split()).casefold()


def _tax_keys(tax_category_ids: set) -> dict[UUID, str]:
    return dict(TaxCategory.objects.filter(pk__in=tax_category_ids).values_list("pk", "key"))


def _restorable(product_ids) -> set[UUID]:
    """Of ``product_ids``, those the business holds deleted and that can come back the same: never one whose SKU or
    EAN-13 another live product holds now (made again by hand since: that one stays)."""
    live = Product.objects.filter(is_deleted=False)
    deleted = (
        Product.objects.filter(pk__in=product_ids, is_deleted=True)
        .exclude(sku__in=live.values("sku"))
        .exclude(ean13__in=live.filter(ean13__isnull=False).values("ean13"))
    )
    return set(deleted.values_list("pk", flat=True))


def products_deleted_in_business(products: list[dict]) -> list[dict]:
    """The products of a separate copy (``products_in_copy``) the business still holds deleted (INVENTORY-F04) and
    that can come back the same (``_restorable``), in their order, for ``inventory.product.restore``."""
    held = _restorable([one["id"] for one in products])
    return [one for one in products if one["id"] in held]


def products_not_in_business(products: list[dict]) -> list[dict]:
    """The products of a separate copy (``products_in_copy``) the business lacks, in their order, each as
    ``inventory.product.recover`` takes it here. Not lacking: any product it still holds, live or deleted (it comes back
    the same, ``products_deleted_in_business``), nor one with the SKU or the EAN-13 of a live one (the code is the
    article's identity: one made again by hand, or brought back already). Lacking: one gone altogether. Each takes the
    key of its tax category (Taxes never deletes one; one no longer active is the create's to refuse, and one without
    any names none) and its categories here: the same while live, else the one with its name, brought back just before
    it or made again by hand (``_categories_held``); one gone and not back is left out (INVENTORY-F07)."""
    held = set(Product.objects.filter(pk__in=[one["id"] for one in products]).values_list("pk", flat=True))
    live = Product.objects.filter(is_deleted=False)
    skus = set(live.filter(sku__in=[one["sku"] for one in products]).values_list("sku", flat=True))
    codes = [one["ean13"] for one in products if one["ean13"]]
    barcodes = set(live.filter(ean13__in=codes).values_list("ean13", flat=True))
    lacking = [
        one
        for one in products
        if one["id"] not in held and one["sku"] not in skus and not (one["ean13"] and one["ean13"] in barcodes)
    ]
    keys = _tax_keys({one["tax_category"] for one in lacking})
    categories = _categories_held(next((one["copy_categories"] for one in products), {}))
    return [_as_created(one, keys.get(one["tax_category"]), categories) for one in lacking]


def products_standing_for(skus: dict[UUID, str]) -> dict[UUID, UUID]:
    """The business's product that stands for each of a separate copy's products (``{id there: SKU there}``) it no
    longer holds live, as ``{id there: id here}``: the live one with its SKU, the article's identity, that a recovery
    made (``brought_back``), as ``products_not_in_business`` has one the business no longer holds at all made again
    with another id (INVENTORY-F01). One the business made again by hand is its own, set up as it chose: it stands for
    none. A product still live here is itself, and is not in the result. For the apps whose records hang from a
    product to give each back to the product it is now."""
    live = set(Product.objects.filter(pk__in=list(skus), is_deleted=False).values_list("pk", flat=True))
    wanted = {sku: there for there, sku in skus.items() if there not in live}
    made = Product.objects.filter(sku__in=list(wanted), is_deleted=False).values_list("sku", "pk", "created_by")
    return {wanted[sku]: pk for sku, pk, created_by in made if brought_back(created_by)}


def _as_created(product: dict, tax_key: str | None, categories: dict[UUID, UUID]) -> dict:
    """``product`` of the copy as ``inventory.product.recover`` takes it in the business, with its ``id`` there."""
    created = {field: product[field] for field in ("id", *PRODUCT_FIELDS, *LATER_PRODUCT_FIELDS) if field in product}
    created["category_ids"] = [categories[one] for one in product["category_ids"] if one in categories]
    if tax_key is not None:
        created["tax_category_key"] = tax_key
    return created

"""What Menus gives back from a separate copy of the business (BASE-F114, COMBO-F15)."""

from collections import Counter
from uuid import UUID

from psycopg import sql

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo
from apps.inventory.models import Product
from apps.inventory.queries.recovery import products_standing_for
from apps.tax.models import TaxCategory

#: What a menu of a separate copy is read with besides its id and its tax category: what ``combo.combo.recover`` takes,
#: each a column since ``0002_combo_image`` (its image).
COMBO_FIELDS = ("name", "kitchen_name", "price", "supply_kind", "sort_order", "is_active", "image")

#: What a course of a separate copy is read with besides its id and its menu: what ``combo.group.recover`` takes, each a
#: column since ``0001_initial``.
GROUP_FIELDS = ("name", "min_choices", "max_choices", "allow_repeat")


def combos_in_copy(conn) -> list[dict]:
    """Each menu of a separate copy of the business, in the menus' order, with its id, what ``COMBO_FIELDS`` names and
    the id there of its tax category (``tax_category_id``); nothing where the app's table is not there. ``conn`` is the
    copy's direct, read-only connection."""
    rows = _rows_in_copy(conn, Combo._meta, ("id", *COMBO_FIELDS, "tax_category"), ("sort_order", "name", "id"))
    return [dict(zip(("id", *COMBO_FIELDS, "tax_category_id"), row, strict=True)) for row in rows]


def groups_in_copy(conn) -> list[dict]:
    """Each course of a separate copy of the business, menu by menu in its order, with its id, its menu's
    (``combo_id``) and what ``GROUP_FIELDS`` names; nothing where the app's table is not there. ``conn`` is the copy's
    direct, read-only connection."""
    rows = _rows_in_copy(conn, ChoiceGroup._meta, ("id", "combo", *GROUP_FIELDS), ("combo", "sort_order", "id"))
    return [dict(zip(("id", "combo_id", *GROUP_FIELDS), row, strict=True)) for row in rows]


def _rows_in_copy(conn, meta, read: tuple[str, ...], order: tuple[str, ...]) -> list[tuple]:
    """The ``read`` columns of every row of the model ``meta`` in a separate copy, by ``order``; none where its table is
    not there. It is read by its own SQL over the model's names, never the ORM: the copy is no business."""
    if conn.execute("SELECT to_regclass(%s)", [meta.db_table]).fetchone()[0] is None:
        return []

    def columns(fields: tuple[str, ...]) -> sql.Composed:
        return sql.SQL(", ").join(sql.Identifier(meta.get_field(field).column) for field in fields)

    query = sql.SQL("SELECT {} FROM {} ORDER BY {}")
    return conn.execute(query.format(columns(read), sql.Identifier(meta.db_table), columns(order))).fetchall()


def combos_not_in_business(combos: list[dict]) -> list[dict]:
    """The menus of a separate copy (``combos_in_copy``) the business no longer has, in their order, each as
    ``combo.combo.recover`` takes it with its ``id`` there: the key of its tax category (Taxes never deletes one; one
    turned off since is the create's to refuse) and which of the copy's it stands for. Not lacking: one the business
    still holds or a recovery made again for it, renamed or not; nor one the business made again by hand with its name,
    the case and the spaces aside. Names are not unique, so each made again stands for one: the copy's oldest first."""
    if not combos:
        return []
    ids = [one["id"] for one in combos]
    here = set(Combo.objects.filter(pk__in=ids).values_list("pk", flat=True)) | set(_standing_for(Combo, ids))
    others = Combo.objects.exclude(pk__in=ids).exclude(stands_for__in=ids).values_list("name", flat=True)
    twins = Counter(_alike(name) for name in others)
    for one in sorted(combos, key=lambda menu: menu["id"]):
        if one["id"] not in here and twins[_alike(one["name"])]:
            twins[_alike(one["name"])] -= 1
            here.add(one["id"])
    keys = dict(TaxCategory.objects.filter(pk__in={one["tax_category_id"] for one in combos}).values_list("pk", "key"))
    return [
        {field: one[field] for field in ("id", *COMBO_FIELDS)}
        | {"tax_category_key": keys.get(one["tax_category_id"]), "stands_for": one["id"]}
        for one in combos
        if one["id"] not in here
    ]


def _alike(name: str) -> str:
    """A name as two that are the same compare: single spaces, the case aside."""
    return " ".join(name.split()).casefold()


def groups_not_in_business(groups: list[dict]) -> list[dict]:
    """The courses of a separate copy (``groups_in_copy``) their menu no longer has, in their order, each as
    ``combo.group.recover`` takes it with its ``id`` there and which of the copy's it stands for. Its menu is the
    business's that stands for the copy's: the same while held, else the one a recovery made again for it; the copy's
    own where none does, which the create then refuses as not found. Not lacking: one the business still holds or a
    recovery made again for it, renamed or not; nor one whose name its menu has again, the case aside, as the menu
    builder takes no second one: the business's stays."""
    if not groups:
        return []
    ids = [one["id"] for one in groups]
    held = set(ChoiceGroup.objects.filter(pk__in=ids).values_list("pk", flat=True))
    here = held | set(_standing_for(ChoiceGroup, ids))
    menus = _standing_for(Combo, {one["combo_id"] for one in groups})
    wanted = [(one, menus.get(one["combo_id"], one["combo_id"])) for one in groups if one["id"] not in here]
    named = ChoiceGroup.objects.filter(combo_id__in={menu for _one, menu in wanted}).values_list("combo_id", "name")
    taken = {(menu, name.lower()) for menu, name in named}
    return [
        {field: one[field] for field in ("id", *GROUP_FIELDS)} | {"combo_id": menu, "stands_for": one["id"]}
        for one, menu in wanted
        if (menu, one["name"].lower()) not in taken
    ]


def _standing_for(model, ids) -> dict[UUID, UUID]:
    """The business's menu or course (``model``) a recovery made again for each of a separate copy's (``ids``, there),
    as ``{id there: id here}`` (``stands_for``), renamed or not; the oldest if one was made twice. A recovery only makes
    one the business no longer holds, so one still held is in none. One the business made again by hand is its own, set
    up as it chose: it stands for none."""
    made = model.objects.filter(stands_for__in=ids).order_by("created_at", "id")
    standing: dict[UUID, UUID] = {}
    for there, here in made.values_list("stands_for", "pk"):
        standing.setdefault(there, here)
    return standing


#: What a choice of a separate copy is read with: its id there, what ``combo.option.create`` takes and its product's SKU
#: there, each a column since ``0001_initial``.
OPTION_FIELDS = ("id", "group_id", "product_id", "price_delta", "is_available", "sku")


def options_in_copy(conn) -> list[dict]:
    """Each choice of a separate copy of the business, of a product Inventory had not deleted there, with what
    ``OPTION_FIELDS`` names, course by course in its order; nothing where the app's table is not there. ``conn`` is the
    copy's direct, read-only connection: it is read by its own SQL over the models' names, never the ORM."""
    option, product = ChoiceOption._meta, Product._meta
    if conn.execute("SELECT to_regclass(%s)", [option.db_table]).fetchone()[0] is None:
        return []

    def column(meta, field: str) -> sql.Identifier:
        return sql.Identifier(meta.get_field(field).column)

    read = sql.SQL(
        "SELECT {columns} FROM {options} o JOIN {products} p ON p.{product_pk} = o.{product_id}"
        " WHERE NOT p.{deleted} ORDER BY o.{group_id}, o.{order}, o.{option_pk}"
    ).format(
        columns=sql.SQL(", ").join(
            [
                *(
                    sql.SQL("o.{}").format(column(option, field))
                    for field in ("id", "group", "product", "price_delta", "is_available")
                ),
                sql.SQL("p.{}").format(column(product, "sku")),
            ]
        ),
        options=sql.Identifier(option.db_table),
        products=sql.Identifier(product.db_table),
        product_pk=column(product, "id"),
        product_id=column(option, "product"),
        deleted=column(product, "is_deleted"),
        group_id=column(option, "group"),
        order=column(option, "sort_order"),
        option_pk=column(option, "id"),
    )
    return [dict(zip(OPTION_FIELDS, row, strict=True)) for row in conn.execute(read)]


def options_not_in_business(options: list[dict]) -> list[dict]:
    """The choices of a separate copy (``options_in_copy``) the business no longer offers, in their order, each as
    ``combo.option.create`` takes it with its ``id`` there. Its course is the business's that stands for the copy's: the
    same while held, else the one a recovery made again for it; the copy's own where none does, which the create then
    refuses as not found. Its product is the business's that stands for the copy's (Inventory's
    ``products_standing_for``): the same while live, else the one a recovery made again with its SKU. Not lacking: one
    the business still holds, even with another product it was given since, nor one whose product the business offers
    again in that course: it stays as the business has it."""
    held = set(ChoiceOption.objects.filter(pk__in=[one["id"] for one in options]).values_list("pk", flat=True))
    courses = _standing_for(ChoiceGroup, {one["group_id"] for one in options})
    products = products_standing_for({one["product_id"]: one["sku"] for one in options})
    wanted = [
        (one, courses.get(one["group_id"], one["group_id"]), products.get(one["product_id"], one["product_id"]))
        for one in options
        if one["id"] not in held
    ]
    taken = set(
        ChoiceOption.objects.filter(group_id__in={course for _one, course, _product in wanted}).values_list(
            "group_id", "product_id"
        )
    )
    return [
        {
            "id": one["id"],
            "group_id": course,
            "product_id": product,
            "price_delta": one["price_delta"],
            "is_available": one["is_available"],
        }
        for one, course, product in wanted
        if (course, product) not in taken
    ]

"""A separate copy of the business (BASE-F114): what Modifiers gives back from it."""

from uuid import UUID

from psycopg import sql

from apps.inventory.queries.recovery import categories_standing_for, category_names_in_copy, products_standing_for
from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.tax.models import TaxCategory
from base.recovery import at_work, brought_back

from .copy_columns import LATER_OPTION_FIELDS, later_option_fields

#: What a group of a separate copy is read with besides its id: what ``modifier.group.create`` takes, each a column since
#: ``0001_initial``.
GROUP_COPY_FIELDS = ("name", "kitchen_name", "min_choices", "max_choices", "allow_repeat", "sort_order")

#: What each option of a group of a separate copy is read with besides its tax category: what ``modifier.option.create``
#: takes but its group, each a column since ``0001_initial``.
OPTION_COPY_FIELDS = ("name", "kitchen_name", "price_delta", "is_default", "sort_order")

#: What a group hung from a product in a separate copy is read with: its link's id there, what
#: ``modifier.link.attach`` takes and its product's SKU there, each a column since ``0001_initial``.
LINK_FIELDS = ("id", "group_id", "product_id", "sku")

#: What a group hung from a category in a separate copy is read with: its link's id there and what
#: ``modifier.link.attach`` takes, each a column since ``0001_initial``.
CATEGORY_LINK_FIELDS = ("id", "group_id", "category_id")


def groups_in_copy(conn) -> list[dict]:
    """Each group of a separate copy of the business, by id, with what ``GROUP_COPY_FIELDS`` names and its options there
    (``options``) in the order they were added, each with what ``OPTION_COPY_FIELDS`` names, the later fields the copy
    holds (``copy_columns``) and the id of its own tax category (``tax_category_id``); nothing where the app's table is
    not there. ``conn`` is the copy's direct, read-only connection: read by its own SQL over the models' names."""
    group, option = ModifierGroup._meta, ModifierOption._meta
    if conn.execute("SELECT to_regclass(%s)", [group.db_table]).fetchone()[0] is None:
        return []
    groups = [
        dict(zip(("id", *GROUP_COPY_FIELDS), row, strict=True)) | {"options": []}
        for row in conn.execute(_by_id(group, ("id", *GROUP_COPY_FIELDS)))
    ]
    by_id, read = {one["id"]: one for one in groups}, (*OPTION_COPY_FIELDS, *later_option_fields(conn))
    for group_id, *row in conn.execute(_by_id(option, ("group", *read, "tax_category"))):
        by_id[group_id]["options"].append(dict(zip((*read, "tax_category_id"), row, strict=True)))
    return groups


def group_names_in_copy(conn) -> dict[UUID, str]:
    """Every group of a separate copy of the business by id, with its name there: what pairs each with the business's
    (``groups_standing_for``). ``conn`` is the copy's direct, read-only connection."""
    return dict(conn.execute(_by_id(ModifierGroup._meta, ("id", "name"))).fetchall())


def _by_id(meta, read: tuple[str, ...]) -> sql.Composed:
    """The ``read`` columns of every row of the model ``meta`` of a copy, by id."""
    return sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
        sql.SQL(", ").join(sql.Identifier(meta.get_field(field).column) for field in read),
        sql.Identifier(meta.db_table),
        sql.Identifier(meta.pk.column),
    )


def groups_not_in_business(groups: list[dict]) -> list[dict]:
    """The groups of a separate copy (``groups_in_copy``) the business no longer has, in their order, each as
    ``modifier.group.recover`` takes it, with its ``id`` there: its options with the key of each one's own tax category
    (Taxes never deletes one). Not lacking: one the business still holds, renamed or not, with the options it has now;
    nor one with its name, the case aside, as a group's name is unique: made again by hand or brought back already, it
    is the business's, and none is ever made twice."""
    if not groups:
        return []
    held = set(ModifierGroup.objects.filter(pk__in=[one["id"] for one in groups]).values_list("pk", flat=True))
    names = {name.lower() for name in ModifierGroup.objects.values_list("name", flat=True)}
    lacking = [one for one in groups if one["id"] not in held and one["name"].lower() not in names]
    taxed = {option["tax_category_id"] for one in lacking for option in one["options"]}
    keys = dict(TaxCategory.objects.filter(pk__in=taxed).values_list("pk", "key"))
    return [
        {field: one[field] for field in ("id", *GROUP_COPY_FIELDS)}
        | {
            "options": [
                {field: option[field] for field in (*OPTION_COPY_FIELDS, *LATER_OPTION_FIELDS) if field in option}
                | {"tax_category_key": keys.get(option["tax_category_id"], "")}
                for option in one["options"]
            ]
        }
        for one in lacking
    ]


def options_in_copy(conn) -> list[dict]:
    """Each option of a separate copy of the business, by id, with its group there (``group_id``), what
    ``OPTION_COPY_FIELDS`` names, the later fields the copy holds (``copy_columns``), the id of its own tax category
    (``tax_category_id``) and the copy's groups by name (``copy_groups``, to pair a group the business deleted with the
    one brought back); nothing where the app's table is not there. ``conn`` is the copy's direct read-only connection."""
    option = ModifierOption._meta
    if conn.execute("SELECT to_regclass(%s)", [option.db_table]).fetchone()[0] is None:
        return []
    read = (*OPTION_COPY_FIELDS, *later_option_fields(conn))
    rows = conn.execute(_by_id(option, ("id", "group", *read, "tax_category"))).fetchall()
    if not rows:
        return []
    groups = group_names_in_copy(conn)
    keys = ("id", "group_id", *read, "tax_category_id")
    return [dict(zip(keys, row, strict=True)) | {"copy_groups": groups} for row in rows]


def options_not_in_business(options: list[dict]) -> list[dict]:
    """The options of a separate copy (``options_in_copy``) that a group the business keeps no longer has, in their
    order, each as ``modifier.option.recover`` takes it with its ``id`` there and the key of its own tax category. Its
    group is the business's that stands for the copy's (``groups_standing_for``): the same while held, else the one a
    recovery brought back with its name; the copy's own where none does, which the create then refuses as not found.
    Not lacking: one the business still holds, renamed or not (an option never changes its group); one whose name its
    group has again, the case aside, made again by hand or brought back already; nor one of a group the recovery at work
    brought back, whose recover gave back its options and said what it came back without."""
    if not options:
        return []
    groups = groups_standing_for(options[0]["copy_groups"])
    held = set(ModifierOption.objects.filter(pk__in=[one["id"] for one in options]).values_list("pk", flat=True))
    wanted = [(one, groups.get(one["group_id"], one["group_id"])) for one in options if one["id"] not in held]
    places = {group for _one, group in wanted}
    # Outside a recovery, at_work() is None and no group was made by it.
    with_it = set(ModifierGroup.objects.filter(pk__in=places, created_by=at_work()).values_list("pk", flat=True))
    named = ModifierOption.objects.filter(group_id__in=places).values_list("group_id", "name")
    taken = {(group, name.lower()) for group, name in named}
    lacking = [
        (one, group) for one, group in wanted if group not in with_it and (group, one["name"].lower()) not in taken
    ]
    taxed = {one["tax_category_id"] for one, _group in lacking}
    keys = dict(TaxCategory.objects.filter(pk__in=taxed).values_list("pk", "key"))
    return [
        {field: one[field] for field in ("id", *OPTION_COPY_FIELDS, *LATER_OPTION_FIELDS) if field in one}
        | {"group_id": group, "tax_category_key": keys.get(one["tax_category_id"], "")}
        for one, group in lacking
    ]


def groups_standing_for(copy: dict[UUID, str]) -> dict[UUID, UUID]:
    """The business's group that stands for each of a separate copy's it no longer holds, as ``{id there: id here}``:
    the one with its name, the case aside, that a recovery made again (``brought_back``) and that is none of the copy's,
    which is why ``copy`` is every group of the copy by name (``group_names_in_copy``). One the business made again by
    hand is its own, set up as it chose: it stands for none. A group still held here is itself, and is not in the
    result. For the copy's links to hang from the group it is now."""
    here = list(ModifierGroup.objects.values_list("pk", "name", "created_by"))
    held = {pk for pk, _name, _by in here}
    back = {name.lower(): pk for pk, name, created_by in here if pk not in copy and brought_back(created_by)}
    return {there: back[name.lower()] for there, name in copy.items() if there not in held and name.lower() in back}


def links_in_copy(conn) -> list[dict]:
    """Each group hung from a product in a separate copy of the business, of a product Inventory had not deleted there
    (a category's groups are ``category_links_in_copy``), with what ``LINK_FIELDS`` names and the copy's groups by name
    (``copy_groups``, to pair a group the business deleted with the one brought back); nothing where the app's table is
    not there. ``conn`` is the copy's direct, read-only connection."""
    rows = _links_in_copy(conn, "product", also=("sku",))
    if not rows:
        return []
    groups = group_names_in_copy(conn)
    return [dict(zip(LINK_FIELDS, row, strict=True)) | {"copy_groups": groups} for row in rows]


def category_links_in_copy(conn) -> list[dict]:
    """Each group hung from a category in a separate copy of the business, of a category Inventory had not deleted
    there, with what ``CATEGORY_LINK_FIELDS`` names, the copy's live categories by name (``copy_categories``, to pair
    its category with the business's) and its groups by name (``copy_groups``, the same with a group); nothing where
    the app's table is not there. ``conn`` is the copy's direct, read-only connection."""
    rows = _links_in_copy(conn, "category")
    if not rows:
        return []
    named, groups = category_names_in_copy(conn), group_names_in_copy(conn)
    return [
        dict(zip(CATEGORY_LINK_FIELDS, row, strict=True)) | {"copy_categories": named, "copy_groups": groups}
        for row in rows
    ]


def _links_in_copy(conn, target: str, also: tuple[str, ...] = ()) -> list[tuple]:
    """The copy's links to a live ``target`` of Inventory (``"product"`` or ``"category"``), by id: each one's id, group
    and target there, and the target's columns ``also``; none where the app's table is not there. It is read by its own
    SQL over the models' names, never the ORM: the copy is no business."""
    link = ModifierLink._meta
    model = link.get_field(target).related_model._meta
    if conn.execute("SELECT to_regclass(%s)", [link.db_table]).fetchone()[0] is None:
        return []

    def column(meta, field: str) -> sql.Identifier:
        return sql.Identifier(meta.get_field(field).column)

    read = sql.SQL(
        "SELECT {columns} FROM {links} l JOIN {targets} t ON t.{target_pk} = l.{target_id}"
        " WHERE NOT t.{deleted} ORDER BY l.{link_pk}"
    ).format(
        columns=sql.SQL(", ").join(
            [
                *(sql.SQL("l.{}").format(column(link, field)) for field in ("id", "group", target)),
                *(sql.SQL("t.{}").format(column(model, field)) for field in also),
            ]
        ),
        links=sql.Identifier(link.db_table),
        targets=sql.Identifier(model.db_table),
        target_pk=column(model, "id"),
        target_id=column(link, target),
        deleted=column(model, "is_deleted"),
        link_pk=column(link, "id"),
    )
    return conn.execute(read).fetchall()


def links_not_in_business(links: list[dict]) -> list[dict]:
    """The groups hung from a product in a separate copy (``links_in_copy``) the business no longer hangs there, in
    their order, each as ``modifier.link.attach`` takes it with its ``id`` there. Its product is the business's that
    stands for the copy's (Inventory's ``products_standing_for``): the same while live, else the one a recovery made
    again with its SKU; and its group too (``groups_standing_for``)."""
    if not links:
        return []
    return _not_hung(links, "product", products_standing_for({one["product_id"]: one["sku"] for one in links}))


def category_links_not_in_business(links: list[dict]) -> list[dict]:
    """The groups hung from a category in a separate copy (``category_links_in_copy``) the business no longer hangs
    there, in their order, each as ``modifier.link.attach`` takes it with its ``id`` there. Its category is the
    business's that stands for the copy's (Inventory's ``categories_standing_for``): the same while live, else the one a
    recovery brought back with its name; and its group too (``groups_standing_for``)."""
    if not links:
        return []
    return _not_hung(links, "category", categories_standing_for(links[0]["copy_categories"]))


def _not_hung(links: list[dict], target: str, here: dict) -> list[dict]:
    """Of the copy's ``links`` to a ``target``, those whose group the business does not hang from the ``target`` that
    stands for the copy's (``here``, ``{id there: id here}``), each group the one that stands for the copy's
    (``groups_standing_for``); the copy's own id when none does, which the attach then refuses as not found. Not
    lacking: the same link or one the business hung again, which stays as the business has it. A link never changes
    its group nor its target, so the one the business still holds is always in its place."""
    key = f"{target}_id"
    groups = groups_standing_for(links[0]["copy_groups"])
    wanted = [(one, groups.get(one["group_id"], one["group_id"]), here.get(one[key], one[key])) for one in links]
    taken = set(
        ModifierLink.objects.filter(group_id__in={group for _one, group, _at in wanted}).values_list("group_id", key)
    )
    return [{"id": one["id"], "group_id": group, key: at} for one, group, at in wanted if (group, at) not in taken]

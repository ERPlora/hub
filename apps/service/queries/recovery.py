"""What a separate copy of the business gives back (BASE-F114, SERVICE-F01, F07, F31): the categories and
services the business lost, what goes back into each, and the service that stands for one of the copy."""

from uuid import UUID

from live.context import OperationContext
from live.operations import INTERNAL, operation
from psycopg import sql

from apps.service.models import Assignment, Category, Service, parent_problem
from apps.service.queries.reads import SYSTEM
from apps.service.schemas import StandingForIn, StandingForOut
from apps.tax.models import TaxCategory
from base.recovery import at_work, brought_back

#: What ``service.category.create`` takes of a category of a separate copy, each a column since ``0001_initial``
#: (``categories_in_copy``): all of it but its parent, which the business names its own way.
CATEGORY_COPY_FIELDS = ("name", "description", "icon", "color", "sort_order")


def categories_in_copy(conn) -> list[dict]:
    """hub#1323: each live category of a separate copy of the business, with its ``id`` there, what
    ``service.category.create`` takes, the id there of its parent (``parent_id``) and of each service in it, archived
    ones too (``service_ids``, hub#1364); nothing where the app's table is not there. One the copy had deleted already
    is not the moment's and never comes back. ``conn`` is the copy's direct, read-only connection (as
    ``services_in_copy``), so it is read by its own SQL over the model's names."""
    table = Category._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return []
    read = ("id", *CATEGORY_COPY_FIELDS, "parent")
    column = {field: sql.Identifier(Category._meta.get_field(field).column) for field in (*read, "is_deleted")}
    query = sql.SQL("SELECT {} FROM {} WHERE NOT {} ORDER BY {}").format(
        sql.SQL(", ").join(column[field] for field in read),
        sql.Identifier(table),
        column["is_deleted"],
        column["id"],
    )
    named = ("id", *CATEGORY_COPY_FIELDS, "parent_id")
    inside = _services_by_category_in_copy(conn)
    return [
        dict(zip(named, row, strict=True)) | {"service_ids": inside.get(row[0], [])} for row in conn.execute(query)
    ]


def _services_by_category_in_copy(conn) -> dict[UUID, list[UUID]]:
    """``{category's id: [its services' ids]}`` in a separate copy, in id order; nothing where the table is not."""
    table = Service._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return {}
    pk, category = (sql.Identifier(Service._meta.get_field(field).column) for field in ("id", "category"))
    query = sql.SQL("SELECT {}, {} FROM {} WHERE {} IS NOT NULL ORDER BY {}").format(
        category, pk, sql.Identifier(table), category, pk
    )
    inside: dict[UUID, list[UUID]] = {}
    for category_id, service_id in conn.execute(query):
        inside.setdefault(category_id, []).append(service_id)
    return inside


def categories_not_in_business(categories: list[dict]) -> list[dict]:
    """hub#1323: the categories of a separate copy (``categories_in_copy``) the business lacks, parents first and then
    in their order, each as ``service.category.recover`` takes it here, with its ``id`` there. Not lacking: one the
    business still has live, or one it made again (a live one with its name, the case and the spaces aside: a live name
    is unique, SERVICE-F07), so none is ever made twice. Each goes into its parent: by its id when the business has it
    (``_category_held``), by its name when it comes back too (created just before it, so with no id here yet), and at
    the root when the copy did not have it live. Each takes the copy's category it stands for and what it had inside
    it there, its services and its subcategories, for the create to take back what the business kept (hub#1364)."""
    here = _categories_here()
    by_id = {one["id"]: one for one in categories}
    lacking = [one for one in categories if _category_held(one["id"], one["name"], here) is None]
    created = []
    # Sorted is stable: within a depth, the copy's order.
    for one in sorted(lacking, key=lambda category: _depth(category, by_id)):
        record = {field: one[field] for field in ("id", *CATEGORY_COPY_FIELDS, "service_ids")}
        record["stands_for"] = one["id"]
        record["subcategory_ids"] = [child["id"] for child in categories if child["parent_id"] == one["id"]]
        if (parent := by_id.get(one["parent_id"])) is not None:
            if (held := _category_held(parent["id"], parent["name"], here)) is not None:
                record["parent_id"] = held
            else:
                record["parent"] = parent["name"]
        created.append(record)
    return created


def _depth(category: dict, by_id: dict[UUID, dict]) -> int:
    """How many of the copy's categories ``category`` hangs from; a loop a raw write left counts each once."""
    seen, parent = {category["id"]}, by_id.get(category["parent_id"])
    while parent is not None and parent["id"] not in seen:
        seen.add(parent["id"])
        parent = by_id.get(parent["parent_id"])
    return len(seen) - 1


def _categories_here() -> tuple[set[UUID], dict[str, UUID]]:
    """The business's live categories: their ids, and each by its name as two that are the same compare."""
    live = list(Category.objects.filter(is_deleted=False).values_list("pk", "name"))
    return {pk for pk, _name in live}, {_same_name(name): pk for pk, name in live}


def _category_held(category_id: UUID | None, name: str | None, here: tuple[set[UUID], dict[str, UUID]]) -> UUID | None:
    """The business's live category that is the copy's ``category_id`` (named ``name`` there): the same while it is
    live, else the live one with its name (brought back by an earlier part of the recovery, or made again by hand);
    none otherwise."""
    ids, by_name = here
    if category_id in ids:
        return category_id
    return by_name.get(_same_name(name)) if name is not None else None


#: What ``service.service.recover`` takes of a service of a separate copy (``services_in_copy``): its create's, each a
#: column since ``0001_initial``, and the image it showed, one since ``0003_service_image``, the migration its
#: declaration names (``reads_since``); not its category and its tax category, which the business names its own way,
#: nor who performs it, read apart (``recoverable_services_in_copy``).
COPY_FIELDS = (
    "name",
    "pricing_type",
    "price",
    "min_price",
    "max_price",
    "cost",
    "duration_minutes",
    "buffer_before",
    "buffer_after",
    "max_capacity",
    "description",
    "short_description",
    "is_bookable",
    "requires_confirmation",
    "allow_online_booking",
    "sort_order",
    "is_featured",
    "sku",
    "barcode",
    "notes",
    "image",
)


def services_in_copy(conn) -> list[dict]:
    """hub#1283: each service of a separate copy of the business, on offer or archived (``is_active``), with its ``id``
    there, what ``service.service.recover`` takes (``COPY_FIELDS``) and the ids there of its category (``category_id``)
    and its tax category (``tax_category_id``), by id, and its category's name there (``category_name``, hub#1323: a
    category brought back is a new one, found by its name); nothing where the app's table is not there. Only one on
    offer comes back (``services_not_in_business``), but every one is read: a service of the copy is never another one's
    made again (``services_in_business``). ``conn`` is the copy's direct, read-only connection
    (``recoverable_from_copy`` on this app's config: the copy is no business and has no alias), so it is read by its
    own SQL over the model's names, never the ORM."""
    table = Service._meta.db_table
    if conn.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] is None:
        return []
    read = ("id", *COPY_FIELDS, "category", "tax_category", "is_active")
    service, category = sql.Identifier("service"), sql.Identifier("category")

    def of(alias, model, field):
        return sql.SQL("{}.{}").format(alias, sql.Identifier(model._meta.get_field(field).column))

    # Deleting a category takes its services out of it (SERVICE-F08): a service's category is a live one.
    query = sql.SQL("SELECT {}, {} FROM {} AS {} LEFT JOIN {} AS {} ON {} = {} ORDER BY {}").format(
        sql.SQL(", ").join(of(service, Service, field) for field in read),
        of(category, Category, "name"),
        sql.Identifier(table),
        service,
        sql.Identifier(Category._meta.db_table),
        category,
        of(category, Category, "id"),
        of(service, Service, "category"),
        of(service, Service, "id"),
    )
    named = ("id", *COPY_FIELDS, "category_id", "tax_category_id", "is_active", "category_name")
    return [dict(zip(named, row, strict=True)) for row in conn.execute(query)]


#: What ``service.service.recover`` takes of each professional who performed a service of a separate copy, besides who
#: they are (``AssignmentOfCopyIn``), each a column since ``0001_initial``.
ASSIGNMENT_COPY_FIELDS = ("custom_duration", "custom_price", "is_primary", "is_active")


def recoverable_services_in_copy(conn) -> list[dict]:
    """Each service of ``services_in_copy`` with who performed it in the copy (``assignments``), as
    ``service.service.recover`` takes them: each professional by their id there, the same in the business, and their
    own minutes and price, whether it was their main service and whether it was switched on, in the order they were
    assigned. The same connection and rule as ``services_in_copy``: its own SQL over the model's names, never the ORM."""
    services = services_in_copy(conn)
    if not services:
        return []
    read = ("service", "member", *ASSIGNMENT_COPY_FIELDS)
    query = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
        sql.SQL(", ").join(sql.Identifier(Assignment._meta.get_field(field).column) for field in read),
        sql.Identifier(Assignment._meta.db_table),
        sql.Identifier(Assignment._meta.pk.column),
    )
    performed: dict[UUID, list[dict]] = {}
    for service_id, *row in conn.execute(query):
        performed.setdefault(service_id, []).append(dict(zip(("member_id", *ASSIGNMENT_COPY_FIELDS), row, strict=True)))
    return [one | {"assignments": performed.get(one["id"], [])} for one in services]


def services_in_business(services: list[dict]) -> dict[UUID, UUID]:
    """hub#1283: ``{id in the copy: id in the business}`` of each service of a separate copy (all of
    ``services_in_copy``, never a part) the business holds: the same one, on offer or archived (a service is never
    deleted; SERVICE-F05 restores it), or, for one the copy had on offer, one made again, by hand or brought back
    already: a service that is none of the copy's, with the same name, the case and the spaces aside, in the category it
    would come back to (``_category_here``). Names are not unique, so each made again stands for one service of the copy:
    the oldest made again for the copy's oldest. What a recovery of another app matches a service of the copy by."""
    ids = [one["id"] for one in services]
    by_id = set(Service.objects.filter(pk__in=ids).values_list("pk", flat=True))
    here = _categories_here()
    made_again: dict[tuple[str, UUID | None], list[UUID]] = {}
    others = Service.objects.exclude(pk__in=ids).order_by("created_at", "id")
    for pk, name, category in others.values_list("pk", "name", "category"):
        made_again.setdefault((_same_name(name), category), []).append(pk)
    held = {}
    for one in sorted(services, key=lambda service: service["id"]):
        if one["id"] in by_id:
            held[one["id"]] = one["id"]
        elif one["is_active"] and (twins := made_again.get((_same_name(one["name"]), _category_here(one, here)))):
            held[one["id"]] = twins.pop(0)
    return held


def services_not_in_business(services: list[dict]) -> list[dict]:
    """The services a separate copy (``recoverable_services_in_copy``) had on offer and the business lacks (not
    in ``services_in_business``), in their order, each as ``service.service.recover`` takes it here, with its ``id``
    there: the key of its tax category (Taxes never deletes one; one turned off since is the create's to refuse, and
    without one it takes the settings'), its category here (``_category_here``), who performed it there
    (``assignments``) and which of the copy's it stands for (``stands_for``), which the business keeps."""
    held = services_in_business(services)
    lacking = [one for one in services if one["is_active"] and one["id"] not in held]
    keys = dict(TaxCategory.objects.filter(pk__in={one["tax_category_id"] for one in lacking}).values_list("pk", "key"))
    here = _categories_here()
    created = []
    for one in lacking:
        record = {field: one[field] for field in ("id", *COPY_FIELDS, "assignments")} | {"stands_for": one["id"]}
        if (category := _category_here(one, here)) is not None:
            record["category_id"] = category
        if (key := keys.get(one["tax_category_id"])) is not None:
            record["tax_category_key"] = key
        created.append(record)
    return created


def services_standing_for(ids) -> dict[UUID, UUID]:
    """The business's service that stands for each of a separate copy's services (``ids``, there) it no longer holds,
    as ``{id there: id here}``: the one a recovery made again for it (``stands_for``, kept by
    ``service.service.recover``), on offer or archived since, renamed or not; the oldest if a recovery made it twice.
    One the business made again by hand is its own, set up as it chose: it stands for none. A service it still holds is
    itself, and is not in the result. For the apps whose records hang from a service of the copy to give each back to
    the service it is now."""
    held = set(Service.objects.filter(pk__in=ids).values_list("pk", flat=True))
    made = Service.objects.filter(stands_for__in=[one for one in ids if one not in held]).order_by("created_at", "id")
    standing: dict[UUID, UUID] = {}
    for there, here in made.values_list("stands_for", "pk"):
        standing.setdefault(there, here)
    return standing


# Not an assistant tool and no route: what Price Lists, which does not require Services, asks while it gives a separate
# copy back (BASE-F114, PRICING-F15).
@operation(
    "service.service.standing_for",
    kind="query",
    permission=SYSTEM,
    input=StandingForIn,
    output=StandingForOut,
    ai=INTERNAL,
)
def standing_for(ctx: OperationContext, data: StandingForIn) -> dict:
    """The business's service that stands for each of a separate copy's it no longer holds
    (``services_standing_for``)."""
    return {"standing_for": services_standing_for(data.ids)}


def _category_here(service: dict, here: tuple[set[UUID], dict[str, UUID]]) -> UUID | None:
    """The category a service of the copy comes back to: its own while the business still has it, else the live one
    with its name (brought back just before it by the categories' part, hub#1323, or made again by hand), none
    otherwise (none in the copy, or deleted since and not back, SERVICE-F08)."""
    return _category_held(service["category_id"], service["category_name"], here)


def service_links_not_in_business(categories: list[dict]) -> list[dict]:
    """The services of a separate copy's categories (``categories_in_copy``) that go back into the category a recovery
    brought back for theirs (``_brought_back_for``), in id order, each as ``service.service.return_to_category`` takes
    it, with its ``id``: one the business keeps where deleting that category left it, without a category, archived
    too, and has not touched since the category came back (asked again, what the business did since stays). One it
    touched while the recovery that brought the category back is still at work goes too, for its link to say why it
    stays out (``_said_while_at_work``)."""
    back = _brought_back_for(categories)
    into = {service: back[one["id"]] for one in categories if one["id"] in back for service in one["service_ids"]}
    kept = Service.objects.filter(pk__in=into, category__isnull=True).order_by("id").values_list("pk", "updated_at")
    return [
        {"id": pk, "service_id": pk, "category_id": into[pk].pk}
        for pk, updated_at in kept
        if updated_at <= into[pk].created_at or _said_while_at_work(into[pk])
    ]


def subcategory_links_not_in_business(categories: list[dict]) -> list[dict]:
    """The subcategories of a separate copy's categories (``categories_in_copy``) that go back into the category a
    recovery brought back for their parent (``_brought_back_for``), in id order, each as
    ``service.category.return_to_parent`` takes it, with its ``id`` and the copy's category it hung from
    (``stands_for``): one the business keeps live where deleting that one left it (``left_by_deleting``), has not
    touched since the category came back (or touched while that recovery is still at work, ``_said_while_at_work``),
    and that would not hang from one of its own subcategories."""
    back = _brought_back_for(categories)
    under = {one["id"]: one["parent_id"] for one in categories if one["parent_id"] in back}
    parent_of = dict(Category.objects.filter(is_deleted=False).values_list("pk", "parent"))
    kept = Category.objects.filter(pk__in=under, is_deleted=False).order_by("id")
    links = []
    for pk, parent, updated_at in kept.values_list("pk", "parent", "updated_at"):
        stands_for, into = under[pk], back[under[pk]]
        if (
            parent == left_by_deleting(stands_for)
            and (updated_at <= into.created_at or _said_while_at_work(into))
            and parent_problem(pk, into.pk, parent_of) is None
        ):
            links.append({"id": pk, "category_id": pk, "parent_id": into.pk, "stands_for": stands_for})
    return links


def _brought_back_for(categories: list[dict]) -> dict[UUID, Category]:
    """Each of a separate copy's categories the business no longer has live, with the live one a recovery made again
    with its name (``base.recovery.brought_back``); none for one it kept, or made again by hand."""
    ids, by_name = _categories_here()
    named = {one["id"]: by_name.get(_same_name(one["name"])) for one in categories if one["id"] not in ids}
    made = Category.objects.filter(pk__in={pk for pk in named.values() if pk is not None})
    by_recovery = {one.pk: one for one in made.only("pk", "created_by", "created_at") if brought_back(one.created_by)}
    return {there: by_recovery[here] for there, here in named.items() if here in by_recovery}


def _said_while_at_work(category: Category) -> bool:
    """Whether ``category`` came back with the recovery at work (``base.recovery.at_work``): what the business touched
    in it since is its link's to refuse and say, as its link does for what it moved. Asked again, it is not."""
    return category.created_by == at_work()


def left_by_deleting(category_id: UUID | None) -> UUID | None:
    """Where deleting the category ``category_id`` left what hung from it: the parent its row has now (a deleted one
    moves up with its siblings, SERVICE-F08), or the root when the business no longer holds it at all."""
    return Category.objects.filter(pk=category_id).values_list("parent", flat=True).first()


def _same_name(name: str) -> str:
    """A name as two that are the same compare: single spaces (as it is kept), the case aside."""
    return " ".join(name.split()).casefold()

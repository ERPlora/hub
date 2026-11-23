"""The categories (SERVICE-F07, F08): created, changed and deleted, with every live category locked first when one moves
or goes, so two writes never hang one inside the other.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.service import events
from apps.service.models import CATEGORY_CYCLE, CATEGORY_LOOP, Category, Service, parent_problem
from apps.service.queries.categories import find_category, load_category
from apps.service.schemas.categories import CategoryIn, CategoryOut, CategoryPatchIn
from apps.service.schemas.fields import CategoryRefIn, DeletedOut
from apps.service.services.writes import _actor, _apply, _changes, _refuse, _save_unique, _tidy

PARENT_UNAVAILABLE = _(
    "That parent category is not available: it does not exist in this business or it has been deleted."
)
CATEGORY_NAME_TAKEN = _(
    "There is already a category with that name. Pick another name."
)


def _check_category_name(name: str, *, other_than=None) -> None:
    taken = Category.objects.filter(is_deleted=False, name__iexact=name)
    if other_than is not None:
        taken = taken.exclude(pk=other_than)
    if taken.exists():
        raise Conflict(
            str(CATEGORY_NAME_TAKEN),
            code="service.category_name_taken",
            fields={"name": str(CATEGORY_NAME_TAKEN)},
        )


def _parent(parent_id, said, *, hold: bool = False) -> Category | None:
    if parent_id is None and said is None:
        return None
    try:
        return find_category(parent_id, said, hold=hold)
    except NotFound as exc:
        field = "parent_id" if parent_id else "parent"
        raise _refuse(
            PARENT_UNAVAILABLE, "service.parent_category_unavailable", field
        ) from exc


def lock_tree() -> dict:
    """Locks every live category in id order; their parents as they are now (id → parent id). Moving or
    deleting a category takes it first, and so does the Hub admin's «Delete» (admin.py): a write that holds a
    category it names and then its own row never waits in a circle with them."""
    rows = Category.objects.select_for_update().filter(is_deleted=False).order_by("id")
    return dict(rows.values_list("id", "parent_id"))


@operation(
    "service.category.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.add_category",
    input=CategoryIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Create a service category, optionally inside another one; its name is unique.",
        "risk": "normal",
        "asks": {
            "en": ("create a nails category for the services", "add a Colour service category"),
            "es": ("crea la categoría Uñas para los servicios", "añade una familia de servicios llamada Color"),
        },
    },
)
def create_category(ctx: OperationContext, data: CategoryIn) -> dict:
    name = _tidy(data.name)
    _check_category_name(name)
    category = Category(
        name=name,
        description=data.description,
        parent=_parent(data.parent_id, data.parent, hold=True),
        icon=data.icon,
        color=data.color,
        sort_order=data.sort_order,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _save_unique(
        category,
        "service_category_live_name_unique",
        CATEGORY_NAME_TAKEN,
        "service.category_name_taken",
    )
    record_event(ctx, events.CATEGORY_CREATED, {"id": str(category.id)})
    return load_category(category.id)


@operation(
    "service.category.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.change_category",
    input=CategoryPatchIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Change a service category (named by its id or its name): only the fields sent change; "
        "parent_id null makes it a root category.",
        "risk": "normal",
        "asks": {
            "en": ("rename the nails category to Hands and feet", "move the colour category inside Hair"),
            "es": (
                "cambia el nombre de la categoría Uñas a Manos y pies",
                "mete la categoría de color dentro de Peluquería",
            ),
        },
    },
)
def update_category(ctx: OperationContext, data: CategoryPatchIn) -> dict:
    sent = data.model_fields_set
    moving = bool(sent & {"parent_id", "parent"})
    category_id = find_category(data.id, data.category).pk
    # Moving a category takes every live category, in id order, before its own row: two moves at
    # once go one after the other, and the second sees where the first left the tree.
    parent_of = lock_tree() if moving else {}
    category = find_category(category_id, None, lock=True)
    values = {
        field: getattr(data, field)
        for field in ("description", "icon", "color", "sort_order")
        if field in sent and getattr(data, field) is not None
    }
    if data.name is not None:
        values["name"] = _tidy(data.name)
        _check_category_name(values["name"], other_than=category.pk)
    if moving:
        parent = _parent(data.parent_id, data.parent)
        problem = parent_problem(category.pk, parent.pk if parent else None, parent_of)
        if problem == "cycle":
            raise _refuse(CATEGORY_CYCLE, "service.category_cycle", "parent_id" if data.parent_id else "parent")
        if problem == "loop":
            raise Conflict(str(CATEGORY_LOOP), code="service.category_cycle")
        values["parent"] = parent
    changes = _changes(category, values)
    if changes:
        _apply(category, changes, ctx)
        _save_unique(
            category,
            "service_category_live_name_unique",
            CATEGORY_NAME_TAKEN,
            "service.category_name_taken",
        )
        record_event(ctx, events.CATEGORY_UPDATED, {"id": str(category.id)})
    return load_category(category.id)


@operation(
    "service.category.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.delete_category",
    input=CategoryRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a service category: its services stay, without a category, and its subcategories "
        "move up to its parent; its name is free again.",
        "risk": "high",
        "asks": {
            "en": (
                "delete the nails category, its services can stay without one",
                "remove the Others service category",
            ),
            "es": ("elimina la categoría Uñas", "borra la familia de servicios Varios"),
        },
    },
)
def delete_category(ctx: OperationContext, data: CategoryRefIn) -> dict:
    category_id = find_category(data.id, data.category).pk
    lock_tree()  # its children move: the same order as a move, so the two never wait for each other
    category = find_category(category_id, None, lock=True)
    now = timezone.now()
    Service.objects.filter(category=category).update(category=None, updated_at=now)
    children = Category.objects.filter(parent=category)
    # Its children go up to its parent; one that is that parent (a loop a raw write left) goes to the root.
    children.exclude(pk=category.parent_id).update(parent=category.parent_id, updated_at=now)
    children.filter(pk=category.parent_id).update(parent=None, updated_at=now)
    _apply(category, {"is_deleted": True, "deleted_at": timezone.now()}, ctx)
    category.save()
    record_event(ctx, events.CATEGORY_DELETED, {"id": str(category.id)})
    return {"id": category.id}

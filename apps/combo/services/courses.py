"""A menu's courses (COMBO-F05): add one, last in its menu, change it in its place, remove it, put them in a new
order, and add one again from a separate copy (COMBO-F15)."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.combo import events
from apps.combo.models import ChoiceGroup, Combo
from apps.combo.queries.reads import find_combo, find_group
from apps.combo.queries.rows import load_detail
from apps.combo.schemas.courses import GroupIn, GroupOut, GroupPatchIn, GroupRecoverIn, GroupReorderIn
from apps.combo.schemas.fields import CEILING_BELOW_FLOOR, MAX_GROUPS, DeletedOut
from apps.combo.schemas.menus import ComboDetailOut
from apps.combo.schemas.references import GroupRefIn
from apps.combo.services.writes import SYSTEM, _group_out, _next_order, _reordered, _saved

GROUP_EXISTS = _("That menu already has a course “%(name)s”.")
TOO_MANY_GROUPS = _("A menu holds %(max)s courses at most.")


def _group_event(ctx: OperationContext, name: str, group: ChoiceGroup) -> None:
    record_event(ctx, name, {"id": str(group.id), "combo_id": str(group.combo_id)})


def _lock_combo(combo_id: UUID) -> None:
    """Locks the menu's row until the end of the command: writes of a menu's courses queue on it."""
    list(Combo.objects.select_for_update().filter(pk=combo_id).values_list("pk", flat=True))


def _name_free(combo_id: UUID, name: str, exclude: UUID | None = None) -> None:
    taken = ChoiceGroup.objects.filter(combo_id=combo_id, name__iexact=name).exclude(
        pk=exclude
    )
    if taken.exists():
        message = str(GROUP_EXISTS) % {"name": name}
        raise Conflict(message, code="combo.group_exists", fields={"name": message})


@operation(
    "combo.group.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=GroupIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Add a course to a menu («add Starters to the menu of the day, pick 1»): it goes last. "
        "min_choices 1 or more makes it compulsory; max_choices 0 is no limit.",
        "risk": "normal",
        "asks": {
            "en": (
                "add a Desserts course to the vegan menu, pick one",
                "the kids' menu needs a Drinks course",
            ),
            "es": (
                "añade el plato Postres al menú vegano, a elegir uno",
                "el menú infantil necesita un plato de bebidas",
            ),
        },
    },
)
def create_group(ctx: OperationContext, data: GroupIn) -> dict:
    combo = find_combo(data.combo_id, data.combo, lock=True)
    if combo.groups.count() >= MAX_GROUPS:
        raise Conflict(
            str(TOO_MANY_GROUPS) % {"max": MAX_GROUPS}, code="combo.too_many_groups"
        )
    _name_free(combo.id, data.name)
    group = ChoiceGroup(
        combo=combo,
        name=data.name,
        min_choices=data.min_choices,
        max_choices=data.max_choices,
        allow_repeat=data.allow_repeat,
        sort_order=_next_order(combo.groups),
    )
    _saved(group.save, lambda: _name_free(combo.id, data.name))
    _group_event(ctx, events.GROUP_CREATED, group)
    return _group_out(group.id)


# Not an assistant tool and no route: its one door is the recovery from a separate copy (BASE-F114, COMBO-F15), for a
# course its menu no longer has (removing one deletes it with its choices).
@operation(
    "combo.group.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=GroupRecoverIn,
    output=GroupOut,
    ai=INTERNAL,
)
def recover_group(ctx: OperationContext, data: GroupRecoverIn) -> dict:
    """A course of a separate copy added again by ``combo.group.create``, last in its menu. It keeps which of the
    copy's it is made again for (``stands_for``), so its choices come back to it."""
    made = create_group(ctx, GroupIn.model_validate(data.model_dump(include=set(GroupIn.model_fields))))
    ChoiceGroup.objects.filter(pk=made.id).update(stands_for=data.stands_for)
    return made


@operation(
    "combo.group.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=GroupPatchIn,
    output=GroupOut,
    expose_api=True,
    ai={
        "description": "Change a course: its name, minimum and maximum picks, or whether a choice may repeat. "
        "Only the fields sent change; it keeps its place.",
        "risk": "normal",
        # The course as the write will find it, before its card: the yes holds to it (hub#1231).
        "check": "combo.group.get",
        "asks": {
            "en": (
                "let them pick two starters instead of one",
                "make the drinks course optional for kids",
            ),
            "es": (
                "que se puedan elegir dos entrantes en vez de uno",
                "haz opcional el plato de bebida del infantil",
            ),
        },
    },
)
def update_group(ctx: OperationContext, data: GroupPatchIn) -> dict:
    # The menu first, as creating a course does: a rename and a new course of the same name queue.
    _lock_combo(find_group(data.id, data.combo_id, data.combo, data.group).combo_id)
    group = find_group(data.id, data.combo_id, data.combo, data.group, lock=True)
    sent = data.model_fields_set
    changed: list[str] = []
    for field in ("name", "min_choices", "max_choices", "allow_repeat"):
        value = getattr(data, field)
        if field in sent and value is not None and getattr(group, field) != value:
            setattr(group, field, value)
            changed.append(field)
    if group.max_choices and group.max_choices < group.min_choices:
        message = str(CEILING_BELOW_FLOOR) % {
            "max": group.max_choices,
            "min": group.min_choices,
        }
        field = "max_choices" if "max_choices" in sent else "min_choices"
        raise InvalidPayload(message, code="invalid_field", fields={field: message})
    if "name" in changed:
        _name_free(group.combo_id, group.name, exclude=group.id)
    if changed:
        _saved(
            lambda: group.save(update_fields=[*changed, "updated_at"]),
            lambda: _name_free(group.combo_id, group.name, exclude=group.id),
        )
        _group_event(ctx, events.GROUP_UPDATED, group)
    return _group_out(group.id)


@operation(
    "combo.group.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=GroupRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Remove a course from its menu, with its choices.",
        "risk": "high",
        "check": "combo.group.get",
        "asks": {
            "en": (
                "remove the Desserts course from the vegan menu",
                "the kids' menu no longer has a drinks course",
            ),
            "es": (
                "quita los postres del menú vegano",
                "el menú infantil ya no lleva plato de bebida",
            ),
        },
    },
)
def delete_group(ctx: OperationContext, data: GroupRefIn) -> dict:
    group = find_group(data.id, data.combo_id, data.combo, data.group, lock=True)
    _group_event(ctx, events.GROUP_DELETED, group)
    group_id = group.id
    group.delete()
    return {"id": group_id}


@operation(
    "combo.group.reorder",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="combo.manage",
    input=GroupReorderIn,
    output=ComboDetailOut,
    expose_api=True,
    ai={
        "description": "Put the courses of a menu in a new order (the order the till asks them in): give every "
        "course id, in order.",
        "risk": "normal",
        "check": "combo.combo.get",
        "asks": {
            "en": (
                "reorder the courses of the kids' menu: starter, main, dessert",
                "the dessert course should come before the main one",
            ),
            "es": (
                "ordena los platos del menú infantil: entrante, segundo y postre",
                "en el menú vegano, que el postre vaya antes que el segundo",
            ),
        },
    },
)
def reorder_groups(ctx: OperationContext, data: GroupReorderIn) -> dict:
    combo = find_combo(data.id, data.combo, lock=True)
    _reordered(combo.groups.select_for_update(), data.group_ids)
    record_event(ctx, events.GROUP_REORDERED, {"combo_id": str(combo.id)})
    return load_detail(combo.id, ctx.scope)

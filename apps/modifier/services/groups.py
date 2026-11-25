"""The writes on a group (MODIFIER-F02, F03)."""

from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.modifier import events
from apps.modifier.models import ModifierGroup
from apps.modifier.queries.reads import find_group, load_group
from apps.modifier.schemas.fields import DeletedOut
from apps.modifier.schemas.groups import MAX_BELOW_MIN, GroupIn, GroupOut, GroupPatchIn, GroupRefIn
from apps.modifier.services.defaults import _too_many_defaults
from apps.modifier.services.writes import GROUP_NAME_TAKEN, _actor, _save


@operation(
    "modifier.group.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="modifier.manage",
    input=GroupIn,
    output=GroupOut,
    ai={
        "description": "Create a modifier group (e.g. «Sauces», «Doneness») with how many options must be chosen "
        "(a minimum of 1 or more makes it required; a maximum of 0 is no ceiling) and whether one can repeat. It "
        "starts empty: the till asks for it once it has its options (modifier.option.create) and is applied to "
        "products or categories (modifier.link.attach, which base.assistant.find_tools gives you when you lack it). "
        "You can do both: offer it. On screen, both are done on the group's sheet in Modifiers (/modifier/groups); a "
        "product's own form has none.",
        "risk": "normal",
        "asks": {
            "en": ("create a sauces group for the pizzas", "new Doneness group, required, one choice only"),
            "es": (
                "crea un grupo de salsas para las pizzas",
                "nuevo grupo Punto de la carne, obligatorio y de una sola opción",
            ),
        },
    },
)
def create_group(ctx: OperationContext, data: GroupIn) -> dict:
    _check_group_name(data.name)
    group = ModifierGroup(**data.model_dump(), created_by=_actor(ctx), updated_by=_actor(ctx))
    _save(group)
    record_event(ctx, events.GROUP_CREATED, _group_payload(group))
    return load_group(group.id)


@operation(
    "modifier.group.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="modifier.manage",
    input=GroupPatchIn,
    output=GroupOut,
    ai={
        "description": "Change a modifier group, named by its id or its name; what is not sent is kept.",
        "risk": "normal",
        "check": "modifier.group.get",
        "asks": {
            "en": (
                "make the Sauces group required",
                "change Extras so up to three can be picked",
            ),
            "es": (
                "haz que el grupo Salsas sea obligatorio",
                "cambia el grupo Extras para que se puedan elegir hasta tres",
            ),
        },
    },
)
def update_group(ctx: OperationContext, data: GroupPatchIn) -> dict:
    group = find_group(data.id, data.group, lock=True)
    sent = data.model_dump(
        exclude_unset=True, exclude_none=True, exclude={"id", "group"}
    )
    changes = {
        field: value for field, value in sent.items() if getattr(group, field) != value
    }
    if not changes:
        return load_group(group.id)
    minimum = changes.get("min_choices", group.min_choices)
    maximum = changes.get("max_choices", group.max_choices)
    if maximum and maximum < minimum:
        field = "max_choices" if "max_choices" in changes else "min_choices"
        raise InvalidPayload(
            str(MAX_BELOW_MIN), code="invalid_field", fields={field: str(MAX_BELOW_MIN)}
        )
    if "name" in changes and changes["name"].casefold() != group.name.casefold():
        _check_group_name(changes["name"])
    if (
        "max_choices" in changes
        and maximum
        and group.options.filter(is_default=True).count() > maximum
    ):
        raise _too_many_defaults("max_choices")
    for field, value in changes.items():
        setattr(group, field, value)
    group.updated_by = _actor(ctx)
    _save(group, update_fields=[*changes, "updated_by", "updated_at"])
    record_event(ctx, events.GROUP_UPDATED, _group_payload(group))
    return load_group(group.id)


@operation(
    "modifier.group.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="modifier.manage",
    input=GroupRefIn,
    output=DeletedOut,
    ai={
        "description": "Delete a modifier group, named by its id or its name, with all its options and the "
        "products and categories it applied to; what was already ordered keeps its copy.",
        "risk": "high",
        "check": "modifier.group.get",
        "asks": {
            "en": (
                "delete the Sauces group and all its choices",
                "remove the Doneness modifier group",
            ),
            "es": (
                "borra el grupo Salsas con todas sus opciones y asignaciones",
                "elimina el grupo de suplementos Punto de la carne, los tiques antiguos no cambian",
            ),
        },
    },
)
def delete_group(ctx: OperationContext, data: GroupRefIn) -> dict:
    group = find_group(data.id, data.group, lock=True)
    payload, group_id = _group_payload(group), group.id
    group.delete()
    record_event(ctx, events.GROUP_DELETED, payload)
    return {"id": group_id}


def _check_group_name(name: str) -> None:
    if ModifierGroup.objects.filter(name__iexact=name).exists():
        raise Conflict(
            str(GROUP_NAME_TAKEN),
            code="modifier.group_name_taken",
            fields={"name": str(GROUP_NAME_TAKEN)},
        )


def _group_payload(group: ModifierGroup) -> dict:
    return {"id": str(group.id), "name": group.name}

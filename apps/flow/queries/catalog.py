"""The catalog (``flow.catalog.read``): the events, actions and reads of the active apps an automation can
start on and be granted, never a name made up here, with the data each one asks for and leaves."""

import importlib
from importlib.util import find_spec

from django.utils import translation
from live.assistant import description, risk
from live.context import OperationContext, Scope
from live.meta import LiveAppConfig, module_configs
from live.operations import Operation, operation, registry

from base import apps_on
from base import assistant as hub_assistant
from apps.flow.schemas.catalog import CatalogIn, CatalogOut

from .reads import VIEW

#: What needs a person in front that an automation may still be granted, only for an «Ask the assistant» step that
#: asks first: cancelling a booking a customer asks to cancel, done once someone who may cancel it says yes (Zapier's
#: Human in the Loop and n8n's human review gate the step that cannot be undone; Fresha's AI Concierge cancels within
#: the business's policy). Never what is done in person, money, fiscal records nor erasing.
ASK_FIRST = frozenset({"reservation.reservation.cancel", "appointment.appointment.cancel"})


def installed_apps() -> dict[str, LiveAppConfig]:
    """Every installed module but this one, on or off: whose recipes still fix what was built from them."""
    return {config.label: config for config in module_configs() if config.label != "flow"}


def off_apps(scope: Scope) -> dict[str, LiveAppConfig]:
    """The installed modules that are not on in ``scope``'s business (turned off, or without the right to them): what
    an automation built before still names, and the editor says why it is missing."""
    active = active_apps(scope)
    return {label: config for label, config in installed_apps().items() if label not in active}


def active_apps(scope: Scope) -> dict[str, LiveAppConfig]:
    """The modules active in ``scope``'s business, but this one, as the platform resolves them (``base.apps_on``)."""
    active = apps_on.active_apps(scope)
    return {label: config for label, config in installed_apps().items() if label in active}


def catalog_events(scope: Scope) -> dict[str, LiveAppConfig]:
    """``{event name: its app}``: the ``events.ALL`` of every active app."""
    return _events_of(active_apps(scope))


def _events_of(apps: dict[str, LiveAppConfig]) -> dict[str, LiveAppConfig]:
    found: dict[str, LiveAppConfig] = {}
    for label, config in apps.items():
        module_name = f"{config.name}.events"
        if find_spec(module_name) is None:
            continue
        for name in getattr(importlib.import_module(module_name), "ALL", []):
            if name.startswith(f"{label}."):
                found[name] = config
    return found


def event_amounts(event: str) -> frozenset[str]:
    """The data the events of ``event``'s app bring that it declares as amounts (``events.AMOUNTS``), in whole minor
    units of their currency; none when its app declares none or is not installed."""
    config = installed_apps().get(event.split(".", 1)[0])
    module_name = f"{config.name}.events" if config else ""
    if not module_name or find_spec(module_name) is None:
        return frozenset()
    return frozenset(getattr(importlib.import_module(module_name), "AMOUNTS", ()))


def grantable_operations(scope: Scope) -> dict[str, Operation]:
    """``{operation name: operation}`` of the active apps whose permission the app declares: what a
    person can be granted (the platform-only reactions are left out)."""
    return _grantable_of(active_apps(scope))


def _grantable_of(apps: dict[str, LiveAppConfig]) -> dict[str, Operation]:
    granted: dict[str, Operation] = {}
    for name, op in registry.items():
        config = apps.get(op.app_label)
        if config is not None and op.permission in config.permissions:
            granted[name] = op
    return granted


def needs_a_person(op: Operation) -> bool:
    """An action the assistant confirms before running (``ai.risk == "high"``: voiding, refunding,
    erasing, sending to the tax agency…) or one done in person (``ai.in_person``: seating a party at the
    door): never for an automation, which acts with nobody in front."""
    return risk(op) == "high" or in_person(op)


def in_person(op: Operation) -> bool:
    """An action done in person (``ai.in_person``, a key of the ``ai=`` dictionary: seating a party at the door)."""
    return isinstance(op.ai, dict) and op.ai.get("in_person") is True


def asks_first(op: Operation) -> bool:
    """An action that needs a person in front that an «Ask me first» step may still propose (``ASK_FIRST``), never
    one done in person."""
    return op.name in ASK_FIRST and needs_a_person(op) and not in_person(op)


def yes_permission(op: Operation) -> str | None:
    """What a person's yes to ``op``'s change needs (``ASK_FIRST``): its own permission or, when that one only reaches
    what is theirs, the one over everybody's that its app names (``ai.yes_permission``, a key of the ``ai=`` dictionary).
    The automation's change reaches anybody's (Appointments' ``is_own``), and the yes lends nothing."""
    declared = op.ai.get("yes_permission") if isinstance(op.ai, dict) else None
    return declared or op.permission


def catalog_operations(scope: Scope) -> dict[str, Operation]:
    """What an automation may be granted and run: the grantable operations that do not need a person."""
    return {name: op for name, op in grantable_operations(scope).items() if not needs_a_person(op)}


def ask_first_catalog(scope: Scope) -> dict[str, Operation]:
    """What an «Ask the assistant» step that asks first may be granted and offered: the catalog and ``ASK_FIRST``."""
    return {
        name: op
        for name, op in grantable_operations(scope).items()
        if not needs_a_person(op) or asks_first(op)
    }


def asked_first(steps: list[dict]) -> set[str]:
    """The tools of the steps that ask first («Ask me first», the default of «Ask the assistant»)."""
    return {
        str(name)
        for step in steps
        if step.get("kind") == "assistant" and step.get("mode", "ask") == "ask"
        for name in step.get("tools") or []
    }


def read_permissions(scope: Scope, op: Operation) -> frozenset[str]:
    """The reads of ``op``'s app (its declared ``<app>.view…`` permissions): what a step may also need to
    answer with what it did, never to change anything else."""
    config = active_apps(scope).get(op.app_label)
    declared = config.permissions if config is not None else []
    return frozenset(permission for permission in declared if permission.split(".", 1)[-1].startswith("view"))


def _resolve_ref(schema: dict, defs: dict) -> dict:
    ref = schema.get("$ref")
    return defs.get(ref.rsplit("/", 1)[-1], {}) if ref else schema


def _field_type(prop: dict, defs: dict) -> tuple[str, list[str]]:
    for branch in prop.get("anyOf", []):
        if branch.get("type") != "null":
            return _field_type(branch, defs)
    prop = _resolve_ref(prop, defs)
    if "enum" in prop:
        return "choice", [str(value) for value in prop["enum"]]
    if "const" in prop:
        return "choice", [str(prop["const"])]
    kind = (
        prop.get("format")
        if prop.get("format") in ("uuid", "date", "date-time", "time")
        else None
    )
    return kind or str(prop.get("type", "object")), []


def action_fields(op: Operation) -> list[dict]:
    """What an operation asks for: one field each, with its type, whether it is required and its words."""
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})
    required = set(schema.get("required", []))
    fields = []
    for name, prop in schema.get("properties", {}).items():
        declared = op.input.model_fields.get(name)
        kind, choices = _field_type(prop, defs)
        fields.append(
            {
                "name": name,
                "type": kind,
                "required": name in required,
                "description": (declared.description if declared else None)
                or prop.get("description", ""),
                "choices": choices,
            }
        )
    return fields


def step_fields(op: Operation) -> dict[str, dict]:
    """The fields a step of ``op`` leaves for the next ones (``steps.<id>.<field>``), by name, with their schema: its
    output's, a list's first row's."""
    return _step_fields(op, op.output.model_json_schema())


def _step_fields(op: Operation, schema: dict) -> dict[str, dict]:
    """``step_fields`` from ``schema``, ``op``'s output's already built."""
    properties = schema.get("properties", {})
    if op.kind == "query" and "rows" in properties:
        return _resolve_ref(properties["rows"].get("items", {}), schema.get("$defs", {})).get("properties", {})
    return properties


def step_data(op: Operation) -> dict[str, dict]:
    """Every datum a step of ``op`` leaves that a path names (``steps.<id>.<path>``), by its path below the step, with
    its schema: the fields ``step_fields`` gives and, at any depth, those of an object among them — the line a step
    adds to a cart (``item.unit_price``), the invoice of a sale (``invoice.total_amount``) —; never inside a list,
    which no path names."""
    schema = op.output.model_json_schema()
    defs = schema.get("$defs", {})
    found: dict[str, dict] = {}

    def walk(fields: dict, prefix: str, seen: frozenset[str]) -> None:
        for name, prop in fields.items():
            path = f"{prefix}{name}"
            found[path] = prop
            for branch in (prop, *prop.get("anyOf", [])):
                ref = branch.get("$ref")
                inner = _resolve_ref(branch, defs).get("properties")
                if inner and ref not in seen:
                    walk(inner, f"{path}.", seen | {ref} if ref else seen)

    walk(_step_fields(op, schema), "", frozenset())
    return found


def action_outputs(op: Operation) -> list[str]:
    """What a step of ``op`` leaves for the next ones, by the path the engine resolves below the step (``step_data``):
    its output's fields (a list's first row's), each object among them followed by what it holds (``item``,
    ``item.unit_price``), never inside a list; and ``found`` and ``count`` for a read."""
    names = list(step_data(op))
    if op.kind == "query":
        names += [name for name in ("found", "count") if name not in names]
    return names


def in_part(data: CatalogIn, app: str, name: str) -> bool:
    """Whether the part of the catalog ``data`` asks for holds the event or action ``name`` of ``app``: an app it names
    or a name it says; with neither, the whole catalog does."""
    if data.apps is None and data.names is None:
        return True
    return app in (data.apps or ()) or name in (data.names or ())


@operation(
    "flow.catalog.read",
    kind="query",
    permission=VIEW,
    input=CatalogIn,
    output=CatalogOut,
    ai={
        "asks": {
            "en": (
                "what can my automations react to, and what can they do?",
                "which events and actions can I use in an automation?",
            ),
            "es": (
                "¿qué eventos y acciones puedo usar en una automatización?",
                "¿a qué puede reaccionar una automatización en mi negocio?",
            ),
        },
        "description": "What an automation can start on and do in this business: the events of the active apps "
        "(`sale.sale.completed`…) and the actions and reads it can be granted, with the data each one asks for. "
        "One with `ask_first` only goes in an `assistant` step whose `mode` is `ask`. A business with many apps "
        "has more than you can read at once: first read the names in the apps you need (`apps` and `only_names`), "
        "then read whole only the events and actions you will use, by name (`names`)."
    },
)
def read_catalog(ctx: OperationContext, data: CatalogIn) -> dict:
    with translation.override(ctx.language):
        events = [
            {"name": name, "app": config.label, "app_name": str(config.verbose_name)}
            for name, config in catalog_events(ctx.scope).items()
            if in_part(data, config.label, name)
        ]
        apps = active_apps(ctx.scope)
        chosen = {name: op for name, op in ask_first_catalog(ctx.scope).items() if in_part(data, op.app_label, name)}
        actions = [] if data.only_names else [_whole_action(name, op, apps) for name, op in chosen.items()]
        off = [{"app": label, "app_name": str(config.verbose_name)} for label, config in off_apps(ctx.scope).items()]
    return {
        "events": sorted(events, key=lambda event: (event["app"], event["name"])),
        "actions": sorted(actions, key=lambda action: (action["app"], action["name"])),
        "action_names": sorted(chosen, key=lambda name: (chosen[name].app_label, name)) if data.only_names else [],
        "off_apps": sorted(off, key=lambda app: app["app"]),
    }


def _whole_action(name: str, op: Operation, apps: dict[str, LiveAppConfig]) -> dict:
    return {
        "name": name,
        "kind": op.kind,
        "app": op.app_label,
        "app_name": str(apps[op.app_label].verbose_name),
        "description": description(op),
        "fields": action_fields(op),
        "outputs": action_outputs(op),
        "assistant": hub_assistant.tools.is_tool(op),
        "ask_first": asks_first(op),
    }

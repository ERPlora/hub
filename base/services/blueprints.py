"""Settings › Data: loading a template or a file (``base.blueprint.*``), undoing a load (``base.import.undo``) and
the loads that wait for an app still being set up.

``base.blueprint.import`` loads a template or a file and keeps it as an ``ImportBatch``, ``base.import.undo`` removes
exactly what one load created; the rules are ``base.blueprint``'s.
"""

from collections.abc import Collection, Iterable
from typing import Any

from django.utils import timezone, translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, NotFound, OperationError
from live.operations import AI, operation
from live.operations import get as get_operation
from live.outbox import record_event

from base import activation, blueprint, business, entitlement, events
from base.activation import CREATING
from base.models.blueprints import ImportBatch
from base.permissions import ADMINISTER_HUB
from base.schemas.apps import AppChangeIn
from base.schemas.blueprints import (
    BlueprintImportIn,
    BlueprintSourceIn,
    BlueprintSummaryOut,
    ImportOut,
    ImportUndoIn,
    ImportUndoOut,
)


def _who(ctx: OperationContext) -> str:
    actor = ctx.actor
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.get_username())[:150]
    return str(actor)[:150]


def _import_summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The template by its name and its language, as the Import screen shows them, and, when no apps are chosen (an
    empty list loads every one too), the apps it loads by their names."""
    seed = blueprint.seeds.template(arguments.get("template") or "")
    if seed is None:
        return fields
    language = business.babel_locale(ctx.language).languages.get(seed.language, seed.language)
    chosen = arguments.get("apps")
    shown = [
        {**field, "value": f"{seed.name} ({language})"} if field["name"] == "template" else field
        for field in fields
        if chosen or field["name"] != "apps"
    ]
    if chosen:
        return shown
    apps = [str(blueprint.datasets.app_label(app)) for app in seed.bundle.manifest["apps"]]
    title = gettext(BlueprintImportIn.model_fields["apps"].title)
    return [*shown, {"name": "apps", "label": title, "kind": "list", "value": apps, "titled": True, "named": True}]


@operation(
    "base.blueprint.inspect",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=BlueprintSourceIn,
    output=BlueprintSummaryOut,
    ai=AI(
        description="Says what a template of the catalogue brings, app by app, before loading it; it writes nothing.",
        asks={
            "en": ("what does the hair salon template bring?", "before loading it, what's inside the bar template?"),
            "es": (
                "antes de cargarla, ¿qué incluye la plantilla de bar?",
                "¿qué viene en la plantilla de restaurante?",
            ),
        },
    ),
)
def blueprint_inspect(ctx: OperationContext, data: BlueprintSourceIn) -> dict:
    """What a template or an uploaded file brings and what of it would load here.

    It writes nothing: a command only because its input is a file, which no query string carries (a query is served
    by GET), like the rehearsal (``dry_run``) of the apps' imports.
    """
    with translation.override(ctx.language):
        bundle, seed = blueprint.preview.open_source(data.template, data.file_base64)
        return blueprint.preview.summary(ctx, bundle, seed=seed)


@operation(
    "base.blueprint.import",
    kind="command",
    permission=ADMINISTER_HUB,
    input=BlueprintImportIn,
    output=ImportOut,
    ai={
        "description": (
            "Loads a template of the catalogue (a restaurant, a hair salon…), or a copy of a business the person "
            "attached in the chat (a .blueprint.zip, from another business or a backup: its name in file_base64), "
            "into this business: turns on its apps "
            "that are off (with the apps they need, within the plan's limit of apps), then loads its menu or services, "
            "its tables and the rest of its apps' data, app by app; what is already there is left as it was. An app "
            "still being set up («waiting») brings its data by itself when it is ready: nothing to do but say so. "
            "Returns the report of what went in, with why an app could not be turned on. Never brings people, PINs or "
            "fiscal data. Use this, not blueprint.list or blueprint.inspect, when asked to load, import or apply one. "
            f"A copy is made in the business it comes from. {blueprint.export.TO_ANOTHER_BUSINESS}"
        ),
        "risk": "high",
        "asks": {
            "en": (
                "load the restaurant template",
                "set me up like a hair salon",
                "fill the business with the café starter menu",
                "import the restaurant template",
                "load this copy of another business I attached",
            ),
            "es": (
                "carga la plantilla de restaurante",
                "quiero empezar con la plantilla de bar",
                "importa la plantilla de restaurante",
                "cárgame la copia de otro bar que te he adjuntado",
            ),
        },
        "summary": _import_summary,
    },
)
def blueprint_import(ctx: OperationContext, data: BlueprintImportIn) -> dict:
    """Load a template, a file or what a load left out and keep its report and the rows it created.

    First it turns on the apps the blueprint lists that are off (a hub is born with every app off),
    each through ``base.app.enable`` and in this transaction; one refused (the plan's limit, no right to it) stays
    off, loads nothing and its report says why. A backup turns on the apps it lists too. One whose tables its hub's
    database is still making (``creating``) is waited for: a template's part of it loads when the worker turns it on
    (``_load_what_waited``); a file is not kept, so its report says to upload it again."""
    with translation.override(ctx.language):
        retried = None
        if data.retry_of is not None:
            retried = ImportBatch.objects.select_for_update().filter(pk=data.retry_of).first()
            if retried is None:
                raise NotFound(gettext("This load is not there any more."), code="base.import_not_found")
            blocked = blueprint.loads.retry_state(ctx, retried)
            if blocked:
                code, message = blueprint.loads.RETRY_BLOCKED[blocked]
                raise Conflict(str(message), code=code)
            bundle, seed = blueprint.preview.open_source(retried.template_key, "")
            apps = list(retried.apps)
            # What it still waited for (an app whose setup failed) is this load's now: one report, one load of it.
            _stop_waiting(ctx, [retried], None, blueprint.loads.STOPPED_RETRIED)
        else:
            bundle, seed = blueprint.preview.open_source(data.template, data.file_base64)
            apps = list(dict.fromkeys(data.apps)) if data.apps is not None else []
        # A hub is born with every app off. The apps the blueprint lists are turned on first, and
        # what loads reads its rows, never the cache of the apps off kept before this change.
        with activation.changing(ctx.scope.key):
            refused = _turn_on_listed(ctx, bundle.manifest["apps"], set(apps))
            waiting = _being_set_up(ctx, bundle.manifest["apps"], set(apps)) - refused.keys()
            if seed is None:
                refused |= dict.fromkeys(waiting, str(blueprint.loads.FILE_BEING_SET_UP))
                waiting = set()
            applied = blueprint.loading.apply(ctx, bundle, apps=set(apps) if apps else None, refused=refused, waiting=waiting)
        load = ImportBatch.objects.create(
            name=bundle.manifest["name"],
            source=ImportBatch.Source.CATALOG if seed else ImportBatch.Source.FILE,
            template_key=seed.key if seed else "",
            template_version=seed.version if seed else "",
            purpose=bundle.manifest["purpose"],
            apps=apps,
            status=applied.report["status"],
            report=applied.report,
            created_rows=applied.created,
            created_by=_who(ctx),
            retry_of=retried,
        )
        record_event(ctx, events.BLUEPRINT_IMPORTED, {"id": str(load.pk), "status": load.status})
        return blueprint.loads.describe_load(ctx, load)


@operation(
    "base.import.undo",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ImportUndoIn,
    output=ImportUndoOut,
    ai=AI(
        description=(
            "Undoes one load of a template or a file: removes exactly the rows it brought; what was made afterwards "
            "stays."
        ),
        risk="high",
        asks={
            "en": ("undo the template I just loaded", "take back that import, it was the wrong file"),
            "es": ("deshaz la plantilla que acabo de cargar", "echa atrás esa importación, era el archivo equivocado"),
        },
    ),
)
def import_undo(ctx: OperationContext, data: ImportUndoIn) -> dict:
    """Remove exactly the rows one load created, once."""
    with translation.override(ctx.language):
        load = ImportBatch.objects.select_for_update().filter(pk=data.id).first()
        if load is None:
            raise NotFound(gettext("This load is not there any more."), code="base.import_not_found")
        if load.undone_at is not None:
            raise Conflict(gettext("This load was undone already."), code="base.import_undone")
        removed = blueprint.removal.undo(ctx, load.created_rows)
        _stop_waiting(ctx, [load], None, blueprint.loads.STOPPED_UNDONE)
        load.undone_at = timezone.now()
        load.save(update_fields=["undone_at"])
        record_event(ctx, events.IMPORT_UNDONE, {"id": str(load.pk)})
        return {"id": load.pk, "apps": removed["apps"]}


def _wanted(listed: Iterable[str], selected: set[str], graph: dict) -> list[str]:
    """The apps of a blueprint's manifest a load turns on: those ``selected``, when the person chose some."""
    return [app for app in dict.fromkeys(listed) if app in graph and (not selected or app in selected)]


def _being_set_up(ctx: OperationContext, listed: Iterable[str], selected: set[str]) -> set[str]:
    """Which of the apps a load turns on its hub's own database is still making the tables of, read from their rows."""
    states = activation.states_of(ctx.scope)
    return {app for app in _wanted(listed, selected, activation.module_graph()) if states[app].state == CREATING}


def _waiting_loads() -> list[ImportBatch]:
    """The loads of this business still waiting for an app, oldest first, locked as what is written on them is."""
    return list(
        ImportBatch.objects.select_for_update()
        .filter(report__apps__contains=[{"status": blueprint.loading.WAITING}], undone_at__isnull=True)
        .order_by("created_at", "id")
    )


def _stop_waiting(ctx: OperationContext, loads: Iterable[ImportBatch], apps: Collection[str] | None, reason: Any) -> None:
    """``loads`` stop waiting for ``apps`` (``None``: for any): their report says ``reason``, and they load nothing."""
    for load in loads:
        waited = [app for app in blueprint.loads.waiting_apps(load) if apps is None or app in apps]
        if waited:
            blueprint.loads.stop_waiting(ctx, load, waited, reason)
            load.save(update_fields=["report", "status", "created_rows"])


def _load_what_waited(ctx: OperationContext, on: Iterable[str]) -> None:
    """The apps ``on`` just went on: what the loads of this business waited to bring of them comes now, in this same
    transaction (hub#609). Nothing but those rows says what waits: a worker that dies here undid the app going on, and
    the next one does both, so nothing is lost or left half done. Oldest first: what is there already is left as it is."""
    on = set(on)
    for load in _waiting_loads():
        waited = set(blueprint.loads.waiting_apps(load)) & on
        if waited:
            blueprint.loads.finish_waiting(ctx, load, waited)
            load.save(update_fields=["report", "status", "created_rows"])
            record_event(ctx, events.BLUEPRINT_IMPORTED, {"id": str(load.pk), "status": load.status})


def _turn_on_listed(ctx: OperationContext, listed: Iterable[str], selected: set[str]) -> dict[str, str]:
    """Before a blueprint loads, turn on the apps its manifest lists (only those ``selected``, when the person chose
    some) that are off here, each through ``base.app.enable``: its plan's limit, its rights, what it needs along and
    its event, as if the person turned it on in Apps. Their roots first, chosen, so what they need comes along and
    does not count against the limit (as a vertical's template, ``base.activation.template``); then any listed app
    still off. An app refused stays off and its reason is returned, by app: the rest are turned on and load, or wait
    for their tables (``creating``: ``_being_set_up``)."""
    graph = activation.module_graph()
    wanted = _wanted(listed, selected, graph)
    roots = activation.roots(set(wanted) | activation.needs(wanted, graph), graph)
    enable = get_operation("base.app.enable")
    blocked = entitlement.blocked_apps(ctx.scope)
    refused: dict[str, str] = {}
    for app in [app for app in wanted if app in roots] + [app for app in wanted if app not in roots]:
        if app not in blocked and activation.states_of(ctx.scope)[app].on:
            continue
        try:
            enable(ctx, AppChangeIn(app=app))
        except OperationError as refusal:
            refused[app] = refusal.message
    return refused

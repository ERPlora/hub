"""Settings › Data's reads: the catalogue of templates, the export, the loads and the apps' data (their rules are
``base.blueprint``'s)."""

import base64

from django.utils import timezone, translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import AI, operation

from base import blueprint, home
from base.apps_on import active_apps
from base.models import Hub
from base.models.blueprints import ImportBatch
from base.permissions import ADMINISTER_HUB
from base.schemas.blueprints import (
    BlueprintExportIn,
    BlueprintFileOut,
    BlueprintListIn,
    BlueprintListOut,
    DatasetListIn,
    DatasetListOut,
    ImportIdIn,
    ImportListIn,
    ImportListOut,
    ImportOut,
)


# ── Data: blueprints, imports and reset ───────────────
#: The loads Settings › Data lists: the latest ones.
IMPORTS_SHOWN = 50


@operation(
    "base.blueprint.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=BlueprintListIn,
    output=BlueprintListOut,
    ai=AI(
        description=(
            "Lists the templates of businesses this hub can load (a restaurant, a hair salon…): what each one brings "
            "(its apps, its menu or services, its tables) and whether this business is still empty."
        ),
        asks={
            "en": (
                "which business templates can I start from?",
                "show me the business templates",
                "is there a template for a bakery?",
            ),
            "es": (
                "¿qué plantillas de negocio hay?",
                "¿tenéis alguna plantilla para una panadería?",
                "enséñame los modelos de negocio para empezar",
            ),
        },
    ),
)
def blueprint_list(ctx: OperationContext, data: BlueprintListIn) -> dict:
    """The seeds by vertical: the hub's country first, then the person's language, then the hub's vertical."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        country, vertical = (hub.country, hub.vertical) if hub else ("", "")
        seeds = sorted(
            blueprint.seeds.catalog(),
            key=lambda seed: (
                bool(country) and seed.country != country,
                seed.language != ctx.language,
                bool(vertical) and seed.vertical != vertical,
                seed.key,
            ),
        )
        return {"templates": [blueprint.preview.template_out(seed) for seed in seeds], "empty": blueprint.export.no_rows_yet(ctx)}


@operation(
    "base.blueprint.export",
    kind="query",
    permission=ADMINISTER_HUB,
    input=BlueprintExportIn,
    output=BlueprintFileOut,
    ai=AI(
        description=(
            "Writes a .blueprint.zip of this business: the apps chosen and, of those marked, their data. A template "
            "never takes personal data (customers); a backup takes them. People, PINs and fiscal data never."
        ),
        risk="high",
        # Only for live.E020 (it checks the whole app): base.assistant.tools.NOT_FROM_CHAT keeps this out of the chat
        # (pinned by base/tests/test_assistant_tools.py).
        asks={
            "en": ("make a backup of the whole business", "export my menu as a template for the other bar"),
            "es": ("haz una copia de seguridad del negocio", "exporta mi carta como plantilla para el otro local"),
        },
    ),
)
def blueprint_export(ctx: OperationContext, data: BlueprintExportIn) -> dict:
    """The file of the apps and datasets chosen, in base64 for the screen to save."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        on = active_apps(ctx.scope)
        shown = {config.label for config in home.shown_modules.shown_modules(demo_hub=bool(hub and hub.is_demo))}
        registered = list(dict.fromkeys(data.apps))
        missing = [app for app in registered if app not in shown or app not in on]
        if missing:
            raise InvalidPayload(
                gettext("The app «%(app)s» is not on in this business.") % {"app": missing[0]},
                fields={"apps": gettext("Choose only apps that are on in this business.")},
            )
        if not set(data.data) <= set(registered):
            raise InvalidPayload(
                gettext("The data of an app travels only with the app."),
                fields={"data": gettext("Mark the app too, not only its data.")},
            )
        named = set(data.datasets)
        own = {app: [part.key for part in blueprint.datasets.datasets_of(app)] for app in dict.fromkeys(data.data)}
        if not named <= {key for keys in own.values() for key in keys}:
            raise InvalidPayload(
                gettext("Some of the data chosen belongs to no app whose data travels."),
                fields={"datasets": gettext("Choose only data of the app it belongs to.")},
            )
        chosen = {app: [key for key in keys if key in named] or keys for app, keys in own.items()}
        bundle = blueprint.archive.Bundle(
            manifest=blueprint.archive.manifest(
                name=data.name.strip(),
                language=data.language,
                country=hub.country if hub else "",
                purpose=data.purpose,
                created_at=timezone.now().isoformat(),
                vertical=hub.vertical if hub else "",
                apps=registered,
            ),
            data=blueprint.export.export_data(ctx, chosen, purpose=data.purpose),
        )
        # INVENTORY-F33: the rows' own photos travel inside the file; the library's images by their reference.
        bundle.media = blueprint.photos.export_media(ctx, bundle.data)
        return {
            "filename": blueprint.archive.file_name(data.name, data.language),
            "content_type": "application/zip",
            "content_base64": base64.b64encode(blueprint.archive.write_zip(bundle)).decode("ascii"),
        }


@operation(
    "base.import.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ImportListIn,
    output=ImportListOut,
    ai=AI(
        description=(
            "Lists the templates and files loaded into this business, newest first, each with its report, whether it "
            "can be undone and whether what did not go in can be loaded again."
        ),
        asks={
            "en": ("what have we imported so far?", "list the templates we loaded"),
            "es": ("¿qué importaciones hemos hecho?", "lista las plantillas que hemos cargado"),
        },
    ),
)
def import_list(ctx: OperationContext, data: ImportListIn) -> dict:
    """The loads, newest first; the last one, when it did not go in whole and stands, is shown first."""
    loads = list(ImportBatch.objects.order_by("-created_at", "-id")[:IMPORTS_SHOWN])
    latest = loads[0] if loads else None
    unfinished = latest if latest and latest.status != ImportBatch.Status.COMPLETE and latest.undone_at is None else None
    return {
        "imports": [blueprint.loads.describe_load(ctx, load) for load in loads],
        "unfinished": blueprint.loads.describe_load(ctx, unfinished) if unfinished else None,
    }


@operation(
    "base.import.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ImportIdIn,
    output=ImportOut,
    ai=AI(
        description="Reads one template or file loaded into this business, by its id, as the list of loads shows it.",
        asks={
            "en": ("what did that template load bring in?", "show me the report of yesterday's import"),
            "es": ("¿qué metió esa carga de plantilla?", "enséñame el informe de la importación de ayer"),
        },
    ),
)
def import_detail(ctx: OperationContext, data: ImportIdIn) -> dict:
    """One load of Settings › Data, as its row."""
    load = ImportBatch.objects.filter(pk=data.id).first()
    if load is None:
        raise NotFound(gettext("This load is not there any more."))
    return blueprint.loads.describe_load(ctx, load)


@operation(
    "base.dataset.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=DatasetListIn,
    output=DatasetListOut,
    ai=AI(
        description=(
            "Lists the apps on in this business and, of each, what can travel in an export and how many rows it has."
        ),
        asks={
            "en": ("what data can I export?", "how many rows does each app have?"),
            "es": ("¿cuántos registros tiene cada app?", "¿qué se puede sacar en una exportación?"),
        },
    ),
)
def dataset_list(ctx: OperationContext, data: DatasetListIn) -> dict:
    """Every app on, with its datasets and their rows: what an export can take."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        on = active_apps(ctx.scope)
        counts = blueprint.export.counts(ctx)
        apps = [
            {
                "id": config.label,
                "label": str(config.verbose_name),
                "icon": config.icon,
                "datasets": [
                    {"key": part.key, "label": str(part.label), "rows": counts.get(part.key, 0), "personal": part.personal}
                    for part in blueprint.datasets.datasets_of(config.label)
                ],
            }
            for config in home.shown_modules.shown_modules(demo_hub=bool(hub and hub.is_demo))
            if config.label in on
        ]
        return {"apps": sorted(apps, key=lambda app: app["label"])}

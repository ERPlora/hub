"""What the business has: the rows of the datasets chosen, for an export, and how many each dataset has."""

from django.utils import translation
from live.context import OperationContext

from base.apps_on import active_apps
from base.blueprint.archive import PURPOSE_BACKUP
from base.blueprint.datasets import DATASETS, dataset

#: What the assistant reads where a person may ask to take the menu or the business elsewhere: ``base.blueprint.export``
#: is never a tool of the chat, so this is how it learns where that file is made and what it takes.
TO_ANOTHER_BUSINESS = (
    "To take this business or part of it (the menu, the customers…) to another business or a new venue, it is "
    "exported on Settings (/settings) › «Data and backups» › «Export» (in Spanish «Ajustes» › «Datos y copias» › "
    "«Exportar»), as a «Template to share» («Plantilla para compartir»: never the customers) or a «Backup of this "
    "business» («Copia de seguridad de este negocio»: the customers too), choosing the apps and which of their data "
    "go: the products and services go with their own photos inside; never the business's history, people, PINs or "
    "fiscal data. The other business loads that file. It is made only on that screen, never in the chat."
)


def selection_of(data: dict[str, list[dict]]) -> dict[str, list[str]]:
    """The datasets of ``data`` by app: what an export of the same parts asks."""
    chosen: dict[str, list[str]] = {}
    for key in data:
        chosen.setdefault(key.split(".", 1)[0], []).append(key)
    return chosen


def export_data(ctx: OperationContext, chosen: dict[str, list[str]], *, purpose: str) -> dict[str, list[dict]]:
    """The rows of the datasets ``chosen`` (by app) of the apps on; personal data only in a backup."""
    on = active_apps(ctx.scope)
    exported = {}
    with translation.override(ctx.language):
        for dataset in DATASETS:
            if dataset.key not in chosen.get(dataset.app, ()) or dataset.app not in on:
                continue
            if dataset.personal and purpose != PURPOSE_BACKUP:
                continue
            rows = dataset.rows(ctx)
            if rows:
                exported[dataset.key] = rows
    return exported


def counts(ctx: OperationContext) -> dict[str, int]:
    """How many rows each dataset of the apps on has."""
    on = active_apps(ctx.scope)
    return {dataset.key: dataset.count(ctx) for dataset in DATASETS if dataset.app in on}


def no_rows_yet(ctx: OperationContext) -> bool:
    """Nothing a template brings is in the business yet: no category, product, service, zone or table."""
    return not any(count for key, count in counts(ctx).items() if not dataset(key).personal)

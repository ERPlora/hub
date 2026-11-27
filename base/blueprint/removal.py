"""Undoing a load and resetting apps, through each app's own delete (or archive)."""

from django.utils import translation
from live.context import OperationContext
from live.errors import NotFound, OperationError

from base.apps_on import active_apps
from base.blueprint.calls import MAX_PROBLEMS, Dataset, reason
from base.blueprint.datasets import app_label, datasets_of, every_dataset


def undo(ctx: OperationContext, created: dict[str, list[str]]) -> dict:
    """Remove exactly the rows of ``created`` (a load's), last dataset first; one already gone counts as gone."""
    with translation.override(ctx.language):
        removals = {}
        for dataset in reversed(every_dataset()):
            ids = created.get(dataset.key)
            if ids:
                _remove(ctx, dataset, ids, removals.setdefault(dataset.app, _removal(dataset.app)))
        return {"apps": list(removals.values())}


def reset_plan(ctx: OperationContext) -> list[dict]:
    """The apps on that have rows, each with how many it would lose and of what."""
    with translation.override(ctx.language):
        on = active_apps(ctx.scope)
        plan = []
        for app in dict.fromkeys(dataset.app for dataset in every_dataset()):
            if app not in on:
                continue
            parts = [{"key": dataset.key, "label": str(dataset.label), "rows": dataset.count(ctx)} for dataset in datasets_of(app)]
            total = sum(part["rows"] for part in parts)
            if total:
                plan.append({"id": app, "label": app_label(app), "rows": total, "datasets": parts})
        return plan


def reset(ctx: OperationContext, chosen: list[str]) -> dict:
    """Remove every row of the datasets of the apps ``chosen``, last dataset first."""
    with translation.override(ctx.language):
        on = active_apps(ctx.scope)
        removals = {}
        for dataset in reversed(every_dataset()):
            if dataset.app in chosen and dataset.app in on:
                _remove(ctx, dataset, dataset.ids(ctx), removals.setdefault(dataset.app, _removal(dataset.app)))
        return {"apps": [removals[app] for app in dict.fromkeys(chosen) if app in removals]}


def _removal(app: str) -> dict:
    return {"id": app, "label": app_label(app), "removed": 0, "failed": 0, "problems": []}


def _remove(ctx: OperationContext, dataset: Dataset, ids: list[str], removal: dict) -> None:
    for pk in ids:
        try:
            dataset.remove(ctx, pk)
        except NotFound:
            continue  # gone already: what undo wanted
        except OperationError as exc:
            removal["failed"] += 1
            if len(removal["problems"]) < MAX_PROBLEMS:
                removal["problems"].append(f"{dataset.label}: {reason(exc)}")
        else:
            removal["removed"] += 1

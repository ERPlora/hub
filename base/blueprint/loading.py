"""Loading a blueprint app by app, each part on its own, and the report of what happened to each."""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.meta import module_configs

from base import activation
from base.apps_on import active_apps
from base.blueprint.archive import PURPOSE_BACKUP, Bundle
from base.blueprint.calls import Dataset, Loaded
from base.blueprint.datasets import app_label, datasets_of, every_dataset

# Its lines keep the name they always had, whichever module of the package writes them.
logger = logging.getLogger("base.blueprint")

# Statuses of a dataset and of an app in the report of a load (the screen names each one).
APPLIED, PARTIAL, ALREADY, FAILED, EMPTY, DISCARDED = "applied", "partial", "already", "failed", "empty", "discarded"
INACTIVE, UNKNOWN, NOT_SELECTED = "inactive", "unknown", "not_selected"
# An app of a template its load turned on and its business's database is still making the tables of (hub#609): the load
# waits for it and brings what is its by itself when the worker turns it on. Only ``waiting`` is kept on the load; how
# its setup goes (``setup_failed``) is read from the app's row each time, so a retry or a failure is never out of step.
WAITING, SETUP_FAILED = "waiting", "setup_failed"
#: The language of who loaded a load that still waits, kept on its report for what the worker writes on it later.
REPORT_LANGUAGE = "language"

# Statuses of a whole load.
COMPLETE = "complete"

SOMETHING_WENT_WRONG = _("Something went wrong loading this part; nothing else was affected.")


@dataclass(frozen=True)
class Applied:
    """A load's report (what the screen shows) and the ids it created per dataset (what undo removes)."""

    report: dict
    created: dict[str, list[str]]


def _apps_of(bundle: Bundle) -> list[str]:
    """The apps of a blueprint: the ones its manifest turns on, then any its data names besides."""
    listed = list(bundle.manifest["apps"])
    listed += [key.split(".", 1)[0] for key in bundle.data if key.split(".", 1)[0] not in listed]
    return list(dict.fromkeys(listed))


def apply(ctx: OperationContext, bundle: Bundle, *, apps: set[str] | None, refused: dict[str, str] | None = None,
          waiting: Iterable[str] = ()) -> Applied:
    """Load ``bundle`` app by app (only ``apps`` if given), each part on its own, and say what happened to each.

    An app this hub does not have, or does not have on, loads nothing and is told, with why it is off when it could
    not be turned on (``refused``: its reason by app), or that the load waits for it (``waiting``, being set up:
    :func:`finish_waiting` brings its part); personal data loads only from a backup. Every dataset's failure stays in
    it: what it created before failing is kept and counted for undo.
    """
    waiting = set(waiting)
    with translation.override(ctx.language):
        on = active_apps(ctx.scope)
        known = {config.label for config in module_configs()}
        loads: dict[str, dict] = {}
        created: dict[str, list[str]] = {}
        for dataset in every_dataset():
            rows = bundle.data.get(dataset.key)
            if rows is None or (apps is not None and dataset.app not in apps) or dataset.app not in on:
                continue
            if dataset.personal and bundle.manifest["purpose"] != PURPOSE_BACKUP:
                loads[dataset.key] = _dataset_report(dataset, Loaded(), rows, discarded=True)
                continue
            loaded = _load(ctx, dataset, rows, bundle)
            if loaded.created and dataset.removable:
                created[dataset.key] = loaded.created
            loads[dataset.key] = _dataset_report(dataset, loaded, rows)
        app_reports = [
            _app_report(app, bundle, apps, on, known, loads, refused or {}, waiting) for app in _apps_of(bundle)
        ]
        report = {
            "status": _load_status(ctx, bundle.data, app_reports, created),
            "apps": app_reports,
            "dropped": list(bundle.dropped),
        }
        if any(app["status"] == WAITING for app in app_reports):
            report[REPORT_LANGUAGE] = ctx.language
    return Applied(report=report, created=created)


def _load(ctx: OperationContext, dataset: Dataset, rows: list[dict], bundle: Bundle) -> Loaded:
    """Load one dataset's ``rows``; a failure stays in it and is told."""
    loaded = Loaded(media=bundle.media)
    try:
        dataset.load(ctx, rows, loaded)
    except Exception:
        # Each operation it called rolled its own part back; what committed before stays, and undo has it.
        logger.exception("blueprint: loading %s failed", dataset.key)
        loaded.refuse("", str(SOMETHING_WENT_WRONG))
    return loaded


def _load_status(ctx: OperationContext, data: Mapping[str, list[dict]], app_reports: list[dict],
                 created: Mapping[str, list[str]]) -> str:
    """How a whole load went. An app that never goes on in this business, with nothing of it in the blueprint, lost
    nothing and no retry would change it: the load is not left unfinished by it (hub#694)."""
    rowless = [
        report["id"]
        for report in app_reports
        if report["status"] == INACTIVE and not any(part.key in data for part in datasets_of(report["id"]))
    ]
    never_here = activation.refusals(rowless, ctx=ctx, hook=activation.CAN_ENABLE)
    return _overall([report for report in app_reports if report["id"] not in never_here], created)


def _dataset_report(dataset: Dataset, loaded: Loaded, rows: list[dict], *, discarded: bool = False) -> dict:
    if discarded:
        status = DISCARDED
    elif loaded.created:
        status = PARTIAL if loaded.failed or loaded.problems else APPLIED
    elif loaded.failed or loaded.problems:
        status = FAILED
    elif loaded.already:
        status = ALREADY
    else:
        status = EMPTY
    return {
        "key": dataset.key,
        "label": str(dataset.label),
        "status": status,
        "rows": len(rows),
        "created": len(loaded.created),
        "already": loaded.already,
        "failed": loaded.failed,
        "problems": loaded.problems,
    }


def _app_report(app: str, bundle: Bundle, chosen: set[str] | None, on: frozenset[str], known: set[str],  # noqa: PLR0913, PLR0917
                loads: dict[str, dict], refused: dict[str, str], waiting: set[str]) -> dict:
    report = {"id": app, "label": app_label(app), "status": APPLIED, "reason": "", "datasets": []}
    if chosen is not None and app not in chosen:
        report["status"] = NOT_SELECTED
    elif app not in known:
        report["status"] = UNKNOWN
    elif app not in on:
        report["status"] = WAITING if app in waiting else INACTIVE
        report["reason"] = refused.get(app, "")
    else:
        report["datasets"] = [loads[dataset.key] for dataset in datasets_of(app) if dataset.key in loads]
        report["status"] = _app_status({dataset["status"] for dataset in report["datasets"]} - {EMPTY})
    return report


def _app_status(statuses: set[str]) -> str:
    # An app with nothing of it in the blueprint, or only empty parts, copied nothing: it was not there already.
    if not statuses:
        return EMPTY
    if statuses == {ALREADY}:
        return ALREADY
    if statuses & {FAILED, PARTIAL}:
        return PARTIAL if statuses & {APPLIED, PARTIAL, ALREADY} else FAILED
    if statuses == {DISCARDED}:
        return DISCARDED
    return APPLIED


def _overall(app_reports: list[dict], created: dict[str, list[str]]) -> str:
    statuses = {app["status"] for app in app_reports}
    if not statuses & {FAILED, PARTIAL, INACTIVE, UNKNOWN, WAITING}:
        return COMPLETE
    if created or statuses & {APPLIED, ALREADY, EMPTY, WAITING}:
        return PARTIAL
    return FAILED

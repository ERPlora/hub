"""A load kept (an ``ImportBatch``): how the screens read it, whether it can be retried, and the part of it that
waits for an app being set up.
"""

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from django.utils import translation
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import atomic

from base import activation
from base.blueprint.loading import (
    COMPLETE,
    FAILED,
    INACTIVE,
    REPORT_LANGUAGE,
    SETUP_FAILED,
    SOMETHING_WENT_WRONG,
    WAITING,
    _load_status,
    apply,
    logger,
)
from base.blueprint.seeds import template

BEING_SET_UP = _("It is being set up for this business. Its data will load by itself as soon as it is ready: you can "
                 "leave this screen.")
SETUP_FAILING = _("It could not be set up yet. It keeps trying by itself and its data will load as soon as it works; "
                  "«Retry what is missing» tries again now.")
FILE_BEING_SET_UP = _("It is being set up for this business. Upload the file again in a minute to bring its data.")
STOPPED_TURNED_OFF = _("It was turned off before it was ready, so nothing of it was loaded.")
STOPPED_UNDONE = _("This load was undone before the app was ready, so nothing of it was loaded.")
STOPPED_RETRIED = _("A later load took over what was missing from this one.")
STOPPED_RESET = _("The business was reset before the app was ready, so nothing of it was loaded.")
#: Why a load cannot be loaded again (``retry_state``), each with its code.
RETRY_BLOCKED = {
    "file": ("base.import_from_file", _("This load came from a file uploaded by hand, so it cannot be retried by "
                                        "itself. Upload the file again and choose only what failed.")),
    "version_gone": ("base.template_version_gone", _("The version of the template this load used is no longer in the "
                                                     "catalogue, so it was not retried: another version could load "
                                                     "different data.")),
    "complete": ("base.import_complete", _("Everything of this load went in: there is nothing to retry.")),
    "undone": ("base.import_undone", _("This load was undone, so there is nothing to retry.")),
    "waiting": ("base.import_waiting", _("What is missing is coming by itself as soon as its apps are ready: there is "
                                         "nothing to retry yet.")),
}


def waiting_apps(load: Any) -> list[str]:
    """The apps whose data ``load`` (an ``ImportBatch``) still waits to bring (hub#609)."""
    return [app["id"] for app in load.report.get("apps", []) if app["status"] == WAITING]


def _states_of_waiting(ctx: OperationContext, load: Any) -> dict[str, activation.Activation]:
    """How the apps of the business are, read from their rows, when ``load`` waits for any of them; none otherwise."""
    return activation.states_of(ctx.scope) if waiting_apps(load) else {}


def _state_of(states: dict[str, activation.Activation], app: str) -> str:
    return states.get(app, activation.OFF_ROW).state


def retry_state(ctx: OperationContext, load: Any) -> str:
    """Why ``load`` (an ``ImportBatch``) cannot be loaded again, or ``""`` when what did not go in can be. While an app
    it waits for is being set up there is nothing to retry; once that failed, retrying tries it again."""
    return _retry_state(load, _states_of_waiting(ctx, load))


def _retry_state(load: Any, states: dict[str, activation.Activation]) -> str:
    if load.undone_at is not None:
        return "undone"
    if load.status == COMPLETE:
        return "complete"
    if not load.template_key:
        return "file"
    if any(_state_of(states, app) == activation.CREATING for app in waiting_apps(load)):
        return "waiting"
    seed = template(load.template_key)
    if seed is None or seed.version != load.template_version:
        return "version_gone"
    return ""


def _report_read(ctx: OperationContext, report: dict, states: dict[str, activation.Activation]) -> dict:
    """A load's report as it reads now, in the language of who asks: an app it waits for says how its setup goes."""
    if not states:
        return report

    def read(app: dict) -> dict:
        if app["status"] != WAITING:
            return app
        failing = _state_of(states, app["id"]) == activation.FAILED
        return {
            **app,
            "status": SETUP_FAILED if failing else WAITING,
            "reason": str(SETUP_FAILING if failing else BEING_SET_UP),
        }

    with translation.override(ctx.language):
        return {**report, "apps": [read(app) for app in report["apps"]]}


def describe_load(ctx: OperationContext, load: Any) -> dict:
    """An ``ImportBatch`` as the screens read it."""
    states = _states_of_waiting(ctx, load)
    blocked = _retry_state(load, states)
    rows = sum(len(ids) for ids in load.created_rows.values())
    return {
        "id": load.pk,
        "name": load.name,
        "source": load.source,
        "template_key": load.template_key,
        "status": load.status,
        "created_at": load.created_at,
        "created_by": load.created_by,
        "rows": rows,
        "undone": load.undone_at is not None,
        "undoable": load.undone_at is None and rows > 0,
        "retry": not blocked,
        "retry_blocked": blocked,
        "report": _report_read(ctx, load.report, states),
    }


def _rewrite(ctx: OperationContext, load: Any, data: Mapping[str, list[dict]], changed: Mapping[str, dict],
             created: Mapping[str, list[str]] | None = None) -> None:
    """``load`` (an ``ImportBatch``, its caller saves it) with the reports ``changed`` of its apps and the rows
    ``created`` added to what it created, so its undo removes those too; a load that waits for nothing keeps no
    language."""
    apps = [changed.get(app["id"], app) for app in load.report["apps"]]
    rows = dict(load.created_rows)
    for key, ids in (created or {}).items():
        rows[key] = [*rows.get(key, []), *ids]
    report = {**load.report, "apps": apps, "status": _load_status(ctx, data, apps, rows)}
    if not any(app["status"] == WAITING for app in apps):
        report.pop(REPORT_LANGUAGE, None)
    load.report, load.status, load.created_rows = report, report["status"], rows


def _in_its_language(ctx: OperationContext, load: Any) -> OperationContext:
    """``ctx``, in the language of who loaded ``load``: what is written on it reads as the rest of its report."""
    return replace(ctx, language=load.report.get(REPORT_LANGUAGE) or ctx.language)


def stop_waiting(ctx: OperationContext, load: Any, apps: Iterable[str], reason: Promise) -> None:
    """``load`` stops waiting for ``apps``: they load nothing, and its report says ``reason``. Retrying it can still
    bring them. Its caller saves it."""
    apps = set(apps)
    ctx = _in_its_language(ctx, load)
    seed = template(load.template_key)
    with translation.override(ctx.language):
        changed = {
            app["id"]: {**app, "status": INACTIVE, "reason": str(reason)}
            for app in load.report["apps"]
            if app["id"] in apps and app["status"] == WAITING
        }
    _rewrite(ctx, load, seed.bundle.data if seed else {}, changed)


def finish_waiting(ctx: OperationContext, load: Any, apps: Iterable[str]) -> None:
    """The part of ``load`` that waited for ``apps``, just turned on, loaded and written on it, in the transaction that
    turned them on (hub#609; its caller saves it). If the template changed meanwhile it loads nothing, as a retry would
    not: another version could bring different data. One that breaks leaves the apps on and says so on its report: the
    app is not held back, and retrying the load brings its part."""
    apps = set(apps)
    ctx = _in_its_language(ctx, load)
    seed = template(load.template_key)
    if seed is None or seed.version != load.template_version:
        stop_waiting(ctx, load, apps, RETRY_BLOCKED["version_gone"][1])
        return
    try:
        with atomic():
            applied = apply(ctx, seed.bundle, apps=apps)
    except Exception:
        logger.exception("blueprint: what load %s waited for could not be loaded", load.pk)
        with translation.override(ctx.language):
            broken = {
                app["id"]: {**app, "status": FAILED, "reason": str(SOMETHING_WENT_WRONG)}
                for app in load.report["apps"]
                if app["id"] in apps
            }
        _rewrite(ctx, load, seed.bundle.data, broken)
        return
    reports = {app["id"]: app for app in applied.report["apps"] if app["id"] in apps}
    _rewrite(ctx, load, seed.bundle.data, reports, applied.created)

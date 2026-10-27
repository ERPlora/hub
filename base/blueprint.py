"""Blueprints (PLAN-HUB round 2026-10-21, «Blueprints»): the ``.blueprint.zip``, the catalogue of seeds by vertical and
what travels of each app. Flows BASE-G101–G109 (Settings › Data) and the Home's card (BASE-G131).

A blueprint is a manifest (who made it, for what, its language and country, the apps it turns on) and, per dataset,
the rows that travel. A **dataset** is one kind of thing an app lets travel (inventory's categories, its products,
the tables of the room…): it reads its rows with that app's own list and writes them with that app's own create, so
the app's rules hold for an import too, and never a table is dumped (hub#426). Rows name each other by their natural
key — a product's categories by name, a table's zone by name — never by an id of the business that made the file
(hub#2626). People, PINs and fiscal data have no dataset: they never travel, and a file that brings them has them
dropped on reading (``Bundle.dropped``).

- The file: ``manifest.json`` and ``data/<dataset>.json`` in a zip (:func:`read_zip`, :func:`write_zip`), read with
  limits (5 MB, 50 MB inflated, 200 entries) and refused with a reason the person can read (:class:`BlueprintInvalid`).
- The catalogue: the seeds of ``base/seeds/<vertical>.<language>.json``, one per vertical and language; what a seed
  turns on is its vertical's apps (``base.catalog.template_apps``, PLAN §15.2), what it brings is its own data.
- :func:`apply` loads a blueprint app by app, each part on its own: a row an app refuses fails alone and is told, the
  rest loads, and loading again duplicates nothing (each dataset skips what is already there). Personal data (the
  customers) travels only in a backup, never in a template. Before it, ``base.blueprint.import`` turns on the apps
  the manifest lists that are off (round 2026-10-27: a hub is born with every app off); one it could not turn on (the
  plan's limit, no right to it) loads nothing and its report says why.
- :func:`undo` removes exactly the rows a load created; :func:`reset` every row of the apps chosen; both through the
  apps' own delete (or archive).

No ORM here: every read and write is an operation of its app, called as the person who asked
(``live.operations.get``), so its permission, its transaction and its events are the operation's own.
"""

import base64
import binascii
import csv
import io
import json
import logging
import re
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any

import pydantic
from django.apps import apps as django_apps
from django.utils import translation
from django.utils.functional import Promise
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound, OperationError
from live.meta import module_configs
from live.operations import get

from base.catalog import template_apps
from base.entitlement import blocked_apps
from base.relay import active_apps

logger = logging.getLogger(__name__)

FORMAT = "erplora.blueprint"
FORMAT_VERSION = 1
MANIFEST = "manifest.json"
PURPOSE_BACKUP = "backup"
PURPOSE_TEMPLATE = "template"
PURPOSES = (PURPOSE_BACKUP, PURPOSE_TEMPLATE)
#: The largest file read (what the person uploads), before anything is inflated.
MAX_FILE_BYTES = 5 * 1024 * 1024
#: The most its members may weigh once inflated: a zip bomb stops here, never in memory.
MAX_INFLATED_BYTES = 50 * 1024 * 1024
MAX_ENTRIES = 200
MAX_ROWS = 10_000
#: The problems told per dataset: the first ones say what to fix; the count says how many.
MAX_PROBLEMS = 20
#: A list operation's page (``limit`` ≤ 100, every app's lists).
PAGE = 100
SEEDS_DIR = Path(__file__).resolve().parent / "seeds"
LABEL_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DATA_FILE_RE = re.compile(r"^data/([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\.json$")
#: What a spreadsheet runs as a formula; the customers' export quotes a cell that starts with one (CUSTOMER-F09).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

# Statuses of a dataset and of an app in the report of a load (the screen names each one, hub#1891).
APPLIED, PARTIAL, ALREADY, FAILED, EMPTY, DISCARDED = "applied", "partial", "already", "failed", "empty", "discarded"
INACTIVE, UNKNOWN, NOT_SELECTED = "inactive", "unknown", "not_selected"
# Statuses of an app in a blueprint's summary, before loading it: on here, off and turned on by the load, off and left
# off (only its data names it, or the plan gives no right to it), or not in this hub.
ON, TURNS_ON = "on", "turns_on"
# Statuses of a whole load.
COMPLETE = "complete"

REASONS = {
    "too_big": _("The file is larger than 5 MB, or holds more than a blueprint can."),
    "not_a_blueprint": _("This is not a .blueprint.zip file."),
    "no_manifest": _("The file has no manifest: it was not made by ERPlora."),
    "unreadable": _("The file is damaged or was changed by hand, so it cannot be read."),
    "too_new": _("The file was made by a newer version of ERPlora. Update this one to load it."),
}
SOMETHING_WENT_WRONG = _("Something went wrong loading this part; nothing else was affected.")
NO_NAME = _("A row has no name.")
CATEGORY_MISSING = _("«%(row)s»: the category «%(category)s» is not there, so it was left without it.")
ROW_REFUSED = _("«%(row)s»: %(reason)s")


class BlueprintInvalid(Exception):
    """A file that is no blueprint this hub can read: ``reason`` is its code, ``str()`` the sentence for the person."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:
        return str(REASONS[self.reason])


@dataclass
class Bundle:
    """A blueprint read into memory: its manifest, the rows of each dataset it brings, and what was dropped."""

    manifest: dict
    data: dict[str, list[dict]]
    dropped: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Template:
    """A seed of the catalogue: one vertical in one language (``<vertical>.<language>``)."""

    key: str
    name: str
    description: str
    language: str
    country: str
    vertical: str
    version: str
    bundle: Bundle


@dataclass
class Loaded:
    """What a dataset's load did: the ids it created (for undo), the rows already there, and the ones refused."""

    created: list[str] = field(default_factory=list)
    already: int = 0
    failed: int = 0
    problems: list[str] = field(default_factory=list)

    def refuse(self, row: str, reason: str, *, counted: bool = True) -> None:
        if counted:
            self.failed += 1
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append(str(ROW_REFUSED) % {"row": row, "reason": reason} if row else reason)

    def warn(self, text: str) -> None:
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append(text)


@dataclass(frozen=True)
class Dataset:
    """One kind of thing an app lets travel, through that app's own operations."""

    key: str
    label: Promise
    rows: Callable[[OperationContext], list[dict]]
    ids: Callable[[OperationContext], list[str]]
    count: Callable[[OperationContext], int]
    load: Callable[[OperationContext, list[dict], Loaded], None]
    remove: Callable[[OperationContext, str], None]
    #: Personal data (a person's name, phone, email): it travels in a backup only, never in a template.
    personal: bool = False

    @property
    def app(self) -> str:
        return self.key.split(".", 1)[0]


@dataclass(frozen=True)
class Applied:
    """A load's report (what the screen shows) and the ids it created per dataset (what undo removes)."""

    report: dict
    created: dict[str, list[str]]


# ── The file ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def read_base64(text: str) -> Bundle:
    """A blueprint uploaded in base64 (the upload's JSON body)."""
    if len(text) > (MAX_FILE_BYTES // 3 + 1) * 4:
        raise BlueprintInvalid("too_big")
    try:
        content = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise BlueprintInvalid("not_a_blueprint") from None
    return read_zip(content)


def read_zip(content: bytes) -> Bundle:
    """The blueprint in ``content``, or :class:`BlueprintInvalid` with the reason it cannot be read."""
    if len(content) > MAX_FILE_BYTES:
        raise BlueprintInvalid("too_big")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, OSError):
        raise BlueprintInvalid("not_a_blueprint") from None
    with archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if len(members) > MAX_ENTRIES:
            raise BlueprintInvalid("unreadable")
        if sum(info.file_size for info in members) > MAX_INFLATED_BYTES:
            raise BlueprintInvalid("too_big")
        names = [info.filename for info in members]
        if any(name != MANIFEST and not DATA_FILE_RE.match(name) for name in names):
            raise BlueprintInvalid("unreadable")
        if MANIFEST not in names:
            raise BlueprintInvalid("no_manifest")
        budget = [MAX_INFLATED_BYTES]
        manifest = _manifest(_member_json(archive, MANIFEST, budget))
        data: dict[str, list[dict]] = {}
        dropped = []
        for name in names:
            match = DATA_FILE_RE.match(name)
            if match is None:
                continue
            key = match.group(1)
            rows = _rows(_member_json(archive, name, budget))
            if key in _datasets_by_key():
                data[key] = rows
            else:
                dropped.append(key)
    return Bundle(manifest=manifest, data=_in_order(data), dropped=sorted(dropped))


def write_zip(bundle: Bundle) -> bytes:
    """The ``.blueprint.zip`` of ``bundle``: its manifest and a file per dataset."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(bundle.manifest, ensure_ascii=False, indent=2))
        for key, rows in _in_order(bundle.data).items():
            archive.writestr(f"data/{key}.json", json.dumps(rows, ensure_ascii=False, indent=1))
    return buffer.getvalue()


def file_name(name: str, language: str) -> str:
    """``{name}_{language}.blueprint.zip``, the name made safe for any disk (the old hub's)."""
    return f"{slugify(name) or 'blueprint'}_{slugify(language) or 'xx'}.blueprint.zip"


def manifest(*, name: str, language: str, country: str, purpose: str, created_at: str, vertical: str, apps: list[str],
             version: str = "") -> dict:
    """A manifest of this format."""
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "name": name,
        "language": language,
        "country": country,
        "purpose": purpose,
        "created_at": created_at,
        "vertical": vertical,
        "version": version,
        "apps": list(apps),
    }


def _member_json(archive: zipfile.ZipFile, name: str, budget: list[int]) -> Any:
    """A member parsed as JSON, read in chunks against what is left of the inflated budget."""
    chunks = []
    with archive.open(name) as member:
        while chunk := member.read(65536):
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise BlueprintInvalid("too_big")
            chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise BlueprintInvalid("unreadable") from None


def _manifest(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise BlueprintInvalid("unreadable")
    if raw.get("format") != FORMAT:
        raise BlueprintInvalid("not_a_blueprint")
    version = raw.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise BlueprintInvalid("unreadable")
    if version > FORMAT_VERSION:
        raise BlueprintInvalid("too_new")
    texts = {"name": 120, "language": 8, "country": 2, "created_at": 40, "vertical": 63, "version": 32}
    values = {key: raw.get(key, "") for key in texts}
    if any(not isinstance(value, str) or len(value) > texts[key] for key, value in values.items()):
        raise BlueprintInvalid("unreadable")
    if not values["name"].strip() or raw.get("purpose") not in PURPOSES:
        raise BlueprintInvalid("unreadable")
    apps = raw.get("apps", [])
    if not isinstance(apps, list) or len(apps) > 200 or any(not isinstance(app, str) or not LABEL_RE.match(app) for app in apps):
        raise BlueprintInvalid("unreadable")
    return manifest(purpose=raw["purpose"], apps=list(dict.fromkeys(apps)), **values)


def _rows(raw: Any) -> list[dict]:
    """A dataset's rows: a list of objects, at most ``MAX_ROWS``."""
    if not isinstance(raw, list) or len(raw) > MAX_ROWS or any(not isinstance(row, dict) for row in raw):
        raise BlueprintInvalid("unreadable")
    return raw


def _in_order(data: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """The datasets in their load order (a category before the products that name it)."""
    return {dataset.key: data[dataset.key] for dataset in DATASETS if dataset.key in data}


# ── The catalogue: the seeds by vertical ─────────────────────────────────────────────────────────────────────────────


@cache
def _seeds() -> tuple[Template, ...]:
    templates = []
    for path in sorted(SEEDS_DIR.glob("*.json")):
        seed = json.loads(path.read_text(encoding="utf-8"))
        key = path.stem
        if key != f"{seed['vertical']}.{seed['language']}":
            raise ValueError(f"The seed {path.name} must be named <vertical>.<language>.json.")
        bundle = Bundle(
            manifest=manifest(
                name=seed["name"],
                language=seed["language"],
                country=seed["country"],
                purpose=PURPOSE_TEMPLATE,
                created_at="",
                vertical=seed["vertical"],
                version=seed["version"],
                apps=template_apps(seed["vertical"]),
            ),
            data=_in_order({name: _rows(rows) for name, rows in seed["data"].items()}),
        )
        templates.append(
            Template(
                key=key,
                name=seed["name"],
                description=seed["description"],
                language=seed["language"],
                country=seed["country"],
                vertical=seed["vertical"],
                version=seed["version"],
                bundle=bundle,
            )
        )
    return tuple(templates)


def catalog() -> list[Template]:
    """Every seed of the catalogue, by key."""
    return list(_seeds())


def template(key: str) -> Template | None:
    """The seed ``key`` (``<vertical>.<language>``), or ``None``."""
    return next((seed for seed in _seeds() if seed.key == key), None)


# ── What the screens read: a template, a blueprint's summary, a load ─────────────────────────────────────────────────

ONE_SOURCE = _("Choose a template or a file, one of them.")
TEMPLATE_NOT_FOUND = _("This template is no longer in the catalogue.")
#: Why a load cannot be loaded again (``retry_state``), each with its code.
RETRY_BLOCKED = {
    "file": ("base.import_from_file", _("This load came from a file uploaded by hand, so it cannot be retried by "
                                        "itself. Upload the file again and choose only what failed.")),
    "version_gone": ("base.template_version_gone", _("The version of the template this load used is no longer in the "
                                                     "catalogue, so it was not retried: another version could load "
                                                     "different data.")),
    "complete": ("base.import_complete", _("Everything of this load went in: there is nothing to retry.")),
    "undone": ("base.import_undone", _("This load was undone, so there is nothing to retry.")),
}


def open_source(template_key: str, file_base64: str) -> tuple[Bundle, Template | None]:
    """The blueprint of a template of the catalogue or of an uploaded file, exactly one of them."""
    if bool(template_key) == bool(file_base64):
        raise InvalidPayload(str(ONE_SOURCE), code="base.blueprint_source")
    if template_key:
        seed = template(template_key)
        if seed is None:
            raise NotFound(str(TEMPLATE_NOT_FOUND), code="base.template_not_found")
        return seed.bundle, seed
    try:
        return read_base64(file_base64), None
    except BlueprintInvalid as exc:
        raise InvalidPayload(str(exc), code="base.blueprint_invalid", fields={"file_base64": str(exc)}) from None


def contents(bundle: Bundle) -> list[dict]:
    """What a blueprint brings, by dataset: its name and how many rows."""
    return [{"key": key, "label": str(dataset(key).label), "rows": len(rows)} for key, rows in bundle.data.items()]


def template_out(seed: Template) -> dict:
    return {
        "key": seed.key,
        "name": seed.name,
        "description": seed.description,
        "language": seed.language,
        "country": seed.country,
        "vertical": seed.vertical,
        "version": seed.version,
        "apps": [{"id": app, "label": app_label(app)} for app in seed.bundle.manifest["apps"]],
        "contents": contents(seed.bundle),
    }


def summary(ctx: OperationContext, bundle: Bundle, *, seed: Template | None) -> dict:
    """What a blueprint brings and what of it would load here (BASE-G105), writing nothing."""
    on = active_apps(ctx.scope)
    blocked = blocked_apps(ctx.scope)
    known = {config.label for config in module_configs()}
    manifest_ = bundle.manifest
    listed = set(manifest_["apps"])
    backup = manifest_["purpose"] == PURPOSE_BACKUP
    apps = []
    for app in _apps_of(bundle):
        if app not in known:
            status = UNKNOWN
        elif app in on:
            status = ON
        elif app in listed and app not in blocked:
            status = TURNS_ON
        else:
            status = INACTIVE
        parts = [
            {
                "key": part.key,
                "label": str(part.label),
                "rows": len(bundle.data[part.key]),
                "personal": part.personal,
                "travels": backup or not part.personal,
            }
            for part in datasets_of(app)
            if part.key in bundle.data
        ]
        apps.append({"id": app, "label": app_label(app), "status": status, "datasets": parts})
    return {
        "name": manifest_["name"],
        "language": manifest_["language"],
        "country": manifest_["country"],
        "purpose": manifest_["purpose"],
        "created_at": manifest_["created_at"],
        "version": seed.version if seed else manifest_["version"],
        "source": "catalog" if seed else "file",
        "apps": apps,
        "dropped": list(bundle.dropped),
    }


def _apps_of(bundle: Bundle) -> list[str]:
    """The apps of a blueprint: the ones its manifest turns on, then any its data names besides."""
    listed = list(bundle.manifest["apps"])
    listed += [key.split(".", 1)[0] for key in bundle.data if key.split(".", 1)[0] not in listed]
    return list(dict.fromkeys(listed))


def retry_state(load: Any) -> str:
    """Why ``load`` (an ``ImportBatch``) cannot be loaded again, or ``""`` when what did not go in can be."""
    if load.undone_at is not None:
        return "undone"
    if load.status == COMPLETE:
        return "complete"
    if not load.template_key:
        return "file"
    seed = template(load.template_key)
    if seed is None or seed.version != load.template_version:
        return "version_gone"
    return ""


def describe_load(load: Any) -> dict:
    """An ``ImportBatch`` as the screens read it."""
    blocked = retry_state(load)
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
        "report": load.report,
    }


# ── Loading ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def apply(ctx: OperationContext, bundle: Bundle, *, apps: set[str] | None,
          refused: dict[str, str] | None = None) -> Applied:
    """Load ``bundle`` app by app (only ``apps`` if given), each part on its own, and say what happened to each.

    An app this hub does not have, or does not have on, loads nothing and is told, with why it is off when it could
    not be turned on (``refused``: its reason by app); personal data loads only from a backup. Every dataset's failure
    stays in it: what it created before failing is kept and counted for undo.
    """
    with translation.override(ctx.language):
        on = active_apps(ctx.scope)
        known = {config.label for config in module_configs()}
        loads: dict[str, dict] = {}
        created: dict[str, list[str]] = {}
        for dataset in DATASETS:
            rows = bundle.data.get(dataset.key)
            if rows is None or (apps is not None and dataset.app not in apps) or dataset.app not in on:
                continue
            if dataset.personal and bundle.manifest["purpose"] != PURPOSE_BACKUP:
                loads[dataset.key] = _dataset_report(dataset, Loaded(), rows, discarded=True)
                continue
            loaded = Loaded()
            try:
                dataset.load(ctx, rows, loaded)
            except Exception:
                # Each operation it called rolled its own part back; what committed before stays, and undo has it.
                logger.exception("blueprint: loading %s failed", dataset.key)
                loaded.refuse("", str(SOMETHING_WENT_WRONG))
            if loaded.created:
                created[dataset.key] = loaded.created
            loads[dataset.key] = _dataset_report(dataset, loaded, rows)
        app_reports = [_app_report(app, bundle, apps, on, known, loads, refused or {}) for app in _apps_of(bundle)]
        report = {"status": _overall(app_reports, created), "apps": app_reports, "dropped": list(bundle.dropped)}
    return Applied(report=report, created=created)


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


def _app_report(app: str, bundle: Bundle, chosen: set[str] | None, on: frozenset[str], known: set[str],
                loads: dict[str, dict], refused: dict[str, str]) -> dict:
    report = {"id": app, "label": app_label(app), "status": APPLIED, "reason": "", "datasets": []}
    if chosen is not None and app not in chosen:
        report["status"] = NOT_SELECTED
    elif app not in known:
        report["status"] = UNKNOWN
    elif app not in on:
        report["status"] = INACTIVE
        report["reason"] = refused.get(app, "")
    else:
        report["datasets"] = [loads[dataset.key] for dataset in datasets_of(app) if dataset.key in loads]
        report["status"] = _app_status({dataset["status"] for dataset in report["datasets"]} - {EMPTY})
    return report


def _app_status(statuses: set[str]) -> str:
    if not statuses or statuses == {ALREADY}:
        return ALREADY
    if statuses & {FAILED, PARTIAL}:
        return PARTIAL if statuses & {APPLIED, PARTIAL, ALREADY} else FAILED
    if statuses == {DISCARDED}:
        return DISCARDED
    return APPLIED


def _overall(app_reports: list[dict], created: dict[str, list[str]]) -> str:
    statuses = {app["status"] for app in app_reports}
    if not statuses & {FAILED, PARTIAL, INACTIVE, UNKNOWN}:
        return COMPLETE
    if created or statuses & {APPLIED, ALREADY}:
        return PARTIAL
    return FAILED


def app_label(app: str) -> str:
    """The app's name as the person reads it (hub#488), or its id for an app this hub does not have."""
    try:
        return str(django_apps.get_app_config(app).verbose_name)
    except LookupError:
        return app


# ── Exporting, counting, undoing and resetting ───────────────────────────────────────────────────────────────────────


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


def undo(ctx: OperationContext, created: dict[str, list[str]]) -> dict:
    """Remove exactly the rows of ``created`` (a load's), last dataset first; one already gone counts as gone."""
    with translation.override(ctx.language):
        removals = {}
        for dataset in reversed(DATASETS):
            ids = created.get(dataset.key)
            if ids:
                _remove(ctx, dataset, ids, removals.setdefault(dataset.app, _removal(dataset.app)))
        return {"apps": list(removals.values())}


def reset_plan(ctx: OperationContext) -> list[dict]:
    """The apps on that have rows, each with how many it would lose and of what."""
    with translation.override(ctx.language):
        on = active_apps(ctx.scope)
        plan = []
        for app in dict.fromkeys(dataset.app for dataset in DATASETS):
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
        for dataset in reversed(DATASETS):
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
                removal["problems"].append(f"{dataset.label}: {_reason(exc)}")
        else:
            removal["removed"] += 1


# ── Calling the apps' operations ─────────────────────────────────────────────────────────────────────────────────────


def _call(ctx: OperationContext, operation: str, /, **data: Any) -> Any:
    op = get(operation)
    return op(ctx, op.input(**data))


def _pages(ctx: OperationContext, operation: str, /, **params: Any) -> Iterator[Any]:
    """Every row of the list ``operation``, page by page."""
    offset = 0
    while True:
        page = _call(ctx, operation, limit=PAGE, offset=offset, **params)
        yield from page.rows
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


def _total(ctx: OperationContext, operation: str, /, **params: Any) -> int:
    return _call(ctx, operation, limit=1, offset=0, **params).total


def _reason(exc: Exception) -> str:
    """What an app said when it refused a row, in one line."""
    if isinstance(exc, pydantic.ValidationError):
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error.get("loc", ()))
        return f"{where}: {error.get('msg', '')}" if where else str(error.get("msg", ""))
    if isinstance(exc, OperationError):
        detail = next(iter((exc.fields or {}).values()), "")
        return f"{exc.message} {detail}".strip() if detail and detail not in exc.message else exc.message
    return str(exc)


def _text(row: dict, key: str) -> str:
    value = row.get(key, "")
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value))


def _key(text: str) -> str:
    return text.strip().casefold()


def _money(cents: Any) -> str:
    """Cents as a price cell the import reads (``8.50``)."""
    if isinstance(cents, bool) or not isinstance(cents, int):
        return str(cents)
    return f"{Decimal(cents) / 100:.2f}"


def _quantity(value: Any, *, blank_zero: bool = False) -> str:
    """A quantity as text, exact and without trailing zeros (``24``, ``0.5``); zero left blank if ``blank_zero``."""
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    if blank_zero and not number:
        return ""
    text = format(number.normalize(), "f")
    return "0" if text in {"-0", ""} else text


def _created(loaded: Loaded, result: Any) -> str:
    pk = str(result.id)
    loaded.created.append(pk)
    return pk


def _create_each(ctx: OperationContext, rows: list[dict], loaded: Loaded, *, name: str, key: Callable[[dict], str],
                 existing: set[str], build: Callable[[dict], dict], label: Callable[[dict], str]) -> None:
    """Create each row by ``name`` unless its natural ``key`` is already there; a refused row fails alone."""
    for row in rows:
        natural = key(row)
        if not natural:
            loaded.refuse("", str(NO_NAME))
            continue
        if natural in existing:
            loaded.already += 1
            continue
        try:
            _created(loaded, _call(ctx, name, **build(row)))
        except (OperationError, pydantic.ValidationError) as exc:
            loaded.refuse(label(row), _reason(exc))
            continue
        existing.add(natural)


# ── The datasets ─────────────────────────────────────────────────────────────────────────────────────────────────────

# inventory: categories and products (INVENTORY-F12)


def _inventory_category_rows(ctx: OperationContext) -> list[dict]:
    return [
        {
            "name": row.name,
            "tax_category_key": row.tax_category_key or "",
            "description": row.description,
            "icon": row.icon,
            "color": row.color,
            "order": row.order,
        }
        for row in _pages(ctx, "inventory.category.list")
    ]


def _inventory_category_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_key(row.name) for row in _pages(ctx, "inventory.category.list")}

    def build(row: dict) -> dict:
        fields = {"name": _text(row, "name"), "tax_category_key": _text(row, "tax_category_key") or None}
        fields |= {name: row[name] for name in ("description", "icon", "color", "order") if row.get(name) not in (None, "")}
        return fields

    _create_each(ctx, rows, loaded, name="inventory.category.create", key=lambda row: _key(_text(row, "name")),
                 existing=existing, build=build, label=lambda row: _text(row, "name"))


def _inventory_product_rows(ctx: OperationContext) -> list[dict]:
    names = {row.id: row.name for row in _pages(ctx, "inventory.category.list")}
    return [
        {
            "name": row.name,
            "sku": row.sku,
            "price": row.price,
            "cost": row.cost,
            "stock": _quantity(row.stock, blank_zero=True),
            "low_stock_threshold": _quantity(row.low_stock_threshold),
            "unit": row.unit,
            "ean13": row.ean13 or "",
            "description": row.description,
            "tax_category_key": row.tax_category_key or "",
            "categories": sorted(names[pk] for pk in row.category_ids if pk in names),
            "track_stock": row.track_stock,
            "is_active": row.is_active,
        }
        for row in _pages(ctx, "inventory.product.list")
    ]


def _inventory_product_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    by_sku: dict[str, dict] = {}
    for start in range(0, len(rows), PAGE):
        chunk = rows[start : start + PAGE]
        cells = [
            {
                "line": start + index + 1,
                "name": _text(row, "name"),
                "sku": _text(row, "sku"),
                "price": _money(row.get("price", 0)),
                "cost": _money(row.get("cost", 0)),
                "stock": _text(row, "stock"),
                "low_stock_threshold": _text(row, "low_stock_threshold"),
                "ean13": _text(row, "ean13"),
                "description": _text(row, "description"),
                "unit": _text(row, "unit"),
                "tax_category_key": _text(row, "tax_category_key"),
            }
            for index, row in enumerate(chunk)
        ]
        try:
            report = _call(ctx, "inventory.product.bulk_create", rows=cells)
        except (OperationError, pydantic.ValidationError) as exc:
            for row in chunk:
                loaded.refuse(_text(row, "name") or _text(row, "sku"), _reason(exc))
            continue
        for outcome in report.rows:
            row = chunk[outcome.line - start - 1]
            if outcome.status == "created":
                by_sku[_text(row, "sku")] = {"id": _created(loaded, outcome), "row": row}
            elif outcome.status == "skipped":
                loaded.already += 1
            else:
                # Named as the person knows it (hub#1891): its name, its code only without one.
                loaded.refuse(_text(row, "name") or outcome.key or _text(row, "sku"), outcome.reason)
    if not by_sku:
        return
    categories = {_key(row.name): row.id for row in _pages(ctx, "inventory.category.list")}
    for sku, made in by_sku.items():
        row, patch = made["row"], {}
        names = row.get("categories") or []
        names = [name for name in names if isinstance(name, str) and name.strip()] if isinstance(names, list) else []
        ids = []
        for name in names:
            if _key(name) in categories:
                ids.append(categories[_key(name)])
            else:
                loaded.warn(str(CATEGORY_MISSING) % {"row": sku, "category": name})
        if ids:
            patch["category_ids"] = ids
        if isinstance(row.get("track_stock"), bool):
            patch["track_stock"] = row["track_stock"]
        if row.get("is_active") is False:
            patch["is_active"] = False
        if not patch:
            continue
        try:
            _call(ctx, "inventory.product.update", id=made["id"], **patch)
        except (OperationError, pydantic.ValidationError) as exc:
            loaded.warn(str(ROW_REFUSED) % {"row": sku, "reason": _reason(exc)})


# service: categories and services


def _service_category_rows(ctx: OperationContext) -> list[dict]:
    return [
        {
            "name": row.name,
            "description": row.description,
            "parent": row.parent_name or "",
            "icon": row.icon,
            "color": row.color,
            "sort_order": row.sort_order,
        }
        for row in _pages(ctx, "service.category.list")
    ]


def _service_category_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_key(row.name) for row in _pages(ctx, "service.category.list")}
    # A parent before its children: the ones without a parent first.
    ordered = sorted(rows, key=lambda row: bool(_text(row, "parent")))

    def build(row: dict) -> dict:
        fields = {"name": _text(row, "name"), "parent": _text(row, "parent") or None}
        fields |= {name: row[name] for name in ("description", "icon", "color", "sort_order") if row.get(name) not in (None, "")}
        return fields

    _create_each(ctx, ordered, loaded, name="service.category.create", key=lambda row: _key(_text(row, "name")),
                 existing=existing, build=build, label=lambda row: _text(row, "name"))


SERVICE_FIELDS = (
    "tax_category_key", "pricing_type", "price", "min_price", "max_price", "cost", "duration_minutes", "buffer_before",
    "buffer_after", "max_capacity", "description", "short_description", "is_bookable", "requires_confirmation",
    "allow_online_booking", "sort_order", "is_featured", "sku", "barcode", "notes",
)  # fmt: skip


def _service_rows(ctx: OperationContext) -> list[dict]:
    return [
        {"name": row.name, "category": row.category_name or "", **{name: getattr(row, name) for name in SERVICE_FIELDS}}
        for row in _pages(ctx, "service.service.list")
    ]


def _service_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_key(row.name) for row in _pages(ctx, "service.service.list")}

    def build(row: dict) -> dict:
        fields = {name: row[name] for name in SERVICE_FIELDS if name in row}
        if fields.get("tax_category_key") == "":
            fields["tax_category_key"] = None
        return {"name": _text(row, "name"), "category": _text(row, "category") or None, **fields}

    _create_each(ctx, rows, loaded, name="service.service.create", key=lambda row: _key(_text(row, "name")),
                 existing=existing, build=build, label=lambda row: _text(row, "name"))


# table: zones and tables


def _zone_rows(ctx: OperationContext) -> list[dict]:
    return [
        {"name": row.name, "description": row.description, "color": row.color, "sort_order": row.sort_order}
        for row in _pages(ctx, "table.zone.list")
    ]


def _zone_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_key(row.name) for row in _pages(ctx, "table.zone.list")}

    def build(row: dict) -> dict:
        fields = {"name": _text(row, "name")}
        return fields | {name: row[name] for name in ("description", "color", "sort_order") if row.get(name) not in (None, "")}

    _create_each(ctx, rows, loaded, name="table.zone.create", key=lambda row: _key(_text(row, "name")),
                 existing=existing, build=build, label=lambda row: _text(row, "name"))


def _table_key(zone: str, number: str) -> str:
    return f"{_key(zone)}\x00{_key(number)}" if number.strip() else ""


def _table_rows(ctx: OperationContext) -> list[dict]:
    return [
        {"number": row.number, "name": row.name, "capacity": row.capacity, "shape": row.shape, "zone": row.zone_name or ""}
        for row in _pages(ctx, "table.table.list")
    ]


def _table_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_table_key(row.zone_name or "", row.number) for row in _pages(ctx, "table.table.list")}

    def build(row: dict) -> dict:
        fields = {"number": _text(row, "number"), "zone": _text(row, "zone") or None}
        return fields | {name: row[name] for name in ("name", "capacity", "shape") if row.get(name) not in (None, "")}

    _create_each(ctx, rows, loaded, name="table.table.create",
                 key=lambda row: _table_key(_text(row, "zone"), _text(row, "number")), existing=existing, build=build,
                 label=lambda row: " ".join(part for part in (_text(row, "zone"), _text(row, "number")) if part))


# customer: the customers (personal data: a backup only)

CUSTOMER_FIELDS = (
    "name", "email", "phone", "tax_id", "company_name", "address", "city", "postal_code", "country", "lifecycle_stage",
    "notes", "source",
)  # fmt: skip
#: Rows per call of ``customer.customer.import`` (its ceiling).
CUSTOMER_BATCH = 50


def _uncell(text: str) -> str:
    """A cell of the customers' CSV as it was typed: the quote the export puts before a formula's sign goes."""
    return text[1:] if text[:1] == "'" and text[1:2] in FORMULA_STARTS and len(text) > 1 else text


def _customer_rows(ctx: OperationContext) -> list[dict]:
    exported = _call(ctx, "customer.customer.export")
    return [
        {name: _uncell(line.get(name) or "") for name in CUSTOMER_FIELDS}
        for line in csv.DictReader(io.StringIO(exported.csv))
    ]


def _customer_identity(name: str, phone: str, email: str) -> str:
    return f"{_key(name)}\x00{phone.strip()}\x00{_key(email)}"


def _customer_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_customer_identity(row.name, row.phone, row.email) for row in _pages(ctx, "customer.customer.list")}
    fresh = []
    for row in rows:
        values = {name: _text(row, name) for name in CUSTOMER_FIELDS}
        if not values["name"]:
            loaded.refuse("", str(NO_NAME))
        elif _customer_identity(values["name"], values["phone"], values["email"]) in existing:
            loaded.already += 1
        else:
            fresh.append(values)
    for start in range(0, len(fresh), CUSTOMER_BATCH):
        chunk = fresh[start : start + CUSTOMER_BATCH]
        try:
            result = _call(ctx, "customer.customer.import", rows=chunk)
        except (OperationError, pydantic.ValidationError) as exc:
            for values in chunk:
                loaded.refuse(values["name"], _reason(exc))
            continue
        for outcome in result.rows:
            if outcome.id is not None:
                loaded.created.append(str(outcome.id))
            else:
                loaded.refuse(chunk[outcome.index]["name"], next(iter(outcome.errors.values()), ""))


def _ids(name: str, **params: Any) -> Callable[[OperationContext], list[str]]:
    return lambda ctx: [str(row.id) for row in _pages(ctx, name, **params)]


def _count(name: str) -> Callable[[OperationContext], int]:
    return lambda ctx: _total(ctx, name)


def _remover(name: str) -> Callable[[OperationContext, str], None]:
    return lambda ctx, pk: _call(ctx, name, id=pk)


#: Every dataset, in load order: what a row names is loaded before it (a category before its products).
DATASETS: tuple[Dataset, ...] = (
    Dataset(
        key="inventory.category",
        label=pgettext_lazy("blueprint dataset", "Product categories"),
        rows=_inventory_category_rows,
        ids=_ids("inventory.category.list"),
        count=_count("inventory.category.list"),
        load=_inventory_category_load,
        remove=_remover("inventory.category.delete"),
    ),
    Dataset(
        key="inventory.product",
        label=pgettext_lazy("blueprint dataset", "Products"),
        rows=_inventory_product_rows,
        ids=_ids("inventory.product.list"),
        count=_count("inventory.product.list"),
        load=_inventory_product_load,
        remove=_remover("inventory.product.delete"),
    ),
    Dataset(
        key="service.category",
        label=pgettext_lazy("blueprint dataset", "Service categories"),
        rows=_service_category_rows,
        ids=_ids("service.category.list"),
        count=_count("service.category.list"),
        load=_service_category_load,
        remove=_remover("service.category.delete"),
    ),
    Dataset(
        key="service.service",
        label=pgettext_lazy("blueprint dataset", "Services"),
        rows=_service_rows,
        ids=_ids("service.service.list"),
        count=_count("service.service.list"),
        load=_service_load,
        remove=_remover("service.service.archive"),
    ),
    Dataset(
        key="table.zone",
        label=pgettext_lazy("blueprint dataset", "Zones"),
        rows=_zone_rows,
        ids=_ids("table.zone.list"),
        count=_count("table.zone.list"),
        load=_zone_load,
        remove=_remover("table.zone.delete"),
    ),
    Dataset(
        key="table.table",
        label=pgettext_lazy("blueprint dataset", "Tables"),
        rows=_table_rows,
        ids=_ids("table.table.list"),
        count=_count("table.table.list"),
        load=_table_load,
        remove=_remover("table.table.delete"),
    ),
    Dataset(
        key="customer.customer",
        label=pgettext_lazy("blueprint dataset", "Customers"),
        rows=_customer_rows,
        ids=_ids("customer.customer.list"),
        count=_count("customer.customer.list"),
        load=_customer_load,
        remove=_remover("customer.customer.delete"),
        personal=True,
    ),
)


@cache
def _datasets_by_key() -> dict[str, Dataset]:
    return {dataset.key: dataset for dataset in DATASETS}


def dataset(key: str) -> Dataset:
    """The dataset ``key`` (``KeyError`` for one that does not exist)."""
    return _datasets_by_key()[key]


def datasets_of(app: str) -> list[Dataset]:
    """The datasets of ``app``, in load order."""
    return [dataset for dataset in DATASETS if dataset.app == app]


def no_rows_yet(ctx: OperationContext) -> bool:
    """Nothing a template brings is in the business yet: no category, product, service, zone or table."""
    return not any(count for key, count in counts(ctx).items() if not dataset(key).personal)

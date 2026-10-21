"""The factory recipes the apps bring (WORKBOOK FLOW-F33 to F36; the old Hub's ``flows/templates.rs``).

An app declares its ready-made automations as data in its own ``recipes.py`` (``RECIPES``, a list of
dicts; it imports nothing of this app): an ``id`` unique in the app, its ``name``, ``summary`` and
``description`` (lazy translations), its ``trigger`` and ``steps`` as an automation's document writes them
(texts in them lazy too) and its ``grants``: ``{operation: the sentence that says why}``. This module
reads them from the active apps and offers the ones this business can run; the rest are set aside with
their reason (``SetAside``) and never break the others:

- ``flow.recipe_needs_apps``: it names an event or an operation of an app this business does not have;
- ``flow.recipe_invalid``: it does not read as an automation, it repeats an id, or it asks for other
  permissions than the ones its steps use — never more (the old Hub's «exactly its permissions») and
  never fewer (it would fail at its first run) —, or one that needs a person in front.

Its **fingerprint** (``digest``) is what it does: its document built in every language and its
permissions; never the sentences that explain it. An automation keeps the one it was built from: a
different one today is «New version». Its **repair** (``missing_clauses``): an automation built from an
older version whose «Only when…» lacks a clause today's recipe has started in more cases than its app
meant; the repair adds just those clauses.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pydantic
from django.conf import settings
from django.utils import translation
from django.utils.functional import Promise
from django.utils.module_loading import module_has_submodule
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound
from live.meta import LiveAppConfig

from apps.flow import document, queries
from apps.flow.models import Flow
from apps.flow.schemas import CreateIn

logger = logging.getLogger(__name__)

#: An app's recipe id: what follows ``<app>/`` in an automation's ``recipe``.
RECIPE_ID = re.compile(r"^[a-z][a-z0-9_]{0,47}$")

NEEDS_APPS = "flow.recipe_needs_apps"
INVALID = "flow.recipe_invalid"
NOT_FOUND = "flow.recipe_not_found"

RECIPE_NOT_FOUND = _("No app of this business brings that automation.")
NEEDS_APPS_MESSAGE = _("It needs apps this business does not have: %(apps)s.")
NOT_A_RECIPE = _("It does not read as an automation: %(problem)s.")
REPEATED = _("Its app brings another automation with the same id.")
ASKS_MORE = _("It asks for permissions its steps do not use: %(names)s.")
ASKS_LESS = _("Its steps use permissions it does not ask for: %(names)s.")


@dataclass(frozen=True)
class Recipe:
    """A recipe this business can offer: the app that brings it and what that app declared."""

    app: LiveAppConfig
    declaration: dict

    @property
    def id(self) -> str:
        return self.declaration["id"]

    @property
    def ref(self) -> str:
        return f"{self.app.label}/{self.id}"


@dataclass(frozen=True)
class SetAside:
    """A recipe this business cannot offer, and why: its ``code``, a ``message`` and the ``apps`` it lacks."""

    app: LiveAppConfig
    declaration: dict
    code: str
    message: str
    apps: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        return f"{self.app.label}/{self.declaration.get('id', '')}"


def declarations() -> list[tuple[LiveAppConfig, dict]]:
    """Every recipe the active apps declare in their ``recipes.py``, in the order of the apps and of each list."""
    found: list[tuple[LiveAppConfig, dict]] = []
    for label, config in sorted(queries.active_apps().items()):
        if not module_has_submodule(config.module, "recipes"):
            continue
        for declared in getattr(import_module(f"{config.name}.recipes"), "RECIPES", []):
            found.append((config, declared))
    return found


def _words(value: Any) -> Any:
    """``value`` with its lazy translations written in the active language."""
    if isinstance(value, Promise):
        return str(value)
    if isinstance(value, dict):
        return {key: _words(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_words(item) for item in value]
    return value


def build(recipe: Recipe, language: str) -> dict[str, Any]:
    """Its document in ``language``: ``{name, trigger, steps}``, ready for ``flow.flow.create``."""
    declared = recipe.declaration
    with translation.override(language):
        return _words({"name": declared["name"], "trigger": declared["trigger"], "steps": declared["steps"]})


def grants(recipe: Recipe) -> list[str]:
    """The permissions it asks for, in its own order: exactly what its steps use."""
    return list(recipe.declaration["grants"])


def reasons(recipe: Recipe, language: str) -> dict[str, str]:
    """``{permission: the sentence its app wrote}`` in ``language``."""
    with translation.override(language):
        return {name: str(reason) for name, reason in recipe.declaration["grants"].items()}


def words(recipe: Recipe | SetAside, language: str) -> dict[str, str]:
    """Its ``name``, ``summary`` and ``description`` in ``language`` ('' when it does not say)."""
    with translation.override(language):
        return {key: str(recipe.declaration.get(key, "")) for key in ("name", "summary", "description")}


def digest(recipe: Recipe) -> str:
    """Its fingerprint: a sha256 of its document in every language and of its permissions."""
    canonical = {
        "documents": {code: build(recipe, code) for code, _name in settings.LANGUAGES},
        "grants": grants(recipe),
    }
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def _problem(config: LiveAppConfig, declared: Any) -> tuple[str, str, tuple[str, ...]] | None:
    """``(code, message, apps it lacks)`` of why this business cannot offer ``declared``; ``None`` when it can."""
    if not isinstance(declared, dict) or not RECIPE_ID.fullmatch(str(declared.get("id", ""))):
        return INVALID, str(NOT_A_RECIPE) % {"problem": "id"}, ()
    missing_keys = [key for key in ("name", "summary", "trigger", "steps", "grants") if key not in declared]
    if missing_keys or not isinstance(declared["grants"], dict):
        return INVALID, str(NOT_A_RECIPE) % {"problem": ", ".join(missing_keys) or "grants"}, ()
    built = build(Recipe(config, declared), "en")
    try:
        parsed = CreateIn.model_validate(built)
    except pydantic.ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        return INVALID, str(NOT_A_RECIPE) % {"problem": f"{where}: {first['msg']}"}, ()
    active = queries.active_apps()
    named = [parsed.trigger.event] if parsed.trigger.kind == "event" else []
    named += [step.operation for step in parsed.steps if step.kind in ("command", "query")]
    lacking = tuple(sorted({name.split(".", 1)[0] for name in named} - set(active)))
    if lacking:
        return NEEDS_APPS, str(NEEDS_APPS_MESSAGE) % {"apps": ", ".join(lacking)}, lacking
    problems, _code = queries.catalog_problems(parsed.trigger, parsed.steps)
    if problems:
        return INVALID, next(iter(problems.values())), ()
    needed = document.required_grants(built["steps"])
    asked = list(declared["grants"])
    more = [name for name in asked if name not in needed]
    if more:
        return INVALID, str(ASKS_MORE) % {"names": ", ".join(f"«{name}»" for name in more)}, ()
    less = [name for name in needed if name not in asked]
    if less:
        return INVALID, str(ASKS_LESS) % {"names": ", ".join(f"«{name}»" for name in less)}, ()
    return None


def shelf() -> tuple[list[Recipe], list[SetAside]]:
    """What the active apps bring: the recipes this business can offer and the ones it sets aside."""
    offered: list[Recipe] = []
    set_aside: list[SetAside] = []
    seen: set[str] = set()
    for config, declared in declarations():
        problem = _problem(config, declared)
        ref = f"{config.label}/{declared.get('id', '') if isinstance(declared, dict) else ''}"
        if problem is None and ref in seen:
            problem = (INVALID, str(REPEATED), ())
        if problem is not None:
            code, message, apps = problem
            logger.warning("flow recipe %s set aside: %s (%s)", ref, code, message)
            set_aside.append(SetAside(config, declared if isinstance(declared, dict) else {}, code, message, apps))
            continue
        seen.add(ref)
        offered.append(Recipe(config, declared))
    return offered, set_aside


def find(ref: str) -> Recipe:
    """The recipe ``<app>/<id>`` this business offers. ``NotFound`` when no active app brings it; a
    ``Conflict`` with its own code when it is set aside."""
    offered, set_aside = shelf()
    for recipe in offered:
        if recipe.ref == ref:
            return recipe
    for item in set_aside:
        if item.ref == ref:
            raise Conflict(item.message, code=item.code)
    raise NotFound(str(RECIPE_NOT_FOUND), code=NOT_FOUND)


def missing_clauses(recipe: Recipe, flow: Flow) -> dict[str, dict[str, Any]]:
    """The «Only when…» clauses today's recipe has and ``flow`` lacks, when ``flow`` was built from an older
    version of it and still starts on the recipe's event; ``{}`` when there is nothing to repair."""
    trigger = recipe.declaration["trigger"]
    if (
        trigger.get("kind") != "event"
        or flow.recipe_digest == digest(recipe)
        or flow.trigger_kind != Flow.Trigger.EVENT
        or flow.trigger_event != trigger.get("event")
    ):
        return {}
    wanted = _words(trigger.get("filter") or {})
    have = flow.trigger_filter or {}
    return {path: clause for path, clause in wanted.items() if path not in have}

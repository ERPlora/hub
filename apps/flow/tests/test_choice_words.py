"""Every value of a closed list an action takes has its words in English and in Spanish (FLOW-F11: «never with its
internal name»).

The step's form offers a closed list (a task's priority, the channel of an order) by its words and «Try it» says them
(``choiceLabel`` of ``frontend/lib/choices.ts``): a status by ``flow.statuses.<app>__<entity>.<value>``, any other
value by ``flow.choices.<field>.<value>`` of ``frontend/locale/{en,es}.json``. A country is named by the browser, a
weekday as the trigger names it, the order of a list by the datum it sorts by, and a number is said as it is, so
those need no words of their own. Without them the screen shows the value as the action keeps it, in English on a
Spanish screen («low, medium, high, urgent»), so this walks everything the editor can offer.
"""

import json
from collections import defaultdict
from pathlib import Path

from django.apps import apps

from apps.flow import queries

from .conftest import A, HUB_DB

pytestmark = HUB_DB

LOCALE = Path(apps.get_app_config("flow").path) / "frontend" / "locale"
#: Named by the browser and by the trigger's weekdays (``COUNTRIES`` and ``WEEKDAYS`` of ``choices.ts``).
COUNTRIES = {"country", "country_code"}
WEEKDAYS = {"day_of_week", "weekday"}


def flow_words(language: str) -> dict:
    return json.loads((LOCALE / f"{language}.json").read_text(encoding="utf-8"))["flow"]


def has_words(language: str, *path: str) -> bool:
    words = flow_words(language)
    for part in path:
        if isinstance(words, list) and part.isdigit():
            words = words[int(part)] if int(part) < len(words) else {}
        else:
            words = words.get(part, {}) if isinstance(words, dict) else {}
    return isinstance(words, str) and bool(words.strip())


def needed_words(action: str, field: str, value: str) -> tuple[str, ...] | None:
    """Where the words of ``value`` live, or ``None`` when it is named without words of its own."""
    key = value.replace("/", "_")
    if value == "" or field in COUNTRIES or value.isdigit() and field not in WEEKDAYS:
        return None
    if field in WEEKDAYS:
        return ("trigger", "weekdays", value)
    if field == "sort":
        return ("fields", value.removeprefix("-"))
    if field == "status":
        app, entity, _ = action.split(".")
        return ("statuses", f"{app}__{entity}", key)
    return ("choices", field, key)


def without_words() -> dict[str, list[str]]:
    missing: dict[str, set[str]] = defaultdict(set)
    for name, op in queries.catalog.ask_first_catalog(A).items():
        for field in queries.catalog.action_fields(op):
            for value in field["choices"]:
                path = needed_words(name, field["name"], value)
                if path and not (has_words("en", *path) and has_words("es", *path)):
                    missing[".".join(path)].add(name)
    return {path: sorted(where)[:3] for path, where in sorted(missing.items())}


def test_the_walk_reaches_the_closed_lists_of_the_actions():
    lists = {
        (name, field["name"])
        for name, op in queries.catalog.ask_first_catalog(A).items()
        for field in queries.catalog.action_fields(op)
        if field["choices"]
    }
    assert {("task.task.create", "priority"), ("task.task.list", "status"), ("sale.payment_method.create", "type")} <= lists


def test_every_value_of_a_closed_list_has_its_words_in_both_languages():
    assert without_words() == {}

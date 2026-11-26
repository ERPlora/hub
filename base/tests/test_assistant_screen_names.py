"""Every value of a closed list a tool answers reaches the model with the name its screens give it, beside its code.

The model never sees a result's schema: a code reaches it as a code, and it wrote «lead» and «walk_in» for what the
customer's card calls «Contacto» and «En el local». The name is the one the app's models give the value (its field's
``choices``, or a closed list the app declares), the one its screens and the cards of the assistant say; each answer
names each value once, under the path of its datum (``screen_names``).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from django.utils import translation
from live import assistant as shared
from live.context import OperationContext
from live.operations import Operation, registry
from ninja import Field, Schema

from apps.demo.models import Item
from base import assistant
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.test_assistant_card_values_amounts import tools

__all__ = ["in_business_a"]

SCREEN_NAMES = shared.SCREEN_NAMES

#: The closed lists of the tools' answers the class still lets through, kept beside this test: ``unnamed``, by tool and
#: by path, the values no app names yet, which the model reads as codes; ``undeclared``, by tool, the paths whose field
#: has choices in its app's models but whose schema does not declare it a closed list, so this test sees it only through
#: those choices and would lose it with them. A tool that answers a new one fails here; naming a value (its field's
#: ``choices``, its app's ``LiveAppConfig.choices`` or a ``choices_of`` mark) or declaring the list takes it off.
KNOWN = json.loads(Path(__file__).with_name("assistant_closed_lists_known.json").read_text())


@dataclass(frozen=True)
class ClosedList:
    """A datum of an answer that is a closed list: its path, its name, the ``choices_of`` mark that names the field of
    its values, its values and whether its schema declares them (``enum``)."""

    path: str
    name: str
    mark: str | None
    values: tuple
    declared: bool


def closed_lists(op: Operation) -> list[ClosedList]:
    """The data of ``op``'s answer that are a closed list, at any depth: those its schema declares one (``enum``) and
    those whose field has choices in its app's models, as the result names them (``live.assistant.screen_name``)."""
    schema = shared.output_schema(op)
    defs = schema.get("$defs", {})
    found: list[ClosedList] = []

    def walk(name: str, prop: dict, path: str, mark: str | None, depth: int) -> None:
        prop = shared.resolved(prop, defs)
        mark = prop.get(shared.CHOICES_OF, mark)
        if depth > 8:
            return
        values = _values(op, name, mark, prop)
        if values is not None:
            found.append(ClosedList(path, name, mark, values, "enum" in prop))
        if isinstance(prop.get("items"), dict):
            walk(name, prop["items"], f"{path}[]", mark, depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner, inner_prop, f"{path}.{inner}", None, depth + 1)

    for name, prop in schema.get("properties", {}).items():
        walk(name, prop, name, None, 0)
    return found


def _values(op: Operation, name: str, mark: str | None, prop: dict) -> tuple | None:
    """The codes of the datum ``name`` when it is a closed list: the ones its schema declares, else its field's choices
    or the list its app declares; ``None`` when it is none."""
    if "enum" in prop:
        return tuple(value for value in prop["enum"] if value not in ("", None) and not isinstance(value, bool))
    if prop.get("type") not in ("integer", "string") or "format" in prop:
        return None
    app_label, field_name = shared.choices_of(op.app_label, name, {shared.CHOICES_OF: mark} if mark else {})
    for field in shared.model_fields(app_label, op.name.split(".")[1], field_name):
        if getattr(field, "flatchoices", None):
            return tuple(code for code, _label in field.flatchoices if code not in ("", None))
    config = shared.config_of(app_label)
    declared = config.choices.get(field_name) if config is not None else None
    return tuple(code for code, _label in declared) if declared else None


def unnamed(operations) -> dict[str, dict[str, list[str]]]:
    """The values of the closed lists of ``operations``' answers the screens name nothing, by tool and by path."""
    found: dict[str, dict[str, list[str]]] = {}
    for op in operations:
        for closed in closed_lists(op):
            codes = sorted({str(value) for value in closed.values if shared.screen_name(op, closed.name, closed.mark, value) is None})
            if codes:
                found.setdefault(op.name, {})[closed.path] = codes
    return dict(sorted(found.items()))


def undeclared(operations) -> dict[str, list[str]]:
    """The closed lists of ``operations``' answers their schema does not declare, by tool: the paths of each."""
    found = {op.name: sorted({closed.path for closed in closed_lists(op) if not closed.declared}) for op in operations}
    return {name: paths for name, paths in sorted(found.items()) if paths}


# ── A demo read, its closed lists at any depth ───────────────────────────────────────────────────────────────────────

Status = Literal["open", "done"]


class ItemOut(Schema):
    status: Status


class FiguresOut(Schema):
    status: Status
    note: str
    rows: list[ItemOut]
    best: ItemOut | None
    states: list[Status] = Field(json_schema_extra={shared.CHOICES_OF: "status"})
    state: str = Field(json_schema_extra={shared.CHOICES_OF: "status"})
    unnamed: Literal["one", "two"]


class PlainOut(Schema):
    note: str
    rows: list[ItemOut]
    unnamed: Literal["one", "two"]


def figures(answer: dict, output: type[Schema] = FiguresOut) -> Operation:
    return Operation(
        name="demo.item.figures",
        kind="query",
        permission="demo.view",
        input=Schema,
        output=output,
        expose_api=False,
        ai={"description": "A read with closed lists."},
        fn=lambda ctx, data: answer,
    )


ANSWER = {
    "status": "open",
    "note": "open",
    "rows": [{"status": "open"}, {"status": "done"}, {"status": "open"}],
    "best": {"status": "done"},
    "states": ["done"],
    "state": "open",
    "unnamed": "one",
}


def told(answer: dict, language: str = "es") -> dict:
    """What the model reads of the demo read answering ``answer`` to a person who speaks ``language``."""
    ctx = OperationContext(scope=A, actor="ana", permissions=frozenset({"demo.view"}), language=language)
    outcome = assistant.tools.run(ctx, figures(answer), "{}")
    assert outcome.outcome == "ok"
    return json.loads(outcome.content)


def on_screen(language: str) -> dict[str, str]:
    """The demo item's states as its screens say them in ``language``."""
    with translation.override(language):
        return {status.value: str(status.label) for status in Item.Status}


@HUB_DB
def test_each_value_of_a_closed_list_reaches_the_model_with_its_screen_name_once_under_its_datum():
    said = on_screen("es")
    assert said != on_screen("en")
    answer = told(ANSWER)
    assert {key: value for key, value in answer.items() if key != SCREEN_NAMES} == ANSWER
    assert answer[SCREEN_NAMES] == {
        "status": {"open": said["open"]},
        "rows.status": {"open": said["open"], "done": said["done"]},
        "best.status": {"done": said["done"]},
        "states": {"done": said["done"]},
        "state": {"open": said["open"]},
    }


@HUB_DB
def test_a_name_that_only_capitalizes_its_code_is_not_told():
    assert SCREEN_NAMES not in told(ANSWER, "en")


@HUB_DB
def test_an_answer_with_no_value_the_screens_name_reaches_the_model_as_before():
    answer = {**ANSWER, "rows": [], "best": None, "states": [], "note": "x", "unnamed": "two"}
    content = assistant.tools.run(
        OperationContext(scope=A, actor="ana", permissions=frozenset({"demo.view"}), language="es"),
        figures(answer, output=PlainOut),
        "{}",
    ).content
    assert content == PlainOut.model_validate(answer).model_dump_json()


@HUB_DB
def test_a_long_answer_with_its_names_still_fits_what_the_model_is_told_at_once():
    answer = told({**ANSWER, "rows": [{"status": "open"}, {"status": "done"}] * 2000})
    assert len(json.dumps(answer, ensure_ascii=False, separators=(",", ":"))) <= shared.MAX_RESULT_CHARS
    assert answer[SCREEN_NAMES]["rows.status"] == {"open": on_screen("es")["open"], "done": on_screen("es")["done"]}
    assert answer["cut"]


# ── The class: every closed list a tool answers ──────────────────────────────────────────────────────────────────────


def test_the_class_finds_the_closed_lists_nobody_names_and_the_undeclared_ones_and_nothing_else():
    assert unnamed([figures(ANSWER)]) == {"demo.item.figures": {"unnamed": ["one", "two"]}}
    assert undeclared([figures(ANSWER)]) == {"demo.item.figures": ["state"]}


class ThingOut(Schema):
    status: Literal["zzz_new", "yyy_new", "active"]
    weekday: int


def test_a_new_tool_with_a_list_its_app_names_only_in_part_or_through_its_models_is_found():
    """A list called like one its app names elsewhere is still told by its own values; a whole number whose field has
    choices in its app's models (the day of a schedule) is a closed list even if its schema says only a number."""
    thing = Operation(
        name="staff.thing.figures",
        kind="query",
        permission="staff.view",
        input=Schema,
        output=ThingOut,
        expose_api=False,
        ai={"description": "A read with closed lists."},
        fn=lambda ctx, data: {},
    )
    assert unnamed([thing]) == {"staff.thing.figures": {"status": ["yyy_new", "zzz_new"]}}
    assert undeclared([thing]) == {"staff.thing.figures": ["weekday"]}
    [weekday] = [closed for closed in closed_lists(thing) if closed.name == "weekday"]
    assert weekday.values == tuple(range(7))


def test_every_closed_list_a_tool_answers_is_named_by_its_screens_but_the_known_ones():
    assert unnamed(tools()) == KNOWN["unnamed"]


def test_every_closed_list_a_tool_answers_is_declared_by_its_schema_but_the_known_ones():
    assert undeclared(tools()) == KNOWN["undeclared"]


def test_no_answer_has_a_datum_of_its_own_called_like_the_names():
    assert [name for name, op in sorted(registry.items()) if SCREEN_NAMES in shared.output_schema(op).get("properties", {})] == []

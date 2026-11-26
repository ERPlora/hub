"""Every value of a closed list a tool answers reaches the model with the name its screens give it, beside its code.

The model never sees a result's schema: a code reaches it as a code, and it wrote «lead» and «walk_in» for what the
customer's card calls «Contacto» and «En el local». The name is the one the app's models give the value (its field's
``choices``, or a closed list the app declares), the one its screens and the cards of the assistant say; each answer
names each value once, under the path of its datum (``screen_names``).
"""

import json
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

#: The closed lists the tools answer whose values no app names yet, by app: each one the model reads as a code. A tool
#: that answers a new one fails here; an app that names one (its field's ``choices``, its ``LiveAppConfig.choices`` or
#: a ``choices_of`` mark) takes it off.
UNNAMED: dict[str, set[str]] = {
    "appointment": {"kind"},
    "attendance": {"running"},
    "base": {
        "actions", "kind", "level", "origin", "pin_inactivity_minutes", "pin_length", "preview", "purpose",
        "retry_blocked", "state", "status",
    },
    "cash_register": {"report"},
    "combo": {"allergens", "status"},
    "flow": {"kind", "outcome", "state"},
    "inventory": {"code", "status"},
    "invoice": {"verifactu_status"},
    "kitchen": {"allergy", "allergy_in_dish", "kind"},
    "modifier": {"target_kind"},
    "online_booking": {"status"},
    "pricing": {"kind"},
    "printing": {"state"},
    "sale": {"allergens", "allergy_in_dish", "reason", "tax_kind"},
    "schedule": {"code", "source"},
    "service": {"default_reason", "kind", "reason", "status"},
    "table": {"status"},
    "tax": {"matched_by", "source", "tax_kind", "tax_operation_class"},
    "verifactu": {"correction_status", "document_type", "documents", "severity", "status"},
    "website": {"state"},
    "whatsapp_inbox": {"reason", "send_blocked"},
}


def closed_lists(op: Operation) -> list[tuple[str, str | None, dict]]:
    """The data of ``op``'s answer that are a closed list, at any depth: its name, the mark that names the field of its
    values (``CHOICES_OF``, a list's for its items too) and its schema."""
    schema = shared.output_schema(op)
    defs = schema.get("$defs", {})
    found: list[tuple[str, str | None, dict]] = []

    def walk(name: str, prop: dict, mark: str | None, depth: int) -> None:
        prop = shared.resolved(prop, defs)
        mark = prop.get(shared.CHOICES_OF, mark)
        if depth > 8:
            return
        if "enum" in prop:
            found.append((name, mark, prop))
        if isinstance(prop.get("items"), dict):
            walk(name, prop["items"], mark, depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner, inner_prop, None, depth + 1)

    for name, prop in schema.get("properties", {}).items():
        walk(name, prop, None, 0)
    return found


def unnamed_by_app(operations) -> dict[str, set[str]]:
    """The closed lists of ``operations``' answers with a value the screens name nothing, by app."""
    found: dict[str, set[str]] = {}
    for op in operations:
        for name, mark, prop in closed_lists(op):
            values = [value for value in prop["enum"] if value not in ("", None) and not isinstance(value, bool)]
            if any(shared.screen_name(op, name, mark, value) is None for value in values):
                found.setdefault(op.app_label, set()).add(name)
    return dict(sorted(found.items()))


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


def test_the_ratchet_finds_a_closed_list_nobody_names_and_nothing_else():
    assert unnamed_by_app([figures(ANSWER)]) == {"demo": {"unnamed"}}


def test_every_closed_list_a_tool_answers_is_named_by_its_screens_but_the_known_ones():
    assert unnamed_by_app(tools()) == UNNAMED


def test_no_answer_has_a_datum_of_its_own_called_like_the_names():
    assert [name for name, op in sorted(registry.items()) if SCREEN_NAMES in shared.output_schema(op).get("properties", {})] == []

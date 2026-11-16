"""An attempt key on the card of a write: never shown, always sent as it came, and marked in every app."""

import dataclasses
import json
import re
from uuid import UUID

import pytest
from live import assistant as shared
from live.operations import Operation, registry
from ninja import Field, Schema

from base import assistant
from base.tests.card_values import ADMIN, VisitIn, ctx, is_attempt_key, values, writes
from base.tests.test_services_assistant import call, turn


# ── An attempt key: never on the card, always in the write ────────────────────────────────────────────────────────────

#: A key of the caller's attempt (idempotency), as a model sends it: born once, the same on every retry, so a retry
#: never charges, sends or prints twice. Nobody can judge it: «Clave del intento: charge-0192f5a0-retry-7».
ATTEMPT = "charge-0192f5a0-retry-7"


class KeyedLineIn(Schema):
    text: str
    client_line_id: str = Field(json_schema_extra={"attempt_key": True})


class KeyedIn(Schema):
    note: str
    idempotency_key: str | None = Field(None, json_schema_extra={"attempt_key": True})
    line: KeyedLineIn | None = None
    lines: list[KeyedLineIn] = []


def keyed(fn=lambda ctx, data: data) -> Operation:
    return Operation(
        name="demo.item.keyed",
        kind="command",
        permission="demo.manage",
        input=KeyedIn,
        output=KeyedIn,
        expose_api=False,
        ai={"description": "A write with the key of its attempt."},
        fn=fn,
    )


KEYED_ARGUMENTS = {
    "note": "Mesa 4",
    "idempotency_key": ATTEMPT,
    "line": {"text": "Café", "client_line_id": f"{ATTEMPT}-1"},
    "lines": [{"text": "Té", "client_line_id": f"{ATTEMPT}-2"}],
}


@pytest.mark.parametrize("language", ["es", "en"])
def test_an_attempt_key_its_schema_marks_never_reaches_the_card_at_any_depth(language):
    """Its line is left out, inside an object and in each item of a list too (which still says how many it carries),
    and an empty one leaves no empty line: the person reads what the write does, not the key that makes it safe."""
    card = assistant.cards.card(keyed(), KEYED_ARGUMENTS, language)
    assert values(card) == {"note": "Mesa 4", "line": {"text": "Café"}, "lines": [{"text": "Té"}]}
    assert ATTEMPT not in json.dumps(card, ensure_ascii=False)
    assert values(assistant.cards.card(keyed(), {"note": "Mesa 4", "idempotency_key": None}, language)) == {"note": "Mesa 4"}


class KeyedPreviewOut(Schema):
    name: str
    idempotency_key: str = Field(json_schema_extra={"attempt_key": True})


@pytest.mark.django_db
def test_an_attempt_key_never_reaches_a_preview_either(monkeypatch):
    """«What will happen» of a dangerous card (BASE-F98) says its data by the same rule: a key its read answers is not
    there, even when its app names it among the preview's data."""
    from base.tests.test_assistant import count_preview, declaring

    read = count_preview({"name": "Item 7", "idempotency_key": ATTEMPT}, output=KeyedPreviewOut)
    write = declaring({"operation": read.name, "fields": ["name", "idempotency_key"]})
    monkeypatch.setitem(registry, read.name, read)
    monkeypatch.setitem(registry, write.name, write)
    failure, fields = assistant.cards.preview(ctx({*ADMIN, "demo.view", "demo.manage"}), write, {"id": "7"})
    assert failure is None
    assert [(field["name"], field["value"]) for field in fields] == [("name", "Item 7")]


@pytest.mark.django_db
def test_the_yes_runs_the_write_with_its_attempt_keys_as_sent(monkeypatch):
    """The card leaves the keys out; the write the yes runs gets every one of them whole, at any depth."""
    received = []
    write = keyed(lambda ctx, data: received.append(data.model_dump()) or data)
    monkeypatch.setitem(registry, write.name, write)
    drawn = turn(call(write.name, KEYED_ARGUMENTS))
    assert ATTEMPT not in json.dumps(drawn["confirm"], ensure_ascii=False)
    plan = turn(*drawn["pending"], decision={"call_id": "c1", "accepted": True})
    assert plan["executed"][0]["outcome"] == "ok"
    assert received == [KEYED_ARGUMENTS]


@pytest.mark.django_db
def test_a_line_the_assistant_adds_twice_with_its_key_is_one_line():
    """A real write: Demo's line, its card without its key (its item by its name, hub#670); the yes adds it, and the
    same line again — a retry with the same key — answers the line already there instead of adding another."""
    from base.tests.test_services_assistant import run

    item = run("demo.item.create", name="Mesa 4")
    line = {"id": item["id"], "text": "Café", "qty": "1", "client_line_id": "0192f5a0-0000-7000-8000-000000000001"}
    drawn = turn(call("demo.item.add_line", line))
    assert values(drawn["confirm"]) == {"id": "Mesa 4", "text": "Café", "qty": "1"}
    for _ in range(2):
        plan = turn(*drawn["pending"], decision={"call_id": "c1", "accepted": True})
        assert plan["executed"][0]["outcome"] == "ok"
    lines = run("demo.item.detail", id=item["id"])["lines"]
    assert [(row["text"], row["client_line_id"]) for row in lines] == [("Café", line["client_line_id"])]


# ── The ratchet: attempt keys nobody marks, by app ────────────────────────────────────────────────────────────────────

#: How an attempt key is named in this repo: ``idempotency_key`` (Sales, Payments), ``job_key`` (Printing),
#: ``submit_key`` and ``client_message_id`` (WhatsApp inbox), ``client_line_id`` (Demo), or any name that says
#: idempotency or attempt key. Only a text: ``attempt`` (Printing, which hand-out printed) is a count, and
#: ``tax_category_key`` or ``regime_key`` name a record of a list.
ATTEMPT_KEY_NAME = re.compile(r"idempoten|attempt_key|^(?:job|submit)_key$|^client_\w+_id$")

#: The attempt keys of the assistant's writes no ``attempt_key`` mark declares, by app: their card shows them, or
#: leaves them out only as an id it cannot name. Only ever lower: an app that marks its own lowers its number here,
#: and none comes in.
UNMARKED_ATTEMPT_KEYS: dict[str, int] = {}


def unmarked_attempt_keys(op: Operation) -> list[str]:
    """``op``'s data that look like an attempt key by their name (``ATTEMPT_KEY_NAME``, a text) and no mark declares
    so, at any depth."""
    found: list[str] = []
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})

    def walk(name: str, prop: dict, path: str, depth: int) -> None:
        prop = shared.resolved(prop, defs)
        if depth > 8:
            return
        if prop.get("type") == "string" and ATTEMPT_KEY_NAME.search(name) and not is_attempt_key(prop):
            found.append(path)
        if isinstance(prop.get("items"), dict):
            walk(name, prop["items"], f"{path}[]", depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner, inner_prop, f"{path}.{inner}", depth + 1)

    for name, prop in schema.get("properties", {}).items():
        walk(name, prop, name, 0)
    return found


def attempt_keys_by_app(operations) -> dict[str, int]:
    counted: dict[str, int] = {}
    for op in operations:
        if found := unmarked_attempt_keys(op):
            counted[op.app_label] = counted.get(op.app_label, 0) + len(found)
    return dict(sorted(counted.items()))


def test_every_attempt_key_of_a_write_is_marked_but_the_known_ones():
    """A new attempt key without its mark fails here; an app that marks its own lowers its number."""
    assert attempt_keys_by_app(writes()) == UNMARKED_ATTEMPT_KEYS


class UnmarkedKeysIn(Schema):
    idempotency_key: str
    lines: list[KeyedLineIn] = []
    visits: list[VisitIn] = []
    client_visit_id: UUID | None = None
    marked_key: str = Field(json_schema_extra={"attempt_key": True})
    job_key: str = Field(json_schema_extra={"attempt_key": True})
    attempt: int = 1
    tax_category_key: str = ""
    session_token: str = ""


def test_the_ratchet_counts_an_attempt_key_nobody_marks_and_nothing_else():
    """Its name gives it away at any depth, an id one too; a marked one, a count of attempts or the key of a record of
    a list are not counted."""
    op = dataclasses.replace(keyed(), input=UnmarkedKeysIn, output=UnmarkedKeysIn)
    assert unmarked_attempt_keys(op) == ["idempotency_key", "client_visit_id"]
    assert attempt_keys_by_app([op, op]) == {"demo": 4}


def misplaced_marks(op: Operation) -> list[str]:
    """``op``'s data marked ``attempt_key`` that are no text, at any depth."""
    found: list[str] = []
    schema = op.input.model_json_schema()
    defs = schema.get("$defs", {})

    def walk(prop: dict, path: str, depth: int) -> None:
        prop = shared.resolved(prop, defs)
        if depth > 8:
            return
        if is_attempt_key(prop) and prop.get("type") != "string":
            found.append(path)
        if isinstance(prop.get("items"), dict):
            walk(prop["items"], f"{path}[]", depth + 1)
        for inner, inner_prop in prop.get("properties", {}).items():
            walk(inner_prop, f"{path}.{inner}", depth + 1)

    for name, prop in schema.get("properties", {}).items():
        walk(prop, name, 0)
    return found


class MisplacedIn(Schema):
    amount_cents: int = Field(json_schema_extra={"attempt_key": True})
    line: KeyedLineIn
    visit: VisitIn = Field(json_schema_extra={"attempt_key": True})


def test_an_attempt_key_is_marked_only_on_a_text():
    """The mark leaves its datum out of the card: on anything but a text (an amount, an object) it would hide what the
    person confirms. Every operation of every app, at any depth."""
    misplaced = dataclasses.replace(keyed(), input=MisplacedIn, output=MisplacedIn)
    assert misplaced_marks(misplaced) == ["amount_cents", "visit"]
    assert [f"{name}:{path}" for name, op in sorted(registry.items()) for path in misplaced_marks(op)] == []

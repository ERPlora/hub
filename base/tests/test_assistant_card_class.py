"""Every write of every app, on its card: an amount as money however the model writes it, never an id of ours, every
datum by its name in the person's language, a value that means there is no limit said so and a price by weight with
its unit. A new tool that breaks one of them fails here, not in front of a person."""

import json
import re
from pathlib import Path

import pytest
from django.utils import translation
from live import assistant as shared
from live.assistant import generated_title, own_title, verbose_name
from live.operations import Operation
from pydantic import ValidationError

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.card_values import writes

__all__ = ["in_business_a"]

AN_ID = "0190f5a8-7b1c-7d2e-8f3a-4b5c6d7e8f90"
ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

#: A text that says it carries the id of a record of ours, though its schema does not declare one (``format: uuid``).
SAYS_AN_ID = re.compile(r"^(?:the |its )?id of\b|\bby (?:its )?id\b|\bits id or\b", re.IGNORECASE)

#: A whole number whose description says one of its values means there is no limit («0 = no ceiling», «100 = no cap»).
NO_LIMIT_WORDS = re.compile(r"\b(\d+)\s*(?:=|means)\s*(?:no (?:limit|ceiling|cap)|unlimited)\b", re.IGNORECASE)

#: The datum that names the unit a price is for, beside it.
PRICING_UNIT = "pricing_unit"

#: The data the screen names itself in the person's language (``FIELDS`` of the card in @erplora/ui): its label from
#: the server is never shown.
_UI_CARD = Path(__file__).resolve().parents[2] / "packages/ui/src/components/Assistant/card.ts"


def named_by_the_screen() -> set[str]:
    source = _UI_CARD.read_text(encoding="utf-8")
    listed = re.search(r"const FIELDS = \[(.*?)\];", source, re.DOTALL)
    assert listed is not None, "the card of @erplora/ui no longer lists the data it names itself"
    return set(re.findall(r"'([a-z_]+)'", listed.group(1)))


def schema_of(op: Operation) -> tuple[dict, dict]:
    schema = shared.input_schema(op)
    return schema.get("properties", {}), schema.get("$defs", {})


#: How a model writes a moment of each kind.
MOMENT_SAMPLES = {"date": "2026-11-26", "time": "10:00", "date-time": "2026-11-26T10:00:00+01:00"}


def sample(prop: dict, defs: dict, depth: int = 0):
    """A value of ``prop`` as a model would send it: our ids where it takes one, the figures of an amount as a text."""
    prop = shared.resolved(prop, defs)
    kind = prop.get("type")
    if depth > 6 or "const" in prop or "enum" in prop:
        return prop.get("const", (prop.get("enum") or [None])[0])
    if kind == "array":
        items = prop.get("items")
        return [sample(items if isinstance(items, dict) else {}, defs, depth + 1)]
    if kind == "object" or "properties" in prop:
        return {key: sample(inner, defs, depth + 1) for key, inner in prop.get("properties", {}).items()}
    return scalar(prop, kind)


def scalar(prop: dict, kind: str | None):
    form = prop.get("format")
    if form == "uuid" or (kind == "string" and SAYS_AN_ID.search(str(prop.get("description", "")))):
        return AN_ID
    if form in MOMENT_SAMPLES:
        return MOMENT_SAMPLES[form]
    if kind == "integer":
        return "300" if shared.is_money(prop) else max(prop.get("minimum", 1), 1)
    return {"number": 1, "boolean": True}.get(kind or "", "Texto")


def card_of(op: Operation, arguments: dict, language: str = "es") -> dict:
    return assistant.cards.card(op, arguments, language)


# ── An amount, never in cents ─────────────────────────────────────────────────────────────────────────────────────────


def refuses(op: Operation, name: str, sent) -> bool:
    """Whether the write ``op`` refuses ``sent`` as its datum ``name`` (a strict amount takes no text): then no card is
    drawn, and the model is told which datum to correct."""
    try:
        op.input.model_validate({name: sent})
    except ValidationError as error:
        return any(tuple(each["loc"][:1]) == (name,) for each in error.errors())
    return False


def amounts_said_as_sent(op: Operation) -> list[str]:
    """The amounts of ``op`` its card paints as sent when the model writes them as a text or with decimals, and the
    write takes them."""
    props, defs = schema_of(op)
    found = []
    for name, prop in props.items():
        if not (shared.is_money(shared.resolved(prop, defs)) and shared.resolved(prop, defs).get("type") == "integer"):
            continue
        for sent in ("300", 300.0):
            if refuses(op, name, sent):
                continue
            field = next(field for field in card_of(op, {name: sent})["fields"] if field["name"] == name)
            if field["kind"] != "money":
                found.append(f"{op.name}:{name}={sent!r}")
    return found


@HUB_DB
def test_every_amount_a_write_sends_is_said_as_money_however_the_model_writes_it():
    """A supplement of 3 € reached a card as «300»: the model wrote the figure as a text and the card painted it as
    sent. Every amount of every write is painted as the write takes it."""
    assert [found for op in writes() for found in amounts_said_as_sent(op)] == []


# ── Never an id of ours ──────────────────────────────────────────────────────────────────────────────────────────────


def ids_shown(op: Operation) -> list[str]:
    props, defs = schema_of(op)
    arguments = {name: sample(prop, defs) for name, prop in props.items()}
    return [f"{op.name}:{field['name']}" for field in card_of(op, arguments)["fields"] if ID.search(json.dumps(field))]


@HUB_DB
def test_no_write_shows_an_id_of_ours_on_its_card():
    """A record is said by its name or not at all; a text that carries the id of one says so in its description, and
    its card leaves it out like any other id."""
    assert [found for op in writes() for found in ids_shown(op)] == []


# ── Every datum by its name ──────────────────────────────────────────────────────────────────────────────────────────


def unnamed(op: Operation, screen_names: set[str]) -> list[str]:
    """The data of ``op`` its card names, in Spanish, by a name made up from the code's (pydantic's title of the datum,
    which no catalog translates): ones the screen names itself aside."""
    props, defs = schema_of(op)
    entity = op.name.split(".")[1]
    found = []
    with translation.override("es"):
        for name, prop in props.items():
            title = prop.get("title")
            made_up = title in (None, generated_title(name))
            if name in screen_names or own_title(name, title) is not None or verbose_name(op.app_label, entity, name):
                continue
            if made_up and translation.gettext(generated_title(name)) == generated_title(name):
                found.append(f"{op.name}:{name}")
    return found


@HUB_DB
def test_every_datum_on_a_card_has_its_name_in_the_persons_language():
    screen_names = named_by_the_screen()
    assert [found for op in writes() for found in unnamed(op, screen_names)] == []


# ── What a figure means ──────────────────────────────────────────────────────────────────────────────────────────────


def unmarked_no_limit(op: Operation) -> list[str]:
    props, defs = schema_of(op)
    found = []
    for name, prop in props.items():
        said = NO_LIMIT_WORDS.search(str(prop.get("description", "")))
        if said and shared.resolved(prop, defs).get("no_limit") != int(said.group(1)):
            found.append(f"{op.name}:{name}")
    return found


@HUB_DB
def test_every_value_that_means_no_limit_says_so_on_its_card():
    """A maximum of 0 that means no limit reached the card as «0»: whatever its description says a value means, its
    schema declares it (``no_limit``), and the card says «No limit» for it."""
    assert [found for op in writes() for found in unmarked_no_limit(op)] == []


def unmarked_per_unit(op: Operation) -> list[str]:
    props, defs = schema_of(op)
    if PRICING_UNIT not in props:
        return []
    return [
        f"{op.name}:{name}"
        for name, prop in props.items()
        if shared.is_money(shared.resolved(prop, defs)) and "per_unit" not in shared.resolved(prop, defs)
    ]


@HUB_DB
def test_every_price_beside_its_unit_of_sale_says_it():
    """Prawns at 45 € the kilo reached the card as «Precio: 45,00 €»: a price beside the unit it is for declares so
    (``per_unit``), and the card says «Precio por kg»."""
    assert [found for op in writes() for found in unmarked_per_unit(op)] == []


@pytest.mark.parametrize(
    ("description", "value"),
    [("0 = no ceiling", 0), ("Maximum picks; 0 means no limit.", 0), ("100 = no cap.", 100), ("0 = none", None)],
)
def test_the_check_reads_what_a_value_means_from_its_description(description, value):
    said = NO_LIMIT_WORDS.search(description)
    assert (int(said.group(1)) if said else None) == value

"""A tool's description never quotes a text of the screens in English.

Asked in Spanish what was left to set up, the assistant answered «Te faltan 4 pasos de la lista «Finish setting up your
business»»: the description of the read quoted the Home's title in English, and the model took the quoted words for a
name to repeat as they are. The screens speak the person's language: a description says in its own words what a thing
of the screens is, and a read whose answer the model must name hands it over in the person's language.
"""

import json
import re
from collections.abc import Iterator
from functools import cache
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.operations import registry

from base.tests.po import po_messages

#: A quotation as the descriptions write one: «…», "…" or “…”.
QUOTED = re.compile(r"«([^»]+)»|\"([^\"]+)\"|“([^”]+)”")


def _strings(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, str):
        yield node


@cache
def screen_texts() -> frozenset[str]:
    """The English texts of the Hub's screens: those of the screens' catalogues and the msgids of the server's, base's
    and each app's, which the person reads translated."""
    root = Path(settings.BASE_DIR)
    texts: set[str] = set()
    for path in [root / "base/frontend/locale/en.json", *sorted(root.glob("apps/*/frontend/locale/en.json"))]:
        texts.update(_strings(json.loads(path.read_text(encoding="utf-8"))))
    for path in [root / "base/locale/es/LC_MESSAGES/django.po", *sorted(root.glob("apps/*/locale/es/LC_MESSAGES/django.po"))]:
        texts.update(message.id[0] if message.pluralizable else message.id for message in po_messages(path))
    return frozenset(texts)


def quoted_screen_texts(text: str) -> list[str]:
    quoted = (next(group for group in match.groups() if group) for match in QUOTED.finditer(text))
    return [said for said in quoted if said in screen_texts()]


def test_a_quoted_text_of_a_screen_or_of_the_server_is_found_and_no_other_quotation():
    said = (
        "Reads the checklist «Finish setting up your business»; its step «Your apps» and its key «base.apps», "
        'a state "pending" and a question «how many are in?».'
    )
    assert quoted_screen_texts(said) == ["Finish setting up your business", "Your apps"]


TOOLS = sorted(name for name, op in registry.items() if shared.is_tool(op))


@pytest.mark.parametrize("name", TOOLS)
def test_a_tool_description_quotes_no_text_of_the_screens_in_english(name):
    assert quoted_screen_texts(shared.description(registry[name])) == []


#: The clause of a field's description that says what an empty value becomes, up to its end.
WHAT_EMPTY_BECOMES = re.compile(r"\b(?:empty|blank|omitted|not sent)\b[^.;]*", re.IGNORECASE)


def _fields(parameters: dict) -> Iterator[tuple[str, dict]]:
    for name, prop in parameters.get("properties", {}).items():
        yield name, prop
    for model, schema in parameters.get("$defs", {}).items():
        for name, prop in schema.get("properties", {}).items():
            yield f"{model}.{name}", prop


def _is_text(prop: dict) -> bool:
    return prop.get("type") == "string" or any(one.get("type") == "string" for one in prop.get("anyOf", []))


def english_defaults(parameters: dict) -> list[tuple[str, list[str]]]:
    """The text fields of a tool whose description tells the model, quoted, the English text an empty value becomes."""
    found = []
    for path, prop in _fields(parameters):
        clauses = WHAT_EMPTY_BECOMES.findall(prop.get("description", "")) if _is_text(prop) else []
        quoted = [said for clause in clauses for said in quoted_screen_texts(clause)]
        if quoted:
            found.append((path, quoted))
    return found


def test_a_text_fields_english_default_is_found_and_no_other_quotation():
    parameters = {
        "properties": {
            "name": {"type": "string", "description": "Name of the schedule; empty = «Regular schedule»."},
            "title": {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "A title; blank: «Note added»."},
            "printer": {"type": "string", "description": "A printer by its name («Kitchen»); empty = any."},
            "preselected": {"type": "integer", "description": "Which suggestion comes chosen; empty = «No tip»."},
        },
        "$defs": {"About": {"properties": {"title": {"type": "string", "description": "Heading; empty = «About us»."}}}},
    }
    assert english_defaults(parameters) == [
        ("name", ["Regular schedule"]),
        ("title", ["Note added"]),
        ("About.title", ["About us"]),
    ]


@pytest.mark.parametrize("name", TOOLS)
def test_a_tool_never_tells_the_model_the_english_text_an_empty_field_becomes(name):
    """Asked in Spanish for Ana's week, the assistant saved her schedule as «Regular schedule»: the name's description
    said «empty = «Regular schedule»», and the model sent those words as the name. An empty text field is named by the
    Hub in the person's language; its description says so in its own words."""
    assert english_defaults(shared.tool_spec(registry[name])["parameters"]) == []

"""base.release_note.list: what is new in ERPlora for the business, newest first, in the person's language.

Anyone in the business may read it, like the notes a POS publishes: they say what changed, nothing of the business.
The notes are those the image ships, so the stand-ins here replace what the image would have read.
"""

import datetime as dt

import pytest
from live.assistant import description
from live.context import OperationContext
from live.errors import PermissionDenied
from live.operations import get

from base import release_notes
from base.release_notes import Note, Text
from base.tenancy.tests.business import HUB_DB, A, in_business_a

__all__ = ["in_business_a"]

#: An operation runs inside the business of its request, even one that reads no database.
pytestmark = HUB_DB


def note(day: int, name: str, kind: str = "new") -> Note:
    return Note(
        id=f"2026-11-{day:02d}-{name}",
        date=dt.date(2026, 11, day),
        kind=kind,
        texts={"en": Text(f"{name} title", f"{name} body"), "es": Text(f"título de {name}", f"texto de {name}")},
    )


NOTES = (note(19, "allergens"), note(12, "tables", "improved"), note(3, "receipts", "fixed"))


@pytest.fixture(autouse=True)
def shipped(monkeypatch):
    monkeypatch.setattr(release_notes, "shipped", lambda: NOTES)


def run(language: str = "en", *permissions: str, **data) -> dict:
    op = get("base.release_note.list")
    ctx = OperationContext(
        scope=A, actor="ana", permissions=frozenset(permissions or {"base.view_home"}), language=language
    )
    return op(ctx, op.input.model_validate(data)).model_dump(mode="json")


def test_anyone_in_the_business_reads_it_without_its_database_and_the_assistant_offers_it():
    op = get("base.release_note.list")

    assert (op.kind, op.permission, op.database) == ("query", "base.view_home", False)
    assert description(op)
    assert set(op.ai.asks) == {"en", "es"}
    with pytest.raises(PermissionDenied):
        run("en", "base.something_else")


def test_the_notes_come_newest_first_with_their_day_kind_and_text():
    assert run("en") == {
        "items": [
            {"id": "2026-11-19-allergens", "date": "2026-11-19", "kind": "new", "title": "allergens title", "body": "allergens body"},
            {"id": "2026-11-12-tables", "date": "2026-11-12", "kind": "improved", "title": "tables title", "body": "tables body"},
            {"id": "2026-11-03-receipts", "date": "2026-11-03", "kind": "fixed", "title": "receipts title", "body": "receipts body"},
        ],
        "total": 3,
    }


@pytest.mark.parametrize(("language", "title"), [("es", "título de allergens"), ("es-ES", "título de allergens"), ("en-GB", "allergens title")])
def test_each_person_reads_them_in_their_language(language, title):
    assert run(language)["items"][0]["title"] == title


def test_a_language_the_deployment_does_not_speak_reads_them_in_english():
    assert run("fr")["items"][0]["title"] == "allergens title"


def test_a_page_of_them_says_how_many_there_are_in_all():
    page = run("en", limit=1, offset=1)

    assert ([item["id"] for item in page["items"]], page["total"]) == (["2026-11-12-tables"], 3)
    assert run("en", offset=3) == {"items": [], "total": 3}


@pytest.mark.parametrize("data", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_a_page_out_of_bounds_is_refused(data):
    with pytest.raises(ValueError):
        get("base.release_note.list").input.model_validate(data)


def test_without_notes_the_list_is_empty(monkeypatch):
    monkeypatch.setattr(release_notes, "shipped", lambda: ())

    assert run("en") == {"items": [], "total": 0}

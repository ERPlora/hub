"""What every schema of the book shares: an input refuses a field it does not declare, a reaction ignores the rest
of its payload, a page reads fifty rows unless told otherwise and never more than one hundred, and what a person says
is trimmed and bounded."""

from uuid import UUID

from apps.reservation.schemas.fields import (
    Guests,
    In,
    Minutes,
    NoIn,
    PageIn,
    Reaction,
    Said,
    Weekday,
)

from .conftest import errors

AN_ID = "0192f0d4-0000-7000-8000-000000000001"


class Probe(In):
    said: Said
    guests: Guests = 1
    minutes: Minutes = 1
    weekday: Weekday = 0


class Heard(Reaction):
    id: UUID | None = None


def test_an_input_refuses_a_field_it_does_not_declare():
    assert "colour" in errors(NoIn, {"colour": "red"})
    assert "colour" in errors(Probe, {"said": "Ana", "colour": "red"})


def test_a_reaction_reads_what_it_declares_and_ignores_the_rest():
    assert Heard.model_validate({"id": AN_ID, "other": True}).id == UUID(AN_ID)


def test_a_page_reads_fifty_rows_unless_told_otherwise_and_never_more_than_one_hundred():
    page = PageIn.model_validate({})
    assert (page.limit, page.offset) == (50, 0)
    assert "limit" in errors(PageIn, {"limit": 101})
    assert "limit" in errors(PageIn, {"limit": 0})
    assert "offset" in errors(PageIn, {"offset": -1})


def test_what_a_person_says_is_trimmed_and_never_empty():
    assert Probe.model_validate({"said": "  Ana  "}).said == "Ana"
    assert "said" in errors(Probe, {"said": "   "})
    assert "said" in errors(Probe, {"said": "x" * 101})


def test_the_guests_the_minutes_and_the_weekday_stay_within_the_book_s_bounds():
    assert Probe.model_validate({"said": "Ana", "guests": 999, "minutes": 24 * 60, "weekday": 6}).weekday == 6
    assert "guests" in errors(Probe, {"said": "Ana", "guests": 1000})
    assert "minutes" in errors(Probe, {"said": "Ana", "minutes": 24 * 60 + 1})
    assert "weekday" in errors(Probe, {"said": "Ana", "weekday": 7})
    assert Probe.model_json_schema()["properties"]["weekday"]["enum"] == list(range(7))

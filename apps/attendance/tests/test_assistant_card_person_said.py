"""The card of a clock-in, a clock-out or a break that names its person in words says the person the write will clock,
as the same search finds them, never the words said (ATTENDANCE-F02, ATTENDANCE-F12, BASE-F97).

With «Luis García» in Staff, «pon a Luis en pausa» drew «Empezar en Control horario: Luis», and whoever confirmed could
not see whom the break was for (hub#2297). Words that fit several people, or nobody, draw no card: the model hears why
and asks. So does a write the person could not do: clocking someone else without «Clock others», or their own break
without a staff record."""

import dataclasses

import pytest

from apps.attendance.models import Break, Record
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, said, the_model_hears, turn_as, yes_to
from base.tests.test_services_assistant import call

from .conftest import HUB_DB, ctx_for, make_member
from .test_integration_assistant import CLOCKING, manager, open_day

pytestmark = HUB_DB


@pytest.fixture
def marta(make_user):
    """Marta manages the team: she clocks the others in and out by their names."""
    return manager(make_user, None)


@pytest.fixture
def luis():
    return make_member("Luis", "García")


def turn(ctx, write: str, arguments: dict, language: str = "es") -> dict:
    return turn_as(dataclasses.replace(ctx, language=language), call(write, arguments))


@pytest.mark.parametrize("write", CLOCKING)
def test_the_card_of_a_person_named_in_words_names_the_person_the_search_finds(marta, luis, write):
    for language in ("es", "en"):
        assert said(turn(marta, write, {"member": "luis"}, language)) == [("member", "Luis García")]


def test_the_yes_to_that_card_starts_the_break_of_the_person_it_named(marta, luis, clock):
    clock("2026-10-06T09:00")
    day = open_day(luis)
    spanish = dataclasses.replace(marta, language="es")
    plan = turn(spanish, "attendance.break.start", {"member": "luis"})
    yes_to(plan, turn_of=lambda *calls, decision: turn_as(spanish, *calls, decision=decision))
    assert list(Break.objects.filter(ended_at__isnull=True).values_list("record", flat=True)) == [day.id]


@pytest.mark.parametrize("write", CLOCKING)
def test_words_that_fit_two_people_draw_no_card_and_the_model_hears_which(marta, luis, write):
    make_member("Luisa", "Martín")
    plan = turn(marta, write, {"member": "Luis"})
    no_card_but_the_model_hears(plan, "attendance.ambiguous_member")
    heard = the_model_hears(plan)["message"]
    assert "Luis García" in heard and "Luisa Martín" in heard


@pytest.mark.parametrize("write", CLOCKING)
def test_words_that_fit_nobody_draw_no_card(marta, luis, write):
    no_card_but_the_model_hears(turn(marta, write, {"member": "Pedro"}), "not_found")


def test_words_beside_the_persons_id_are_neither_read_nor_shown(marta, luis):
    """The write takes the person by their id then: the card names that one, never the one the words would find."""
    make_member("Bea", "Ruiz")
    shown = dict(said(turn(marta, "attendance.break.start", {"member_id": str(luis.id), "member": "Bea"})))
    assert (shown["member_id"], "member" in shown) == ("Luis García", False)


@pytest.mark.parametrize("write", CLOCKING)
def test_who_only_clocks_themselves_gets_no_card_for_someone_else(person, luis, write):
    _, ana = person()
    plan = turn(ana, write, {"member": "Luis"})
    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("refused", "permission_denied")]


@pytest.mark.parametrize("write", CLOCKING)
def test_whoever_has_no_staff_record_gets_no_card_for_their_own(write):
    no_card_but_the_model_hears(turn(ctx_for("hub_admin"), write, {}), "attendance.no_member_record")
    assert not Record.objects.exists()


def test_an_employee_pausing_themselves_draws_the_card_with_nothing_else_to_say(person, clock):
    """«Pon que estoy en pausa»: no person named, the break is the caller's own; the verb says the rest."""
    ana, ctx = person()
    clock("2026-10-06T09:00")
    open_day(ana)
    plan = turn(ctx, "attendance.break.start", {})
    assert (plan["confirm"]["operation"], said(plan)) == ("attendance.break.start", [])

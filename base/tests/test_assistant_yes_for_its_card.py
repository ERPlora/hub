"""hub#1208: the person's yes runs a write only on what its card showed them (BASE-F97, BASE-F98).

A card is drawn from what the Hub reads as the person — the record a datum names, by its id or by its name as the write
will find it; the write's check; what a dangerous write will do — and the call it waits on comes back with the
fingerprint of what it showed (``shown``), as the panel gives back the calls that wait. With the yes the Hub draws it
again: when what it shows, or a record it found, is not the same any more, nothing runs and the new card is shown.
"""

import pytest
from live.context import OperationContext, Scope
from live.operations import Operation, get, registry
from ninja import Schema
from pydantic import Field

from apps.demo.models import Item
from base.schemas import names
from base.tenancy import context
from base.tenancy.tests import hubs
from base.tests.test_services_assistant import ASK, MANAGER, asked, call, turn

pytestmark = pytest.mark.django_db


def yes_to(plan: dict, *, typed: str | None = None, turn_of=turn, **extra) -> dict:
    """The person's yes to ``plan``'s card (the word it asks, unless ``typed``), with the calls that wait as the turn
    gave them back, as the panel does; ``turn_of``, the turn of the test."""
    word = plan["confirm"]["confirm_word"] if typed is None else typed
    decision = {"call_id": plan["pending"][0]["call_id"], "accepted": True, "typed": word}
    return turn_of(*plan["pending"], decision=decision, **extra)


def turn_as(person: OperationContext, *calls, decision: dict | None = None) -> dict:
    """``base.assistant.turn`` as ``person`` (an app's own, with its roles), after the model asked for ``calls``."""
    op = get("base.assistant.turn")
    data = {"messages": [ASK, asked(*calls)], "pending": list(calls), "decision": decision}
    return op(person, op.input.model_validate(data)).model_dump(mode="json")


def yes_to_its_card(person: OperationContext, write: str, arguments: dict, meanwhile=lambda: None) -> dict:
    """The case of hub#1208 for any app: ``person`` asks for ``write`` with ``arguments`` (its record by its name), its
    card is drawn, ``meanwhile`` happens (somebody else creates a record the name fits better), and the person says
    yes to that card as the panel sends it. → the yes's turn."""
    plan = turn_as(person, call(write, arguments))
    if plan["confirm"] is None or plan["confirm"]["operation"] != write:
        raise LookupError(f"no card of {write}: {plan['executed']}")
    meanwhile()
    return yes_to(plan, turn_of=lambda *calls, decision: turn_as(person, *calls, decision=decision))


def read_as(mark: dict) -> dict:
    """How the card reads a datum by its mark (``names``), but for the data beside which it leaves it unread
    (``unless``, hub#1250): an app compares how it reads each datum apart from where it does not."""
    return {"refers": {key: value for key, value in mark["refers"].items() if key != "unless"}}


def unless_of(mark: dict) -> set[str]:
    """The data beside which the card leaves a datum by its mark unread (``unless``, hub#1250)."""
    return set(mark["refers"].get("unless", ()))


def said(plan: dict) -> list[tuple[str, object]]:
    return [(field["name"], field["value"]) for field in plan["confirm"]["fields"]]


def kept() -> set[str]:
    return set(Item.objects.values_list("name", flat=True))


# ── A record named by its name ────────────────────────────────────────────────────────────────────────────────────────


def test_the_yes_to_its_card_runs_the_write_on_what_it_showed():
    """Positive control: nothing changed between the card and the yes."""
    Item.objects.create(name="Mesa 4")
    plan = turn(call("demo.item.delete", {"called": "mesa"}))
    assert said(plan) == [("called", "Mesa 4")]

    done = yes_to(plan)

    assert [(row["name"], row["outcome"]) for row in done["executed"]] == [("demo.item.delete", "ok")]
    assert kept() == set()


def test_a_name_another_record_fits_better_before_the_yes_shows_the_new_card_and_deletes_nothing():
    """The case of the issue: «elimina mesa» shows «Mesa 4»; somebody creates «Mesa» before the yes (the same name wins
    over one that holds it): the yes deletes nothing, and the card now says «Mesa»."""
    Item.objects.create(name="Mesa 4")
    plan = turn(call("demo.item.delete", {"called": "mesa"}))
    Item.objects.create(name="Mesa")

    again = yes_to(plan)

    assert (again["executed"], again["append"], said(again)) == ([], [], [("called", "Mesa")])
    assert [p["call_id"] for p in again["pending"]] == ["c1"]
    assert kept() == {"Mesa 4", "Mesa"}


def test_the_yes_to_the_new_card_runs_on_what_the_new_card_shows():
    Item.objects.create(name="Mesa 4")
    plan = turn(call("demo.item.delete", {"called": "mesa"}))
    Item.objects.create(name="Mesa")

    done = yes_to(yes_to(plan))

    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert kept() == {"Mesa 4"}


def test_another_record_under_the_same_name_is_not_what_the_card_showed():
    """What the card found counts, not only the words it said: «Mesa 4» renamed «Barra» and another «Mesa 4» created
    before the yes — the same card, another record —: nothing runs, and the card is shown again."""
    first = Item.objects.create(name="Mesa 4")
    plan = turn(call("demo.item.delete", {"called": "mesa 4"}))
    Item.objects.filter(pk=first.pk).update(name="Barra")
    Item.objects.create(name="Mesa 4")

    again = yes_to(plan)

    assert (again["executed"], said(again)) == ([], [("called", "Mesa 4")])
    assert kept() == {"Barra", "Mesa 4"}


def test_a_record_gone_before_the_yes_is_the_writes_failure_and_nothing_runs():
    """What it found was deleted meanwhile: no card that would act on another, the model hears why (its check)."""
    item = Item.objects.create(name="Mesa 4")
    plan = turn(call("demo.item.delete", {"called": "mesa"}))
    item.delete()
    Item.objects.create(name="Barra")

    gone = yes_to(plan)

    assert gone["confirm"] is None
    assert [(row["outcome"], row["code"]) for row in gone["executed"]] == [("error", "not_found")]
    assert kept() == {"Barra"}


# ── A record named by its id ──────────────────────────────────────────────────────────────────────────────────────────


def test_a_record_renamed_before_the_yes_shows_its_card_with_the_new_name():
    """The same record, but the card said another name: the yes was for what it said."""
    item = Item.objects.create(name="Mesa 4")
    plan = turn(call("demo.item.delete", {"id": str(item.id)}))
    Item.objects.filter(pk=item.pk).update(name="Mesa 5")

    again = yes_to(plan)

    assert (again["executed"], said(again)) == ([], [("id", "Mesa 5")])
    assert kept() == {"Mesa 5"}


def test_a_yes_to_a_card_never_drawn_draws_it_and_runs_nothing():
    """A yes that comes with no card behind it (its call carries none): the card first, as for any write."""
    item = Item.objects.create(name="Mesa 4")
    write = call("demo.item.delete", {"id": str(item.id)})

    plan = turn(write, decision={"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"})

    assert (plan["executed"], plan["confirm"]["operation"], said(plan)) == ([], "demo.item.delete", [("id", "Mesa 4")])
    assert kept() == {"Mesa 4"}


def test_the_no_and_a_wrong_word_still_run_nothing_whatever_changed():
    """Only a yes is held to its card: a «no» and a word typed wrong are never turned into a card again."""
    item = Item.objects.create(name="Mesa 4")
    plan = turn(call("demo.item.delete", {"id": str(item.id)}))
    Item.objects.filter(pk=item.pk).update(name="Mesa 5")
    pending = plan["pending"]

    no = turn(*pending, decision={"call_id": "c1", "accepted": False})
    wrong = yes_to(plan, typed="CONFIRMA")

    for answer in (no, wrong):
        assert answer["confirm"] is None
        assert [(row["outcome"], row["code"]) for row in answer["executed"]] == [
            ("cancelled", "base.assistant_not_confirmed")
        ]
    assert kept() == {"Mesa 5"}


def test_only_the_call_the_card_waits_on_carries_what_it_showed():
    first, second = call("demo.item.create", {"name": "Uno"}, "c1"), call("demo.item.create", {"name": "Dos"}, "c2")
    plan = turn(first, second)
    waiting, after = plan["pending"]
    assert {key: waiting[key] for key in first} == first and waiting["shown"]
    assert after == {**second, "shown": ""}

    ran = yes_to(plan)

    assert [row["outcome"] for row in ran["executed"]] == ["ok"]
    assert said(ran) == [("name", "Dos")]
    assert [p["call_id"] for p in ran["pending"]] == ["c2"] and ran["pending"][0]["shown"] not in ("", waiting["shown"])


# ── What a dangerous write will do (its preview) ──────────────────────────────────────────────────────────────────────


class TillIn(Schema):
    id: str


class TillOut(Schema):
    expected_cents: int = Field(json_schema_extra={"money": True})


#: What the till holds now: a sale more changes what closing it will count.
TILL = {"expected_cents": 4200}
CLOSED: list[str] = []
TILL_PREVIEW = Operation(
    name="demo.item.till_preview",
    kind="query",
    permission="demo.view",
    input=TillIn,
    output=TillOut,
    expose_api=False,
    ai={"description": "What closing a demo till would count."},
    fn=lambda ctx, data: dict(TILL),
)
TILL_CLOSE = Operation(
    name="demo.item.till_close",
    kind="command",
    permission="demo.manage",
    input=TillIn,
    output=TillOut,
    expose_api=False,
    ai={
        "description": "Closes a demo till.",
        "risk": "high",
        "preview": {"operation": TILL_PREVIEW.name, "fields": ["expected_cents"]},
    },
    fn=lambda ctx, data: CLOSED.append(data.id) or dict(TILL),
)


@pytest.fixture
def till(monkeypatch):
    monkeypatch.setitem(registry, TILL_PREVIEW.name, TILL_PREVIEW)
    monkeypatch.setitem(registry, TILL_CLOSE.name, TILL_CLOSE)
    monkeypatch.setitem(TILL, "expected_cents", 4200)
    CLOSED.clear()
    return TILL_CLOSE


def test_what_a_dangerous_write_said_it_will_do_is_held_too(till):
    """Its preview said 42,00 €; a sale more before the yes (45,00 €): nothing is closed and the new card says it."""
    plan = turn(call(till.name, {"id": "t1"}))
    assert [(field["name"], field["value"]) for field in plan["confirm"]["preview"]] == [("expected_cents", 4200)]
    TILL["expected_cents"] = 4500

    again = yes_to(plan)

    assert again["executed"] == [] and CLOSED == []
    assert [(field["name"], field["value"]) for field in again["confirm"]["preview"]] == [("expected_cents", 4500)]
    done = yes_to(again)
    assert [row["outcome"] for row in done["executed"]] == ["ok"] and CLOSED == ["t1"]


# ── Each way a card finds its record, on its own ──────────────────────────────────────────────────────────────────────


class CalledIn(Schema):
    """An item by its name, which the card reads to say it (a mark by name, as an image by its file's name)."""

    called: str = Field(json_schema_extra=names("demo.item.detail", by="called"))


class SaidIn(Schema):
    """An item by its name, which the card says as sent: only the write's check finds it."""

    called: str


class TouchedOut(Schema):
    touched: str


TOUCHED: list[str] = []


def by_its_name(name: str, input: type[Schema], **ai) -> Operation:
    return Operation(
        name=name,
        kind="command",
        permission="demo.manage",
        input=input,
        output=TouchedOut,
        expose_api=False,
        ai={"description": "Touches a demo item said by its name.", **ai},
        fn=lambda ctx, data: TOUCHED.append(data.called) or {"touched": data.called},
    )


#: A card that reads the item by the name said, with no check; a card that says the name as sent, with its check.
READ_BY_ITS_MARK = by_its_name("demo.item.touch_named", CalledIn)
FOUND_BY_ITS_CHECK = by_its_name("demo.item.touch_checked", SaidIn, check="demo.item.detail")


@pytest.fixture(params=[READ_BY_ITS_MARK, FOUND_BY_ITS_CHECK], ids=["its-mark", "its-check"])
def touch(request, monkeypatch):
    monkeypatch.setitem(registry, request.param.name, request.param)
    TOUCHED.clear()
    return request.param


def test_the_record_a_card_found_by_its_mark_or_by_its_check_is_held_alone(touch):
    """Each of the two ways on its own: «Mesa 4» renamed «Barra» and another «Mesa 4» created before the yes, the
    words on the card the same — another record —: nothing runs; with nothing changed, the yes runs."""
    first = Item.objects.create(name="Mesa 4")
    plan = turn(call(touch.name, {"called": "mesa 4"}))
    assert said(plan) == [("called", "Mesa 4" if touch is READ_BY_ITS_MARK else "mesa 4")]
    Item.objects.filter(pk=first.pk).update(name="Barra")
    Item.objects.create(name="Mesa 4")

    again = yes_to(plan)

    assert (again["executed"], TOUCHED) == ([], [])
    assert [row["outcome"] for row in yes_to(again)["executed"]] == ["ok"] and TOUCHED == ["mesa 4"]


# ── Each business on its own ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_card_drawn_in_one_business_is_no_yes_in_another(hub_a, hub_b):
    """Two businesses with a database each, as production: the same words name another record in B, and the card A
    drew is no yes there."""

    def turn_in(hub, *calls, decision=None) -> dict:
        as_hub = OperationContext(scope=Scope("host", hub.slug), actor="ana", permissions=MANAGER, language="es")
        with context.use_hub(hub):
            return turn_as(as_hub, *calls, decision=decision)

    def kept_in(hub) -> set[str]:
        with context.use_hub(hub):
            return set(Item.objects.values_list("name", flat=True))

    for hub in (hub_a, hub_b):
        with context.use_hub(hub):
            Item.objects.create(name="Mesa 4")
    plan = turn_in(hub_a, call("demo.item.delete", {"called": "mesa"}))
    yes = {"call_id": "c1", "accepted": True, "typed": plan["confirm"]["confirm_word"]}

    in_b = turn_in(hub_b, *plan["pending"], decision=yes)

    assert (in_b["executed"], [(f["name"], f["value"]) for f in in_b["confirm"]["fields"]]) == ([], [("called", "Mesa 4")])
    assert (kept_in(hub_a), kept_in(hub_b)) == ({"Mesa 4"}, {"Mesa 4"})
    assert [row["outcome"] for row in turn_in(hub_a, *plan["pending"], decision=yes)["executed"]] == ["ok"]
    assert (kept_in(hub_a), kept_in(hub_b)) == (set(), {"Mesa 4"})

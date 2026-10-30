"""The factory automations the WhatsApp inbox brings to Automatizaciones (WHATSAPP_INBOX-F21, F23, F24, F25, F26; FLOW-F33):
data only, offered whole, asking for exactly what its steps use and nothing that needs a person in front, but for
cancelling a reservation in a step that asks first (FLOW-F28)."""

import copy

import pytest
from django.utils import translation

from apps.flow import document, queries, recipes
from apps.flow.tests.test_recipes import without
from apps.whatsapp_inbox import recipes as inbox_recipes
from apps.whatsapp_inbox.recipes import RECIPES
from apps.whatsapp_inbox.tests.conftest import ctx_for, run

pytestmark = pytest.mark.django_db

REF = "whatsapp_inbox/appointment_confirmed"
RESERVATION_REF = "whatsapp_inbox/reservation_confirmed"


def offered() -> dict[str, recipes.Recipe]:
    return {recipe.ref: recipe for recipe in recipes.shelf()[0]}


def test_the_confirmed_appointment_notice_is_offered_whole():
    assert REF in offered()
    assert not [item for item in recipes.shelf()[1] if item.ref.startswith("whatsapp_inbox/")]


def test_it_starts_when_an_appointment_is_confirmed_and_writes_only_through_the_narrow_send():
    recipe = offered()[REF]
    built = recipes.build(recipe, "en")
    assert built["trigger"] == {"kind": "event", "event": "appointment.appointment.confirmed"}
    operations = [step["operation"] for step in built["steps"] if step["kind"] in ("command", "query")]
    assert operations[-1] == "whatsapp_inbox.message.notify"
    assert "whatsapp_inbox.message.send" not in operations
    assert recipes.grants(recipe) == document.required_grants(built["steps"])
    catalog = queries.catalog_operations()
    assert all(name in catalog for name in recipes.grants(recipe))


def test_it_stops_without_a_phone_or_a_conversation_before_it_sends():
    steps = recipes.build(offered()[REF], "en")["steps"]
    kinds = [step["kind"] for step in steps]
    send = kinds.index("command")
    guards = [step["when"] for step in steps[:send] if step["kind"] == "condition"]
    assert any("steps.s1.phone" in guard for guard in guards)
    assert any(path.endswith(".conversation_id") for guard in guards for path in guard)


def test_the_notice_says_day_time_service_and_professional_in_the_business_s_language():
    recipe = offered()[REF]
    notify = recipes.build(recipe, "es")["steps"][-1]["params"]
    assert notify["text"].startswith("¡Confirmada! Te esperamos el {{")
    assert notify["template"]["name"] == "appointment_confirmed"
    assert len(notify["template"]["variables"]) == 4
    with translation.override("en"):
        assert recipes.words(recipe, "en")["name"]


# ── WHATSAPP_INBOX-F26 / RESERVATION-F19: the reservation's companion ─────────────────────────────────


def test_the_confirmed_reservation_notice_is_offered_whole():
    assert RESERVATION_REF in offered()


def test_without_reservations_the_reservation_notice_is_set_aside_naming_the_app(monkeypatch):
    without(monkeypatch, "reservation")
    offered_now, set_aside = recipes.shelf()
    assert RESERVATION_REF not in {recipe.ref for recipe in offered_now}
    assert REF in {recipe.ref for recipe in offered_now}  # the appointment's notice does not need Reservations
    assert [(item.code, item.apps) for item in set_aside if item.ref == RESERVATION_REF] == [
        ("flow.recipe_needs_apps", ("reservation",))
    ]


def test_it_starts_only_when_a_reservation_turns_confirmed_and_writes_only_through_the_narrow_send():
    recipe = offered()[RESERVATION_REF]
    built = recipes.build(recipe, "en")
    assert built["trigger"] == {
        "kind": "event",
        "event": "reservation.reservation.status_changed",
        "filter": {"input.status": {"eq": "confirmed"}},
    }
    for status, starts in [("confirmed", True), ("seated", False), ("cancelled", False), ("pending", False),
                           ("no_show", False), ("completed", False), ("deleted", False)]:
        payload = {"input": {"status": status, "previous_status": "pending"}, "steps": {}}
        assert document.holds(built["trigger"]["filter"], payload) is starts, status
    operations = [step["operation"] for step in built["steps"] if step["kind"] in ("command", "query")]
    assert operations[0] == "reservation.reservation.get"
    assert operations[-1] == "whatsapp_inbox.message.notify"
    assert "whatsapp_inbox.message.send" not in operations
    assert recipes.grants(recipe) == document.required_grants(built["steps"])
    catalog = queries.catalog_operations()
    assert all(name in catalog for name in recipes.grants(recipe))


def test_the_reservation_notice_stops_without_a_phone_or_a_conversation_before_it_sends():
    steps = recipes.build(offered()[RESERVATION_REF], "en")["steps"]
    kinds = [step["kind"] for step in steps]
    send = kinds.index("command")
    guards = [step["when"] for step in steps[:send] if step["kind"] == "condition"]
    assert {"steps.s1.guest_phone": {"exists": True, "neq": ""}} in guards
    assert any(path.endswith(".conversation_id") for guard in guards for path in guard)
    by_phone = next(step for step in steps if step.get("operation") == "whatsapp_inbox.conversation.by_phone")
    assert by_phone["params"] == {"phone": "steps.s1.guest_phone"}
    assert steps[send]["params"]["phone"] == "steps.s3.phone"


def test_the_reservation_notice_says_day_time_and_guests_in_the_business_s_language():
    recipe = offered()[RESERVATION_REF]
    spanish = recipes.build(recipe, "es")["steps"][-1]["params"]
    english = recipes.build(recipe, "en")["steps"][-1]["params"]
    for notify in (spanish, english):
        for field in ("date_label", "time_label", "party_size"):
            assert "{{steps.s1.%s}}" % field in notify["text"], field
    assert spanish["text"].startswith("¡Confirmada! Te esperamos el {{")
    assert english["text"].startswith("Confirmed! We are expecting you on {{")
    assert spanish["template"] == english["template"] == {
        "name": "reservation_confirmed",
        "variables": ["{{steps.s1.date_label}}", "{{steps.s1.time_label}}", "{{steps.s1.party_size}}"],
    }
    words = recipes.words(recipe, "es")
    assert words["name"] == "Avisar por WhatsApp al cliente cuando se confirma su reserva"
    assert "«reservation_confirmed»" in words["description"]
    assert set(recipes.reasons(recipe, "es")) == set(recipes.grants(recipe))
    assert all(reason and reason != recipes.reasons(recipe, "en")[name]
               for name, reason in recipes.reasons(recipe, "es").items())


def test_every_recipe_has_an_id_and_its_words():
    assert [recipe["id"] for recipe in RECIPES] == [
        "appointment_confirmed",
        "reservation_confirmed",
        "reservation_from_whatsapp",
    ]
    for recipe in RECIPES:
        assert {"name", "summary", "description", "trigger", "steps", "grants"} <= set(recipe)


def test_the_gallery_offers_no_answer_that_books_appointments():
    """WHATSAPP_INBOX-F14 stays partial: after «Approve», Citas refuses the booking of an automation (its step runs with
    «only mine»), so no answer that books appointments is offered, here or in Automatizaciones' gallery."""
    assert sorted(ref for ref in offered() if ref.startswith("whatsapp_inbox/")) == [
        "whatsapp_inbox/appointment_confirmed",
        "whatsapp_inbox/reservation_confirmed",
        "whatsapp_inbox/reservation_from_whatsapp",
    ]


# ── WHATSAPP_INBOX-F20, F24, F25: the answer that reads what the customer writes ─────────────────────────────

TABLE_REF = "whatsapp_inbox/reservation_from_whatsapp"
ANSWERS = (TABLE_REF,)
#: What each answer's assistant may use, and nothing more: free tables and the reservation's own changes, its
#: cancellation included (F25). A read that names other people (the reservations book, a customer list) never: what
#: it reads goes out to whoever writes.
TOOLS = {
    TABLE_REF: [
        "reservation.availability.day",
        "reservation.availability.tables",
        "reservation.reservation.create",
        "reservation.reservation.update",
        "reservation.reservation.cancel",
        "reservation.waitlist.create",
    ],
}
#: What needs a person in front that each answer is granted all the same, only because its step asks first (FLOW-F28).
ASKED_FIRST = {TABLE_REF: {"reservation.reservation.cancel"}}
#: Reads that tell about other people, which an answer to a stranger may never be granted.
OTHER_PEOPLE = {
    "appointment.availability.check",
    "appointment.appointment.list",
    "appointment.appointment.list_for_customer",
    "appointment.agenda.lanes",
    "customer.customer.list",
    "customer.customer.detail",
    "reservation.reservation.list",
    "whatsapp_inbox.conversation.list",
    "whatsapp_inbox.message.list",
}


def assistant_step(ref: str, language: str = "en") -> dict:
    [found] = [step for step in recipes.build(offered()[ref], language)["steps"] if step["kind"] == "assistant"]
    return found


@pytest.mark.parametrize("ref", ANSWERS)
def test_the_booking_answers_are_offered_whole(ref):
    assert ref in offered()


@pytest.mark.parametrize("ref", ANSWERS)
def test_an_answer_starts_on_each_live_message_of_the_customer_and_never_on_the_business_s_or_history(ref):
    trigger = recipes.build(offered()[ref], "en")["trigger"]
    assert (trigger["kind"], trigger["event"]) == ("event", "whatsapp_inbox.message.received")
    for direction, source, starts in [
        ("inbound", "live", True),
        ("outbound", "live", False),  # the echo of what the owner wrote from her phone
        ("inbound", "history", False),  # the old chats brought by connecting the number
    ]:
        payload = {"input": {"direction": direction, "source": source}, "steps": {}}
        assert document.holds(trigger["filter"], payload) is starts, (direction, source)


@pytest.mark.parametrize("ref", ANSWERS)
def test_an_answer_asks_the_assistant_ask_me_first_with_only_what_it_needs(ref):
    step = assistant_step(ref)
    assert step["mode"] == "ask"
    assert step["tools"] == TOOLS[ref]
    assert recipes.grants(offered()[ref]) == document.required_grants(recipes.build(offered()[ref], "en")["steps"])
    assert all(name in queries.ask_first_catalog() for name in recipes.grants(offered()[ref]))
    catalog = queries.catalog_operations()
    assert {name for name in recipes.grants(offered()[ref]) if name not in catalog} == ASKED_FIRST[ref]


def test_the_table_answer_that_did_it_on_its_own_would_not_be_offered(monkeypatch):
    """A cancellation needs someone's yes (FLOW-F28): with the step on «Do it on its own», the answer is set aside."""
    declared = copy.deepcopy(RECIPES)
    [table] = [recipe for recipe in declared if recipe["id"] == "reservation_from_whatsapp"]
    [step] = [step for step in table["steps"] if step["kind"] == "assistant"]
    step["mode"] = "auto"
    monkeypatch.setattr(inbox_recipes, "RECIPES", declared)
    offered_now, set_aside = recipes.shelf()
    assert TABLE_REF not in {recipe.ref for recipe in offered_now}
    assert [(item.code, item.apps) for item in set_aside if item.ref == TABLE_REF] == [("flow.recipe_invalid", ())]


#: Whose card a change of a reservation goes on: the card of the number that writes, found (``s6``) or just made
#: (``s7``), so Reservas refuses any reservation that is not theirs (``reservation.customer_mismatch``).
THEIR_CARD = "{{steps.s6.id}}{{steps.s7.id}}"


def test_the_table_answer_cancels_only_their_latest_reservation_and_on_their_behalf():
    """F25: ``on_behalf_of`` is fixed by the step (FLOW-F38), which the assistant never sees nor can change: the prompt
    does not ask it for it, and still names the reservation it may cancel, the one read before by their number."""
    for language in ("en", "es"):
        step = assistant_step(TABLE_REF, language)
        assert step["pinned"] == {
            "reservation.reservation.create": {"customer_id": THEIR_CARD},
            "reservation.reservation.update": {"on_behalf_of": THEIR_CARD},
            "reservation.reservation.cancel": {"on_behalf_of": THEIR_CARD},
            "reservation.waitlist.create": {"customer_id": THEIR_CARD},
        }, language
        assert "on_behalf_of" not in step["prompt"], language
        assert THEIR_CARD not in step["prompt"], language  # whose card is never the assistant's to say
        [line] = [line for line in step["prompt"].splitlines() if "{{steps.s9.id}}" in line and line.startswith("- ")]
        assert THEIR_CARD not in line, language


def test_who_has_the_table_answer_on_is_offered_the_version_that_cancels(monkeypatch):
    """WHATSAPP_INBOX-F18: an answer turned on before cancelling was offered is «New version», and updating it gives
    its assistant the cancellation, granted."""
    older = copy.deepcopy(RECIPES)
    [table] = [recipe for recipe in older if recipe["id"] == "reservation_from_whatsapp"]
    [step] = [step for step in table["steps"] if step["kind"] == "assistant"]
    step["tools"].remove("reservation.reservation.cancel")
    del step["pinned"]  # that version fixed no data either
    del table["grants"]["reservation.reservation.cancel"]
    with monkeypatch.context() as patch:
        patch.setattr(inbox_recipes, "RECIPES", older)
        run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))

    [row] = [row for row in run("flow.recipe.list", {}, ctx_for("hub_owner")).recipes if row.ref == TABLE_REF]
    assert row.installed.outdated is True
    flow = run("flow.recipe.restore", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    [assistant] = [step for step in flow.steps if step["kind"] == "assistant"]
    assert "reservation.reservation.cancel" in assistant["tools"]
    assert "reservation.reservation.cancel" in flow.grants


def test_who_has_the_table_answer_on_without_its_card_fixed_is_offered_the_version_that_fixes_it(monkeypatch):
    """WHATSAPP_INBOX-F18, FLOW-F35: an answer turned on when its assistant was only asked for whose card (no
    ``pinned``) is «New version», and updating it fixes the card on its changes and cancellations."""
    older = copy.deepcopy(RECIPES)
    [table] = [recipe for recipe in older if recipe["id"] == "reservation_from_whatsapp"]
    [step] = [step for step in table["steps"] if step["kind"] == "assistant"]
    del step["pinned"]
    with monkeypatch.context() as patch:
        patch.setattr(inbox_recipes, "RECIPES", older)
        run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))

    [row] = [row for row in run("flow.recipe.list", {}, ctx_for("hub_owner")).recipes if row.ref == TABLE_REF]
    assert row.installed.outdated is True
    flow = run("flow.recipe.restore", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    [assistant] = [step for step in flow.steps if step["kind"] == "assistant"]
    assert assistant["pinned"]["reservation.reservation.cancel"] == {"on_behalf_of": THEIR_CARD}
    assert assistant["pinned"]["reservation.reservation.update"] == {"on_behalf_of": THEIR_CARD}
    assert assistant["pinned"]["reservation.reservation.create"] == {"customer_id": THEIR_CARD}
    assert assistant["pinned"]["reservation.waitlist.create"] == {"customer_id": THEIR_CARD}


#: The assistant's step of each answer, and the reads pinned to the customer who writes that come before it.
ASSISTANT = {TABLE_REF: "s10"}
PINNED = {
    TABLE_REF: {
        "customer.customer.by_phone": {"phone": "steps.s1.phone"},
        "reservation.reservation.list": {"guest_phone": "steps.s1.phone", "sort": "-starts_at", "limit": 1},
    },
}


@pytest.mark.parametrize("ref", ANSWERS)
def test_a_read_that_names_people_is_never_the_assistant_s_and_only_ever_about_who_writes(ref):
    assert not OTHER_PEOPLE & set(assistant_step(ref)["tools"])
    steps = recipes.build(offered()[ref], "en")["steps"]
    pinned = {step["operation"]: step["params"] for step in steps if step.get("operation") in PINNED[ref]}
    assert pinned == PINNED[ref]


@pytest.mark.parametrize("ref", ANSWERS)
def test_an_answer_tells_the_assistant_what_she_wrote_and_her_number(ref):
    prompt = assistant_step(ref)["prompt"]
    for path in ("steps.s1.phone", "steps.s1.display_name"):
        assert "{{%s}}" % path in prompt, path
    # Her words alone on their lines, between two of their own: what she wrote is never read as an instruction.
    assert "\n———\n{{steps.s1.body}}\n———\n" in prompt
    assert "«whatsapp»" in prompt


@pytest.mark.parametrize("ref", ANSWERS)
def test_an_answer_books_only_on_her_card(ref):
    """Her card, found by her number or just made, is fixed on a booking and on a place on the waiting list."""
    pinned = assistant_step(ref)["pinned"]
    for tool in ("reservation.reservation.create", "reservation.waitlist.create"):
        assert pinned[tool] == {"customer_id": "{{steps.s6.id}}{{steps.s7.id}}"}, tool


@pytest.mark.parametrize("ref", ANSWERS)
def test_an_answer_thanks_first_then_says_what_the_assistant_answered_or_says_sorry(ref):
    steps = recipes.build(offered()[ref], "en")["steps"]
    by_id = {step["id"]: step for step in steps}
    order = [step["id"] for step in steps]
    assistant = by_id[ASSISTANT[ref]]
    sends = [step for step in steps if step.get("operation") == "whatsapp_inbox.message.notify"]
    thanks, reply, sorry_failed, sorry_silent = sends
    assert order.index(thanks["id"]) < order.index(assistant["id"]) < order.index(reply["id"])
    assert all(send["params"]["phone"] == "steps.s1.phone" for send in sends)
    assert sorry_failed["params"]["text"] == sorry_silent["params"]["text"]
    assert assistant["on_error"] == "continue"
    a = assistant["id"]
    assert reply["params"]["text"] == "{{steps.%s.text}}" % a
    assert reply["run_if"] == {"steps.%s.text" % a: {"exists": True, "neq": ""}}
    assert sorry_failed["run_if"] == {"steps.%s.failed" % a: {"eq": True}}
    assert sorry_silent["run_if"] == {"steps.%s.text" % a: {"eq": ""}}
    for sorry in (sorry_failed, sorry_silent):
        mark = by_id[order[order.index(sorry["id"]) + 1]]
        assert (mark["operation"], mark["params"], mark["run_if"]) == (
            "whatsapp_inbox.conversation.flag",
            {"id": "steps.s1.conversation_id"},
            sorry["run_if"],
        )
    for data, said in [({a: {"text": "Booked"}}, [reply]), ({a: {"failed": True}}, [sorry_failed]),
                       ({a: {"text": ""}}, [sorry_silent])]:
        payload = {"input": {}, "steps": data}
        assert [send for send in sends[1:] if document.holds(send["run_if"], payload)] == said


@pytest.mark.parametrize("ref", ANSWERS)
def test_an_answer_stops_on_a_message_with_no_text_and_marks_her_when_nothing_can_be_sent(ref):
    steps = recipes.build(offered()[ref], "en")["steps"]
    assert steps[1] == {"id": "s2", "kind": "condition", "when": {"steps.s1.body": {"exists": True, "neq": ""}}}
    assert (steps[2]["operation"], steps[2]["run_if"]) == (
        "whatsapp_inbox.conversation.flag",
        {"steps.s1.can_send": {"eq": False}},
    )
    assert steps[3] == {"id": "s4", "kind": "condition", "when": {"steps.s1.can_send": {"eq": True}}}
    assert steps[4]["operation"] == "whatsapp_inbox.message.notify"  # the thanks, only once it can go


def test_the_table_answer_thanks_and_says_sorry_in_the_business_s_language():
    steps = recipes.build(offered()[TABLE_REF], "es")["steps"]
    thanks, _reply, sorry, _again = [step for step in steps if step.get("operation") == "whatsapp_inbox.message.notify"]
    assert thanks["params"]["text"] == "¡Gracias por escribirnos! Miro el libro de reservas y te contesto ahora mismo."
    assert sorry["params"]["text"] == (
        "Perdona, ahora mismo no puedo mirar las reservas. Alguien del equipo te contestará por aquí en cuanto pueda."
    )


@pytest.mark.parametrize("ref", ANSWERS)
def test_a_customer_with_no_card_gets_one_from_whatsapp_and_one_with_it_does_not(ref):
    by_id = {step["id"]: step for step in recipes.build(offered()[ref], "en")["steps"]}
    made = by_id["s7"]
    assert made["operation"] == "customer.customer.create"
    assert made["params"] == {"name": "steps.s1.display_name", "phone": "steps.s1.phone", "source": "whatsapp"}
    assert made["run_if"] == {"steps.s6.found": {"eq": False}}


@pytest.mark.parametrize(("ref", "app"), [(TABLE_REF, "reservation"), (TABLE_REF, "customer")])
def test_without_its_app_an_answer_is_set_aside_naming_it(monkeypatch, ref, app):
    without(monkeypatch, app)
    offered_now, set_aside = recipes.shelf()
    assert ref not in {recipe.ref for recipe in offered_now}
    assert [(item.code, item.apps) for item in set_aside if item.ref == ref] == [("flow.recipe_needs_apps", (app,))]


@pytest.mark.parametrize("ref", ANSWERS)
def test_each_permission_says_why_in_both_languages(ref):
    recipe = offered()[ref]
    assert set(recipes.reasons(recipe, "es")) == set(recipes.grants(recipe))
    assert all(reason and reason != recipes.reasons(recipe, "en")[name]
               for name, reason in recipes.reasons(recipe, "es").items())
    assert recipes.words(recipe, "es")["name"] != recipes.words(recipe, "en")["name"]

"""The factory automations the WhatsApp inbox brings to Automatizaciones (WHATSAPP_INBOX-F21, F23, F24, F26; FLOW-F33):
data only, offered whole, asking for exactly what its steps use and nothing that needs a person in front."""

import pytest
from django.utils import translation

from apps.flow import document, queries, recipes
from apps.flow.tests.test_recipes import without
from apps.whatsapp_inbox.recipes import RECIPES

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
        "appointment_from_whatsapp",
        "reservation_from_whatsapp",
    ]
    for recipe in RECIPES:
        assert {"name", "summary", "description", "trigger", "steps", "grants"} <= set(recipe)


# ── WHATSAPP_INBOX-F21, F22, F24, F25: the answers that read what the customer writes ─────────────────────

BOOKING_REF = "whatsapp_inbox/appointment_from_whatsapp"
TABLE_REF = "whatsapp_inbox/reservation_from_whatsapp"
ANSWERS = (BOOKING_REF, TABLE_REF)
#: What each answer's assistant may use, and nothing more: free times and the booking's own changes. A read that
#: names other people (a diary, a customer list, the people a time clashes with) never: what it reads goes out to
#: whoever writes.
TOOLS = {
    BOOKING_REF: ["appointment.availability.slots", "appointment.appointment.create", "appointment.appointment.reschedule"],
    TABLE_REF: [
        "reservation.availability.day",
        "reservation.availability.tables",
        "reservation.reservation.create",
        "reservation.reservation.update",
        "reservation.waitlist.create",
    ],
}
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
    catalog = queries.catalog_operations()
    assert all(name in catalog for name in recipes.grants(offered()[ref]))


#: The assistant's step of each answer, and the reads pinned to the customer who writes that come before it.
ASSISTANT = {BOOKING_REF: "s10", TABLE_REF: "s10"}
PINNED = {
    BOOKING_REF: {
        "customer.customer.by_phone": {"phone": "steps.s1.phone"},
        "appointment.appointment.list_for_customer": {"customer_id": "steps.s6.id", "limit": 1},
    },
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
    for path in ("steps.s1.body", "steps.s1.phone", "steps.s1.display_name"):
        assert "{{%s}}" % path in prompt, path
    assert "«whatsapp»" in prompt


@pytest.mark.parametrize("ref", ANSWERS)
def test_an_answer_books_only_on_her_card(ref):
    assert "{{steps.s6.id}}{{steps.s7.id}}" in assistant_step(ref)["prompt"]  # found by her number, or just made


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


def test_the_appointment_answer_thanks_and_says_sorry_in_the_business_s_language():
    steps = recipes.build(offered()[BOOKING_REF], "es")["steps"]
    thanks, _reply, sorry, _again = [step for step in steps if step.get("operation") == "whatsapp_inbox.message.notify"]
    assert thanks["params"]["text"] == "¡Gracias por escribirnos! Miro la agenda y te contesto ahora mismo."
    assert sorry["params"]["text"] == (
        "Perdona, ahora mismo no puedo mirar la agenda. Alguien del equipo te contestará por aquí en cuanto pueda."
    )


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


@pytest.mark.parametrize(("ref", "app"), [(BOOKING_REF, "appointment"), (TABLE_REF, "reservation")])
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

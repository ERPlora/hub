"""The factory automations the WhatsApp inbox brings to Automatizaciones (WHATSAPP_INBOX-F23, F26; FLOW-F33): data
only, offered whole, asking for exactly what its steps use and nothing that needs a person in front."""

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
    assert [recipe["id"] for recipe in RECIPES] == ["appointment_confirmed", "reservation_confirmed"]
    for recipe in RECIPES:
        assert {"name", "summary", "description", "trigger", "steps", "grants"} <= set(recipe)

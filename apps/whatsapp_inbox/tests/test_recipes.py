"""The factory automations the WhatsApp inbox brings to Automatizaciones (WHATSAPP_INBOX-F23; FLOW-F33): data only,
offered whole, asking for exactly what its steps use and nothing that needs a person in front."""

import pytest
from django.utils import translation

from apps.flow import document, queries, recipes
from apps.whatsapp_inbox.recipes import RECIPES

pytestmark = pytest.mark.django_db

REF = "whatsapp_inbox/appointment_confirmed"


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


def test_every_recipe_has_an_id_and_its_words():
    assert [recipe["id"] for recipe in RECIPES] == ["appointment_confirmed"]
    for recipe in RECIPES:
        assert {"name", "summary", "description", "trigger", "steps", "grants"} <= set(recipe)

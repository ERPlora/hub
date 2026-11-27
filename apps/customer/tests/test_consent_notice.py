"""A marketing consent is given with the business's own sentence and its version, whoever writes it down
(CUSTOMER-F14, hub#2671): the card screen shows it to be read out, the assistant's card shows the same one before it
runs, and both store it word for word as the proof. Nobody types it: a caller cannot send other words."""

import json

import pytest
from django.utils import translation
from live.operations import get

from apps.customer.models import Activity, Consent
from base import assistant
from base.tests.test_assistant_yes_for_its_card import yes_to_its_card

from .conftest import HOST, HUB_DB, card, ctx_for, make_user

__all__ = ["make_user"]

pytestmark = HUB_DB

SENTENCE = {
    "en": "I want to receive offers and news from this business through this channel. I can unsubscribe whenever I want.",
    "es": "Quiero recibir ofertas y novedades de este negocio por este canal. Puedo darme de baja cuando quiera.",
}
READ_OUT = {"en": "Read it out loud", "es": "Léelo en voz alta"}
VERSION = "counter-v1"


def the_screens_sentence(customer_id, language: str) -> str:
    """The words the card screen shows to read out, as the card's read answers them in ``language``: a read runs in
    its reader's language, as the live stream and the API run it."""
    op = get("customer.customer.detail")
    with translation.override(language):
        detail = op(ctx_for(language=language), op.input.model_validate({"id": customer_id}))
    return detail.consent_notice


@pytest.fixture
def employee(client, make_user):
    client.force_login(make_user("ana", role="hub_employee"))
    return client


def given_from_the_screen(employee, customer_id, language: str, **sent):
    """«They said yes» on the card screen: what the panel sends, in the person's language."""
    body = {"customer_id": str(customer_id), "channel": "whatsapp", "purpose": "marketing", "source": "counter", **sent}
    answer = employee.post(
        "/api/customer/consents/grant",
        json.dumps(body),
        content_type="application/json",
        HTTP_HOST=HOST,
        HTTP_ACCEPT_LANGUAGE=language,
    )
    assert answer.status_code == 201, answer.content
    return Consent.objects.get(id=answer.json()["id"])


def given_by_the_assistant(customer_name: str, language: str) -> Consent:
    """An employee tells the assistant the customer said yes and runs its card."""
    done = yes_to_its_card(
        ctx_for("hub_employee", language=language),
        "customer.consent.grant",
        {"customer": customer_name, "channel": "whatsapp"},
    )
    assert [row["outcome"] for row in done["executed"]] == ["ok"], done["executed"]
    return Consent.objects.get()


def proof(fact: Consent) -> tuple:
    said = Activity.objects.get(related_id=str(fact.id))
    return fact.notice_text, fact.notice_version, said.text, said.data["notice_version"]


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_card_screen_shows_the_businesss_sentence_in_the_readers_language(language):
    lucia = card("Lucía Gómez", phone="+34611222333")
    assert the_screens_sentence(lucia.id, language) == SENTENCE[language]


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_assistant_records_a_yes_with_the_sentence_and_version_of_the_card_screen(language):
    lucia = card("Lucía Gómez", phone="+34611222333")
    fact = given_by_the_assistant("Lucía Gómez", language)
    words = the_screens_sentence(lucia.id, language)
    assert (fact.customer_id, fact.channel, fact.state) == (lucia.id, "whatsapp", "granted")
    assert proof(fact) == (words, VERSION, words, VERSION)


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_assistants_card_shows_the_sentence_to_read_out_before_it_runs(language):
    card("Lucía Gómez", phone="+34611222333")
    arguments = {"customer": "Lucía Gómez", "channel": "whatsapp", "purpose": "marketing", "source": "counter"}
    drawn = assistant.cards.card(get("customer.consent.grant"), arguments, language, ctx_for(language=language))
    lines = [(field["label"], field["value"]) for field in drawn["fields"] if field["kind"] != "empty"]
    # A normal write says its first three data in one line: the customer, the channel and the words.
    assert lines[2] == (READ_OUT[language], SENTENCE[language])


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_proof_is_the_same_given_on_the_card_screen_or_through_the_assistant(employee, language):
    lucia = card("Lucía Gómez", phone="+34611222333")
    on_screen = proof(given_from_the_screen(employee, lucia.id, language))
    Consent.objects.all().delete()
    Activity.objects.all().delete()
    assert proof(given_by_the_assistant("Lucía Gómez", language)) == on_screen == (
        SENTENCE[language], VERSION, SENTENCE[language], VERSION
    )


def test_a_caller_cannot_store_other_words_or_another_version(employee):
    lucia = card("Lucía Gómez", phone="+34611222333")
    fact = given_from_the_screen(employee, lucia.id, "es", notice_text="Acepto lo que sea", notice_version="QA-1")
    assert proof(fact) == (SENTENCE["es"], VERSION, SENTENCE["es"], VERSION)

"""The language a person chooses for themselves (BASE-F64) is the one the next request speaks, whichever door ran
``base.profile.preferences_set``: «My profile»'s selector, the assistant's card or the API. The answer of the request
that ran it leaves Django's language cookie, the one ``LocaleMiddleware`` reads; nothing else does.
"""

import json

import pytest
from django.conf import settings
from live.context import OperationContext
from live.operations import get

from base.models import Hub
from base.permissions import VIEW_HOME
from base.services import assistant as assistant_service
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.fake_gateway import gateway
from base.tests.test_api_assistant import HOST, frames, post

__all__ = ["gateway", "in_business_a"]

pytestmark = HUB_DB

COOKIE = settings.LANGUAGE_COOKIE_NAME
SET = "base__profile__preferences_set"
ASKED = {
    "en": "Switch the app back to English for me, just my own profile.",
    "es": "Ponme el programa en español, pero solo para mí.",
}


def preferences(language: str) -> str:
    """What the assistant sends when only the language is asked of it."""
    return json.dumps({"language": language})


def asked_for(language: str, *, said: str = "") -> dict:
    arguments = preferences(language)
    asked = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": SET, "arguments": arguments}}
    ]}
    question = {"role": "user", "content": said or ASKED[language or "es"]}
    return {"messages": [question, asked], "pending": [{"call_id": "c1", "name": SET, "arguments": arguments}]}


def answered(client, body: dict, *, accepted: bool = True):
    """The person's answer to the card ``body`` draws, given back with what the card showed, as the panel does."""
    drawn = frames(post(client, "/assistant/turn", body))
    assert [frame["type"] for frame in drawn] == ["confirm", "done"], drawn
    return post(client, "/assistant/turn", {**body, "pending": drawn[-1]["pending"], "decision": {"call_id": "c1", "accepted": accepted}})


def session_language(client) -> str:
    response = client.get("/api/me", **HOST)
    assert response.status_code == 200, response.content
    return response.json()["language"]


@pytest.fixture
def ana(client, make_user):
    user = make_user("ana", host=A.key, role="hub_manager")
    client.force_login(user)
    return user


@pytest.mark.parametrize("before, chosen", [("es", "en"), ("en", "es")])
def test_the_assistant_s_yes_switches_the_language_the_next_request_speaks(client, ana, gateway, before, chosen):
    client.cookies[COOKIE] = before
    assert session_language(client) == before
    gateway.turn({"type": "text_delta", "text": "Hecho."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    response = answered(client, asked_for(chosen))
    ran = frames(response)
    assert (ran[0]["type"], ran[0]["name"], ran[0]["outcome"]) == ("executed", "base.profile.preferences_set", "ok")
    assert response.cookies[COOKIE].value == chosen
    assert session_language(client) == chosen


def test_back_to_the_business_s_language_the_assistant_leaves_the_business_s(client, ana, gateway):
    business = Hub.objects.get(slug=A.key).language or settings.LANGUAGE_CODE
    other = "en" if business == "es" else "es"
    client.cookies[COOKIE] = other
    gateway.turn({"type": "response", "output": [], "usage": {}, "continuation": None})
    response = answered(client, asked_for("", said="Use the business's language for me again."))
    frames(response)
    assert response.cookies[COOKIE].value == business
    assert session_language(client) == business


def test_a_card_the_person_says_no_to_leaves_the_language_as_it_was(client, ana, gateway):
    client.cookies[COOKIE] = "es"
    gateway.turn({"type": "response", "output": [], "usage": {}, "continuation": None})
    response = answered(client, asked_for("en"), accepted=False)
    ran = frames(response)
    assert (ran[0]["name"], ran[0]["outcome"]) == ("base.profile.preferences_set", "cancelled")
    assert COOKIE not in response.cookies
    assert session_language(client) == "es"


def test_a_card_that_waits_for_the_yes_leaves_no_language(client, ana):
    client.cookies[COOKIE] = "es"
    response = post(client, "/assistant/turn", asked_for("en"))
    frames(response)
    assert COOKIE not in response.cookies
    assert session_language(client) == "es"


def test_a_turn_that_fails_after_the_yes_undoes_the_change_and_leaves_no_language(client, ana, gateway, monkeypatch):
    client.cookies[COOKIE] = "es"
    body = asked_for("en")
    drawn = frames(post(client, "/assistant/turn", body))

    def broken(*args, **kwargs):
        raise RuntimeError("the turn broke after its tool ran")

    monkeypatch.setattr(assistant_service, "_assistant_instructions", broken)
    client.raise_request_exception = False
    response = post(client, "/assistant/turn", {**body, "pending": drawn[-1]["pending"], "decision": {"call_id": "c1", "accepted": True}})
    assert response.status_code == 500
    assert COOKIE not in response.cookies
    assert chosen(ana) == ""
    assert session_language(client) == "es"


def chosen(user) -> str:
    """The language kept in the profile of ``user``, read as «My profile» reads it."""
    profile = get("base.profile.get")
    return profile(as_the(user), profile.input()).language


def as_the(user) -> OperationContext:
    return OperationContext(scope=A, actor=user, permissions=frozenset({VIEW_HOME}), language="es")


def test_without_a_request_the_choice_is_kept_and_there_is_no_answer_to_leave_it_on(ana):
    choose = get("base.profile.preferences_set")
    assert choose(as_the(ana), choose.input.model_validate_json(preferences("en"))).language == "en"
    assert chosen(ana) == "en"


def test_preferences_the_screen_could_not_save_leave_no_language(client, ana):
    client.cookies[COOKIE] = "es"
    response = post(client, "/me/preferences", {"language": "fr", "theme_mode": "", "palette": "", "ui_scale": 100})
    assert response.status_code == 422
    assert COOKIE not in response.cookies
    assert session_language(client) == "es"


@pytest.mark.parametrize("spoken", ["es", "en"])
def test_the_appearance_alone_leaves_the_language_the_person_speaks_here(client, ana, spoken):
    """Who enters with their account speaks its language, which may not be the business's (BASE-F51)."""
    client.cookies[COOKIE] = spoken
    response = post(client, "/me/preferences", {"theme_mode": "dark"})
    assert response.status_code == 200, response.content
    assert COOKIE not in response.cookies
    assert session_language(client) == spoken

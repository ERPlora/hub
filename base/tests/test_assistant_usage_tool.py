"""The assistant answers how many of this month's messages of the assistant are used and left (BASE-F104) with the
figures «Usage and plan» shows: the same read, ``base.assistant.usage``, which asks erplora.com, where they are
counted. Only when the person asks: a turn that does not ask for it reads nothing. It waits on erplora.com, so inside
a turn the route asks it before the turn's transaction opens, as the search in the documentation.
"""

import json

import pytest
from django.db import connections
from live.operations import get

from base import assistant
from base.models import Membership
from base.schemas.assistant import AssistantCallIn
from base.tenancy.tests.business import HUB_DB, HUB_DB_COMMITTED, A, in_business_a
from base.tests.fake_gateway import gateway, signed
from base.tests.test_api_assistant import frames, post
from base.tests.test_assistant_asks import assert_offered_with_room, members

__all__ = ["gateway", "in_business_a"]

pytestmark = HUB_DB

USAGE = "/internal/assistant/usage"
TOOL = "base.assistant.usage"
MONTH = {"used": 599, "limit": 3000, "resets_at": "2026-12-01T00:00:00Z", "demo": False}
#: The questions a person asks, none of the tool's asks: the first, word for word as the QA asked it.
ASKED = {
    "en": "How many questions have I got left this month on my plan? I don't want to run out on a busy weekend.",
    "es": "¿Cuántos mensajes del asistente me quedan este mes? No quiero quedarme sin él un fin de semana de mucho lío.",
}
READ = {"call_id": "u1", "name": "base__assistant__usage", "arguments": "{}"}
READ_ASKED = {
    "role": "assistant",
    "content": "",
    "tool_calls": [{"id": "u1", "type": "function", "function": {"name": READ["name"], "arguments": "{}"}}],
}
ANSWERED = ({"type": "text_delta", "text": "599 de 3000."}, {"type": "response", "output": [], "usage": {}, "continuation": None})


def _turn(client, make_user, gateway, **reply) -> list[dict]:
    """The frames of a turn where an employee asked how many messages are left and the model asked for the read."""
    client.force_login(make_user("ana", host=A.key, role=Membership.Role.EMPLOYEE))
    gateway.reply(USAGE, **reply)
    gateway.turn(*ANSWERED)
    body = {"messages": [{"role": "user", "content": ASKED["en"]}, READ_ASKED], "pending": [READ], "continuation": "tok"}
    return frames(post(client, "/assistant/turn", body))


@pytest.mark.parametrize("role", tuple(Membership.Role))
def test_every_role_holds_the_months_messages_and_never_the_search_among_its_tools(make_user, role):
    tools = assistant.tools.catalog(members(make_user, "usage")(role, "en"))

    assert TOOL in tools
    assert assistant.relevance.FIND_TOOLS not in tools  # the search runs apart: it never ranks among the tools


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.EMPLOYEE])
def test_asking_how_many_messages_are_left_offers_the_months_messages(make_user, role, language):
    tools = assistant.tools.catalog(members(make_user, "usage")(role, language))

    assert_offered_with_room(tools, TOOL, ASKED[language], language)


def test_the_plans_usage_sends_the_model_to_the_months_messages():
    """What the plan's usage reads is no figure of the assistant's: its description names the read that has them, for
    the model not to answer that they cannot be seen."""
    assert TOOL in get("base.plan.usage").ai_spec().description


def test_the_model_reads_the_months_messages_as_usage_and_plan_shows_them(client, make_user, gateway):
    got = _turn(client, make_user, gateway, json=MONTH)

    assert [(frame["name"], frame["outcome"]) for frame in got if frame["type"] == "executed"] == [(TOOL, "ok")]
    result = got[-1]["append"][0]
    assert (result["tool_call_id"], json.loads(result["content"])) == ("u1", MONTH)
    [asked] = gateway.sent(USAGE)
    assert asked.body == {"hub": A.key}
    assert signed(asked)


def test_messages_that_cannot_be_read_are_told_to_the_model_never_made_up(client, make_user, gateway):
    got = _turn(client, make_user, gateway, status=503, json={"error": {"code": "assistant.provider_unavailable", "message": "x"}})

    [executed] = [frame for frame in got if frame["type"] == "executed"]
    assert (executed["name"], executed["outcome"], executed["code"]) == (TOOL, "error", "base.assistant_unavailable")
    assert json.loads(got[-1]["append"][0]["content"])["error"]["code"] == "base.assistant_unavailable"
    assert len(gateway.sent(USAGE)) == 1


def test_a_turn_that_does_not_ask_for_them_reads_nothing_of_erplora_com(client, make_user, gateway):
    client.force_login(make_user("ana", host=A.key, role=Membership.Role.OWNER))
    gateway.turn(*ANSWERED)

    frames(post(client, "/assistant/turn", {"messages": [{"role": "user", "content": ASKED["en"]}]}))

    assert gateway.sent(USAGE) == []
    assert READ["name"] in [tool["name"] for tool in gateway.sent("/internal/assistant/chat/stream")[0].body["tools"]]


def test_a_turn_that_only_searches_the_documentation_does_not_read_them(make_user, gateway):
    person = members(make_user, "usage")(Membership.Role.EMPLOYEE, "es")
    search = AssistantCallIn(call_id="d1", name="base__docs__search", arguments='{"query": "¿Cómo abro la caja?"}')

    assert assistant.gateway.prepare_usage(person, [search]) is None
    assert gateway.requests == []


def test_nobody_without_a_session_makes_erplora_com_read_them(client, gateway):
    body = {"messages": [{"role": "user", "content": ASKED["en"]}, READ_ASKED], "pending": [READ], "continuation": "tok"}

    assert post(client, "/assistant/turn", body).status_code == 401
    assert gateway.requests == []


@HUB_DB_COMMITTED
def test_the_turn_asks_the_months_messages_before_its_transaction_opens(client, make_user, gateway, monkeypatch):
    """Up to 15 s of waiting inside the turn's transaction would hold the hub's connection (on the Free plan, its one
    transaction at a time): the route asks first (``gateway.prepare``) and the turn reads that answer."""
    seen = []
    post_to_gateway = assistant.gateway._post

    def probe(path, payload):
        if path == USAGE:
            seen.append(any(connection.in_atomic_block for connection in connections.all()))
        return post_to_gateway(path, payload)

    monkeypatch.setattr(assistant.gateway, "_post", probe)
    got = _turn(client, make_user, gateway, json=MONTH)

    assert [frame["outcome"] for frame in got if frame["type"] == "executed"] == ["ok"]
    assert seen == [False]

"""The assistant over HTTP (APP-BASE-9): its four routes, each bound to its operation; the turn answers as a stream
of frames (``text/event-stream``) the panel reads with ``fetch``; the gateway is ``fake_gateway`` (a real server).
"""

import json

import pytest
from asgiref.sync import async_to_sync
from django.urls import resolve

from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

HOST = {"HTTP_HOST": "a.localhost:8000"}
ASK = {"role": "user", "content": "¿cuántos elementos tengo?"}


async def _read(stream) -> bytes:
    return b"".join([chunk async for chunk in stream])


def frames(response) -> list[dict]:
    """The frames of a turn, read as the server streams them: asynchronously (ASGI), piece by piece."""
    assert response["Content-Type"].startswith("text/event-stream") and response.is_async
    body = async_to_sync(_read)(response.streaming_content).decode()
    return [json.loads(chunk[len("data: "):]) for chunk in body.split("\n\n") if chunk.startswith("data: ")]


def post(client, path, body, **extra):
    return client.post(f"/api{path}", json.dumps(body), content_type="application/json", **HOST, **extra)


@pytest.mark.parametrize(
    "path, method, operation",
    [
        ("/assistant/turn", "POST", "base.assistant.turn"),
        ("/assistant/usage", "GET", "base.assistant.usage"),
        ("/assistant/report", "POST", "base.assistant.report"),
        ("/assistant/transcribe", "POST", "base.assistant.transcribe"),
    ],
)
def test_each_route_is_bound_to_its_operation(path, method, operation):
    from base.api import router

    [route] = router.path_operations[path].operations
    assert (route.methods, route.operation_id) == ([method], operation)
    assert resolve(f"/api{path}").url_name


def test_nobody_without_a_session_talks_to_the_assistant(client, gateway):
    """gh:hub#1254: the old hub's assistant doors answered without a session."""
    assert post(client, "/assistant/turn", {"messages": [ASK]}).status_code == 401
    assert client.get("/api/assistant/usage", **HOST).status_code == 401
    assert gateway.requests == []


def test_a_turn_streams_the_answer_of_the_gateway(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.turn(
        {"type": "text_delta", "text": "Tienes "},
        {"type": "text_delta", "text": "**2** elementos."},
        {"type": "response", "output": [], "usage": {}, "continuation": None},
        {"type": "usage", "used": 4, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False},
    )
    got = frames(post(client, "/assistant/turn", {"messages": [ASK]}))
    assert [frame["type"] for frame in got] == ["text", "text", "usage", "done"]
    assert got[-1]["append"] == [{"role": "assistant", "content": "Tienes **2** elementos."}]
    sent = gateway.sent("/internal/assistant/chat/stream")[0]
    assert signed(sent)
    assert sent.body["hub"] == "a"
    assert "demo__item__list" in [tool["name"] for tool in sent.body["tools"]]
    # An employee may read the items but not create them: the write is not even offered.
    assert "demo__item__create" not in [tool["name"] for tool in sent.body["tools"]]


def test_a_write_the_model_asked_for_comes_as_a_card_and_the_gateway_waits(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_manager"))
    call = {"call_id": "c1", "name": "demo__item__create", "arguments": '{"name": "Mesa 4"}'}
    asked = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "demo__item__create", "arguments": '{"name": "Mesa 4"}'}}
    ]}
    got = frames(post(client, "/assistant/turn", {"messages": [ASK, asked], "pending": [call], "continuation": "tok"}))
    assert [frame["type"] for frame in got] == ["confirm", "done"]
    assert got[0]["card"]["operation"] == "demo.item.create"
    assert got[0]["call"] == call
    assert (got[1]["pending"], got[1]["continuation"]) == ([call], "tok")
    assert gateway.requests == []


def test_the_yes_runs_it_and_the_turn_goes_on_with_its_result(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_manager"))
    call = {"call_id": "c1", "name": "demo__item__create", "arguments": '{"name": "Mesa 4"}'}
    asked = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "demo__item__create", "arguments": '{"name": "Mesa 4"}'}}
    ]}
    gateway.turn({"type": "text_delta", "text": "Hecho."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    body = {"messages": [ASK, asked], "pending": [call], "continuation": "tok", "decision": {"call_id": "c1", "accepted": True}}
    got = frames(post(client, "/assistant/turn", body))
    assert [frame["type"] for frame in got] == ["executed", "text", "done"]
    assert (got[0]["name"], got[0]["outcome"]) == ("demo.item.create", "ok")
    result, answer = got[-1]["append"]
    assert (result["role"], result["tool_call_id"]) == ("tool", "c1")
    assert answer == {"role": "assistant", "content": "Hecho."}
    sent = gateway.sent("/internal/assistant/chat/stream")[0].body
    assert sent["continuation"] == "tok"
    assert sent["messages"][-1]["tool_call_id"] == "c1"


def test_after_too_many_rounds_it_stops_and_says_why(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    messages = [ASK]
    for n in range(6):
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"r{n}", "type": "function", "function": {"name": "demo__item__list", "arguments": "{}"}}
        ]})
        if n < 5:
            messages.append({"role": "tool", "tool_call_id": f"r{n}", "content": "{}"})
    body = {"messages": messages, "pending": [{"call_id": "r5", "name": "demo__item__list", "arguments": "{}"}]}
    got = frames(post(client, "/assistant/turn", body))
    assert [frame["type"] for frame in got] == ["executed", "error", "done"]
    assert got[1]["code"] == "assistant.too_many_steps"
    assert got[-1]["append"][0]["tool_call_id"] == "r5"
    assert gateway.requests == []


def test_a_turn_too_heavy_is_refused_before_it_is_read(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    from base.api import MAX_ASSISTANT_TURN_BODY

    response = client.post(
        "/api/assistant/turn", b"x", content_type="application/json", CONTENT_LENGTH=MAX_ASSISTANT_TURN_BODY + 1, **HOST
    )
    assert response.status_code == 413


def test_usage_report_and_dictation_go_through_their_routes(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply("/internal/assistant/usage", json={"used": 1, "limit": 30, "resets_at": None, "demo": False})
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    gateway.reply("/internal/speech/transcribe", json={"text": "hola", "language": "es"})
    assert client.get("/api/assistant/usage", **HOST).json()["limit"] == 30
    report = {"message_id": "m1", "reason": "harmful", "answer": "x"}
    assert post(client, "/assistant/report", report).json() == {"sent": True, "duplicate": False}
    dictation = {"audio": "UklGRg==", "mime_type": "audio/webm"}
    assert post(client, "/assistant/transcribe", dictation).json()["text"] == "hola"
    assert gateway.sent("/internal/speech/transcribe")[0].body["language"] == "en"


def test_a_dictation_over_two_megabytes_is_refused_by_the_hub(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    dictation = {"audio": "A" * 2_800_001, "mime_type": "audio/webm"}
    assert post(client, "/assistant/transcribe", dictation).status_code == 422


def test_a_long_answer_can_be_reported_whole(client, make_user, gateway):
    """An answer with a long table runs past 4,000 characters: the Hub takes what erplora.com's door takes (BASE-G123)."""
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    answer = "| a | b |\n" * 2_000
    report = {"message_id": "m1", "reason": "incorrect", "question": "¿?" * 3_000, "answer": answer}
    assert post(client, "/assistant/report", report).status_code == 200
    assert gateway.sent("/internal/assistant/report")[0].body["answer"] == answer

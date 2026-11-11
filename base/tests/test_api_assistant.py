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
#: A question that names the app it asks about: «elementos» is no tool's word (the demo items say no asks), and since
#: live#22 a «¿cuántos…?» of nothing a tool knows brings no list at all.
ASK = {"role": "user", "content": "¿cuántos elementos tengo en Demo?"}


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
    body = _create_turn()
    [call] = body["pending"]
    got = frames(post(client, "/assistant/turn", {key: value for key, value in body.items() if key != "decision"}))
    assert [frame["type"] for frame in got] == ["confirm", "done"]
    assert got[0]["card"]["operation"] == "demo.item.create"
    # hub#1208: the call its card waits on comes with the fingerprint of what the card showed, in the card's frame and
    # in the calls that wait: the panel gives these back with the yes.
    assert got[0]["call"] == {**call, "shown": got[0]["call"]["shown"]} and len(got[0]["call"]["shown"]) == 64
    assert (got[1]["pending"], got[1]["continuation"]) == ([got[0]["call"]], "tok")
    # A round that never reached the gateway brought no pages of the web (hub#870): without the word, the browser would
    # not know where the whole answer came from (ui#105), and its report would reach support without its text.
    assert got[1]["web"] is False
    assert gateway.requests == []


def test_the_yes_runs_it_and_the_turn_goes_on_with_its_result(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_manager"))
    body = _answering_its_card(client, _create_turn())
    gateway.turn({"type": "text_delta", "text": "Hecho."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
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
    assert got[-1]["web"] is False  # no pages: it never reached the gateway (hub#870)
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


# ── Whether the answer came from the web, end to end (hub#870, saas#287, BASE-F105) ────────────────────────────────


def test_a_turn_that_searched_the_web_tells_the_browser_and_its_report_tells_erplora(client, make_user, gateway):
    """The whole way of the mark through the Hub: the gateway's ``{type: web}`` closes the turn as ``done.web``, and the
    report the browser sends back with it reaches erplora.com's door with it, which then does not mail the answer."""
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.turn(
        {"type": "web"},
        {"type": "text_delta", "text": "El plazo acaba el 20 (aeat.es)."},
        {"type": "response", "output": [], "usage": {}, "continuation": None},
    )
    got = frames(post(client, "/assistant/turn", {"messages": [{"role": "user", "content": "¿Cuándo acaba el plazo?"}]}))
    assert [frame["type"] for frame in got] == ["text", "done"]
    assert got[-1]["web"] is True
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    report = {"message_id": "m1", "reason": "incorrect", "question": "¿Cuándo acaba el plazo?", "answer": got[0]["text"]}
    assert post(client, "/assistant/report", {**report, "web": got[-1]["web"]}).json() == {"sent": True, "duplicate": False}
    seen = gateway.sent("/internal/assistant/report")[0]
    assert seen.body["web"] is True
    assert signed(seen)


def test_a_turn_that_did_not_search_lets_support_read_its_report(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.turn({"type": "text_delta", "text": "Tienes 2."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    done = frames(post(client, "/assistant/turn", {"messages": [ASK]}))[-1]
    assert done["web"] is False
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    post(client, "/assistant/report", {"message_id": "m1", "reason": "other", "answer": "Tienes 2.", "web": done["web"]})
    assert gateway.sent("/internal/assistant/report")[0].body["web"] is False


def test_a_report_of_an_answer_kept_before_the_mark_leaves_the_web_out(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply("/internal/assistant/report", status=202, json={"sent": True, "duplicate": False})
    post(client, "/assistant/report", {"message_id": "m1", "reason": "other", "answer": "x"})
    assert "web" not in gateway.sent("/internal/assistant/report")[0].body


def test_a_turn_the_gateway_refused_closes_saying_it_brought_no_pages(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply("/internal/assistant/chat/stream", status=503, json={"error": {"code": "assistant.no_model", "message": "x"}})
    got = frames(post(client, "/assistant/turn", {"messages": [ASK]}))
    assert [frame["type"] for frame in got] == ["error", "done"]
    assert got[-1]["web"] is False


# ── A write a manager may approve (BASE-G118, with APP-BASE-5's approvals): the chat asks as the screen does ────────

APPROVED_CREATE = {"demo.item.create": "Create an item"}


# ── Who asks, told to the model (hub#585, BASE-F100) ────────────────────────────────────────────────────────────


def _instructions_sent(gateway) -> str:
    return " ".join(gateway.sent("/internal/assistant/chat/stream")[0].body["instructions"].split())


def test_the_model_is_told_the_role_of_an_employee_and_what_a_manager_must_approve(client, make_user, gateway):
    """hub#585: an employee asked to switch an app off and the model, never told whom it served, looked for another
    way until «too many steps», or told the state of something else as if it were the app's. What the gateway gets
    names their role as the screens do, in their language, who can do what it cannot, and the write their app lets a
    manager approve (``demo.item.add_line``), offered to them as its button on the screen is."""
    client.force_login(make_user("eva", host="a", role="hub_employee"))
    gateway.turn({"type": "response", "output": [], "usage": {}, "continuation": None})
    ask = {"role": "user", "content": "añade una línea de 2 cafés al elemento Mesa 4"}
    frames(post(client, "/assistant/turn", {"messages": [ask]}, HTTP_ACCEPT_LANGUAGE="es"))

    sent = _instructions_sent(gateway)
    assert "You talk to the «Empleado» of this business: your tools are the ones this role may use" in sent
    assert (
        "say plainly that it is not available to them here, because their role cannot do it or because its app is not "
        "on, and that a manager or the owner can"
    ) in sent
    offered = gateway.sent("/internal/assistant/chat/stream")[0].body["tools"]
    assert "demo__item__add_line" in [tool["name"] for tool in offered]
    approval = sent.split("This person needs a manager's approval to run ")[1].split(": before you call one")[0]
    assert "`demo__item__add_line`" in approval.split(", ")


def test_a_manager_who_may_do_it_is_asked_for_no_approval(client, make_user, gateway):
    client.force_login(make_user("mario", host="a", role="hub_manager"))
    gateway.turn({"type": "response", "output": [], "usage": {}, "continuation": None})
    ask = {"role": "user", "content": "add a line of 2 coffees to the item Mesa 4"}
    frames(post(client, "/assistant/turn", {"messages": [ask]}, HTTP_ACCEPT_LANGUAGE="en"))

    sent = _instructions_sent(gateway)
    assert "You talk to the «Manager» of this business" in sent
    assert "the owner or an administrator can" in sent
    assert "approv" not in sent


@pytest.fixture
def approvable_create(monkeypatch):
    """``demo`` names its «create» as approvable, as an app would in its ``LiveAppConfig``."""
    from django.apps import apps
    from django.core.cache import cache

    monkeypatch.setattr(apps.get_app_config("demo"), "approvals", APPROVED_CREATE, raising=False)
    cache.clear()
    yield
    cache.clear()


def _create_turn() -> dict:
    call = {"call_id": "c1", "name": "demo__item__create", "arguments": '{"name": "Mesa 4"}'}
    asked = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "demo__item__create", "arguments": '{"name": "Mesa 4"}'}}
    ]}
    return {"messages": [ASK, asked], "pending": [call], "continuation": "tok", "decision": {"call_id": "c1", "accepted": True}}


def _answering_its_card(client, body: dict) -> dict:
    """``body`` with the calls that wait as the turn that draws their card gives them back, the way the panel sends
    its answer (hub#1208: a yes is for the card it answers)."""
    drawn = frames(post(client, "/assistant/turn", {key: value for key, value in body.items() if key != "decision"}))
    return {**body, "pending": drawn[-1]["pending"]}


def _employee_and_manager(client, make_user):
    from base.tests.test_people import with_pin

    make_user("saas:4", host="a", role="hub_manager", first_name="Mario")
    with_pin("saas:4", "1357")
    client.force_login(make_user("saas:3", host="a", role="hub_employee", first_name="Eva"))


def _items(name: str = "Mesa 4") -> int:
    from apps.demo.models import Item

    return Item.objects.filter(name=name).count()


def test_its_yes_asks_for_a_managers_approval_as_the_screen_does_and_runs_nothing(client, make_user, gateway, approvable_create):
    _employee_and_manager(client, make_user)
    response = post(client, "/assistant/turn", _answering_its_card(client, _create_turn()))
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "requires_elevation"
    assert (error["approval"]["operation"], error["approval"]["label"]) == ("demo.item.create", "Create an item")
    assert len(error["approval"]["fingerprint"]) == 64
    assert _items() == 0
    assert gateway.requests == []


def test_with_the_managers_pass_it_runs_once_as_the_person_and_the_pass_is_spent(client, make_user, gateway, approvable_create):
    from base.models import Approval, Credential

    _employee_and_manager(client, make_user)
    body = _answering_its_card(client, _create_turn())
    asked = post(client, "/assistant/turn", body).json()["error"]["approval"]
    manager = str(Credential.objects.get(username="saas:4").pk)
    approval = {"operation": asked["operation"], "fingerprint": asked["fingerprint"], "person": manager, "pin": "1357"}
    granted = post(client, "/approvals", approval)
    assert granted.status_code == 200, granted.content
    token = granted.json()["token"]

    gateway.turn({"type": "text_delta", "text": "Hecho."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    got = frames(post(client, "/assistant/turn", body, HTTP_X_ELEVATION_TOKEN=token))
    assert (got[0]["type"], got[0]["name"], got[0]["outcome"]) == ("executed", "demo.item.create", "ok")
    assert _items() == 1
    assert Approval.objects.get().used_at is not None

    # The same pass again: spent, so the write does not run twice.
    gateway.turn({"type": "text_delta", "text": "No."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    again = frames(post(client, "/assistant/turn", body, HTTP_X_ELEVATION_TOKEN=token))
    assert (again[0]["outcome"], again[0]["code"]) == ("error", "requires_elevation")
    assert _items() == 1


def test_its_question_says_the_figures_of_the_write_and_the_record_keeps_them(client, make_user, gateway, approvable_create, monkeypatch):
    """FIX-HUB-BASE-APPROVAL-LABEL-WITHOUT-DISCOUNT-FIGURE: the chat asks with the figures of the very write the
    person said yes to, read from its arguments as the command validates them; the pass spent keeps them."""
    from django.apps import apps

    from base.models import Approval, Credential

    monkeypatch.setattr(apps.get_app_config("demo"), "approval_figures", {"demo.item.create": ["Create the item {name}"]}, raising=False)
    _employee_and_manager(client, make_user)
    body = _answering_its_card(client, _create_turn())
    asked = post(client, "/assistant/turn", body).json()["error"]["approval"]
    assert asked["label"] == "Create the item Mesa 4"
    manager = str(Credential.objects.get(username="saas:4").pk)
    approval = {"operation": asked["operation"], "fingerprint": asked["fingerprint"], "person": manager, "pin": "1357"}
    token = post(client, "/approvals", approval).json()["token"]
    gateway.turn({"type": "text_delta", "text": "Hecho."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    got = frames(post(client, "/assistant/turn", body, HTTP_X_ELEVATION_TOKEN=token))
    assert got[0]["outcome"] == "ok"
    assert Approval.objects.get().figures == {"name": "Mesa 4"}


def test_a_pass_for_another_request_does_not_let_this_one_through(client, make_user, gateway, approvable_create):
    from base.models import Credential

    _employee_and_manager(client, make_user)
    asked = post(client, "/assistant/turn", _answering_its_card(client, _create_turn())).json()["error"]["approval"]
    manager = str(Credential.objects.get(username="saas:4").pk)
    token = post(client, "/approvals", {**asked, "person": manager, "pin": "1357"}).json()["token"]
    other = _create_turn()
    other["pending"][0]["arguments"] = other["messages"][1]["tool_calls"][0]["function"]["arguments"] = '{"name": "Mesa 9"}'
    other = _answering_its_card(client, other)
    gateway.turn({"type": "text_delta", "text": "No."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    got = frames(post(client, "/assistant/turn", other, HTTP_X_ELEVATION_TOKEN=token))
    assert (got[0]["outcome"], got[0]["code"]) == ("error", "requires_elevation")
    assert _items("Mesa 9") == 0


def test_a_write_nobody_may_approve_is_still_refused_flat(client, make_user, gateway):
    _employee_and_manager(client, make_user)
    gateway.turn({"type": "text_delta", "text": "No puedo."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    got = frames(post(client, "/assistant/turn", _create_turn()))
    assert (got[0]["outcome"], got[0]["code"]) == ("refused", "not_available")
    assert _items() == 0


def test_a_pass_approved_for_another_command_on_this_very_request_does_not_let_it_through(client, make_user, gateway, monkeypatch):
    """What the manager read on the dialog is what runs: a pass granted as «Create an item» on the fingerprint of a
    turn that renames one spends nothing on the rename (rv-hub-247)."""
    from django.apps import apps
    from django.core.cache import cache

    from apps.demo.models import Item
    from base.models import Approval, Credential

    monkeypatch.setattr(
        apps.get_app_config("demo"), "approvals", {**APPROVED_CREATE, "demo.item.update": "Change an item"}, raising=False
    )
    cache.clear()
    _employee_and_manager(client, make_user)
    item = Item.objects.create(name="Mesa 4")
    arguments = json.dumps({"id": str(item.pk), "name": "Mesa 9"})
    body = _create_turn()
    body["pending"][0]["name"] = body["messages"][1]["tool_calls"][0]["function"]["name"] = "demo__item__update"
    body["pending"][0]["arguments"] = body["messages"][1]["tool_calls"][0]["function"]["arguments"] = arguments
    body = _answering_its_card(client, body)
    asked = post(client, "/assistant/turn", body).json()["error"]["approval"]
    assert asked["operation"] == "demo.item.update"
    manager = str(Credential.objects.get(username="saas:4").pk)
    granted = post(client, "/approvals", {"operation": "demo.item.create", "fingerprint": asked["fingerprint"], "person": manager, "pin": "1357"})
    assert granted.status_code == 200, granted.content
    gateway.turn({"type": "text_delta", "text": "No."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    got = frames(post(client, "/assistant/turn", body, HTTP_X_ELEVATION_TOKEN=granted.json()["token"]))
    assert (got[0]["outcome"], got[0]["code"]) == ("error", "requires_elevation")
    assert Item.objects.get(pk=item.pk).name == "Mesa 4"
    assert Approval.objects.get().used_at is None
    cache.clear()


# ── How-to questions answered from ERPlora's documentation (saas ASSISTANT-F28) ─────────────────────────────────────

DOCS = "/internal/assistant/docs/search"
HOW = {"role": "user", "content": "¿Cómo abro la caja?"}
EXCERPT = {
    "source": "app_doc",
    "path": "app_doc:cash_register",
    "heading": "Caja > Abrir la caja",
    "text": "Abre la caja desde Caja > Abrir con el efectivo inicial.",
    "score": 0.91,
    "lang": "es",
}
#: What the model reads of it: the excerpt with the line its answer cites it by (hub#1079).
CITED = {**EXCERPT, "cite": "Fuente: Caja > Abrir la caja"}
SEARCH = {"call_id": "d1", "name": "base__docs__search", "arguments": '{"query": "¿Cómo abro la caja?"}'}
SEARCH_ASKED = {"role": "assistant", "content": "", "tool_calls": [
    {"id": "d1", "type": "function", "function": {"name": "base__docs__search", "arguments": SEARCH["arguments"]}}
]}


def _how_to_turn(client, make_user, gateway, role: str) -> list[dict]:
    """The frames of a turn where ``role`` asked how to open the till and the model searched the documentation, which
    erplora.com answers with ``EXCERPT``."""
    client.force_login(make_user("ana", host="a", role=role))
    gateway.reply(DOCS, json={"results": [EXCERPT]})
    gateway.turn({"type": "text_delta", "text": "Desde Caja > Abrir."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    body = {"messages": [HOW, SEARCH_ASKED], "pending": [SEARCH], "continuation": "tok"}
    return frames(post(client, "/assistant/turn", body, HTTP_ACCEPT_LANGUAGE="es"))


def test_a_how_to_question_gets_the_excerpts_of_the_documentation_as_its_tool_result(client, make_user, gateway):
    got = _how_to_turn(client, make_user, gateway, "hub_employee")

    assert [frame["type"] for frame in got] == ["executed", "text", "done"]
    assert (got[0]["name"], got[0]["outcome"], got[0]["app_name"]) == ("base.docs.search", "ok", "Ayuda")
    result = got[-1]["append"][0]
    assert (result["tool_call_id"], json.loads(result["content"])) == ("d1", {"results": [CITED]})
    [asked] = gateway.sent(DOCS)
    assert asked.body == {"hub": "a", "query": "¿Cómo abro la caja?", "language": "es", "limit": 8}
    assert signed(asked)
    assert gateway.sent("/internal/assistant/chat/stream")[0].body["messages"][-1]["tool_call_id"] == "d1"


def test_the_model_answers_a_how_to_question_told_to_end_it_with_the_cite_of_its_excerpt(client, make_user, gateway):
    """hub#1079: «¿cómo se hace una factura a partir de un tique?» got the steps and no excerpt they came from. What
    the model reads next is the excerpt with the line its answer cites it by, in the person's language, and the
    instruction to end the answer with it; nothing of the business ran for it, only the search."""
    got = _how_to_turn(client, make_user, gateway, "hub_owner")

    assert [(frame["name"], frame["kind"]) for frame in got if frame["type"] == "executed"] == [("base.docs.search", "query")]
    [tool] = [message for message in gateway.sent("/internal/assistant/chat/stream")[0].body["messages"] if message["role"] == "tool"]
    assert [excerpt["cite"] for excerpt in json.loads(tool["content"])["results"]] == ["Fuente: Caja > Abrir la caja"]
    assert "end that answer with the `cite` of each excerpt you used" in _instructions_sent(gateway)


def test_documentation_that_cannot_be_searched_is_told_to_the_model_never_made_up(client, make_user, gateway):
    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply(DOCS, status=503, json={"error": {"code": "assistant.provider_unavailable", "message": "down"}})
    gateway.turn({"type": "text_delta", "text": "No he podido buscar."}, {"type": "response", "output": [], "usage": {}, "continuation": None})

    body = {"messages": [HOW, SEARCH_ASKED], "pending": [SEARCH], "continuation": "tok"}
    got = frames(post(client, "/assistant/turn", body, HTTP_ACCEPT_LANGUAGE="es"))

    assert (got[0]["name"], got[0]["outcome"], got[0]["code"]) == ("base.docs.search", "error", "base.assistant_unavailable")
    assert "documentación de ERPlora" in json.loads(got[-1]["append"][0]["content"])["error"]["message"]
    assert len(gateway.sent(DOCS)) == 1


def test_nobody_without_a_session_makes_erplora_com_search(client, gateway):
    body = {"messages": [HOW, SEARCH_ASKED], "pending": [SEARCH], "continuation": "tok"}

    assert post(client, "/assistant/turn", body).status_code == 401
    assert gateway.requests == []


@pytest.mark.django_db(transaction=True)
def test_the_turn_asks_the_documentation_before_its_transaction_opens(client, make_user, gateway, monkeypatch):
    """The search waits on erplora.com (up to 15 s): inside the turn's transaction it would hold the hub's connection
    (PLAN §14.2), so the route asks it first (``assistant.prepare``) and the turn reads the answer."""
    from django.db import connections

    from base import assistant

    client.force_login(make_user("ana", host="a", role="hub_employee"))
    gateway.reply(DOCS, json={"results": [EXCERPT]})
    gateway.turn({"type": "text_delta", "text": "Desde Caja > Abrir."}, {"type": "response", "output": [], "usage": {}, "continuation": None})
    seen = []
    post_to_gateway = assistant._post

    def probe(path, payload):
        if path == DOCS:
            seen.append(any(connection.in_atomic_block for connection in connections.all()))
        return post_to_gateway(path, payload)

    monkeypatch.setattr(assistant, "_post", probe)
    body = {"messages": [HOW, SEARCH_ASKED], "pending": [SEARCH], "continuation": "tok"}
    got = frames(post(client, "/assistant/turn", body, HTTP_ACCEPT_LANGUAGE="es"))

    assert got[0]["outcome"] == "ok"
    assert seen == [False]

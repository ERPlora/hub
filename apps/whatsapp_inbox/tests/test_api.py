"""The WhatsApp inbox's routes: each bound to its operation, and the flows over HTTP.

Requests go to ``a.localhost`` (scope ``a``) with Django's sync test client, which sees the test's
transaction. What erplora.com pushes has no route here: ``base`` mounts ``/internal/whatsapp/*``.
"""

import json

import httpx
import pytest
import respx
from django.conf import settings
from live.ninja import ensure_api_parity

from apps.whatsapp_inbox.api import router
from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import connect, receive
from config.api import api

ROUTES = {
    ("GET", "/whatsapp_inbox/conversations", "whatsapp_inbox.conversation.list"),
    (
        "GET",
        "/whatsapp_inbox/conversations/detail",
        "whatsapp_inbox.conversation.detail",
    ),
    (
        "GET",
        "/whatsapp_inbox/conversations/by_phone",
        "whatsapp_inbox.conversation.by_phone",
    ),
    (
        "GET",
        "/whatsapp_inbox/conversations/summary",
        "whatsapp_inbox.conversation.summary",
    ),
    (
        "GET",
        "/whatsapp_inbox/conversations/count_awaiting_reply",
        "whatsapp_inbox.conversation.count_awaiting_reply",
    ),
    (
        "GET",
        "/whatsapp_inbox/conversations/notices",
        "whatsapp_inbox.conversation.notices",
    ),
    (
        "POST",
        "/whatsapp_inbox/conversations/mark_read",
        "whatsapp_inbox.conversation.mark_read",
    ),
    (
        "POST",
        "/whatsapp_inbox/conversations/assign",
        "whatsapp_inbox.conversation.assign",
    ),
    (
        "POST",
        "/whatsapp_inbox/conversations/set_status",
        "whatsapp_inbox.conversation.set_status",
    ),
    (
        "POST",
        "/whatsapp_inbox/conversations/link_customer",
        "whatsapp_inbox.conversation.link_customer",
    ),
    (
        "POST",
        "/whatsapp_inbox/conversations/erase",
        "whatsapp_inbox.conversation.erase",
    ),
    ("GET", "/whatsapp_inbox/messages", "whatsapp_inbox.message.list"),
    ("POST", "/whatsapp_inbox/messages/send", "whatsapp_inbox.message.send"),
    ("POST", "/whatsapp_inbox/messages/retry", "whatsapp_inbox.message.retry"),
    ("POST", "/whatsapp_inbox/messages/notify", "whatsapp_inbox.message.notify"),
    ("GET", "/whatsapp_inbox/notes", "whatsapp_inbox.note.list"),
    ("POST", "/whatsapp_inbox/notes", "whatsapp_inbox.note.add"),
    ("POST", "/whatsapp_inbox/notes/delete", "whatsapp_inbox.note.delete"),
    ("GET", "/whatsapp_inbox/templates", "whatsapp_inbox.template.list"),
    ("POST", "/whatsapp_inbox/templates", "whatsapp_inbox.template.create"),
    ("POST", "/whatsapp_inbox/templates/update", "whatsapp_inbox.template.update"),
    ("POST", "/whatsapp_inbox/templates/retry", "whatsapp_inbox.template.retry"),
    ("POST", "/whatsapp_inbox/templates/delete", "whatsapp_inbox.template.delete"),
    ("POST", "/whatsapp_inbox/templates/samples", "whatsapp_inbox.template_sample.upload"),
    ("GET", "/whatsapp_inbox/channel", "whatsapp_inbox.channel.get"),
    ("POST", "/whatsapp_inbox/channel/prepare", "whatsapp_inbox.channel.prepare"),
    ("POST", "/whatsapp_inbox/channel/connect", "whatsapp_inbox.channel.connect"),
    ("POST", "/whatsapp_inbox/channel/disconnect", "whatsapp_inbox.channel.disconnect"),
    ("GET", "/whatsapp_inbox/agents", "whatsapp_inbox.agent.list"),
}
SYSTEM_ONLY = {
    "whatsapp_inbox.message.receive",
    "whatsapp_inbox.message.update_status",
    "whatsapp_inbox.channel.sync",
    "whatsapp_inbox.conversation.claim_for_customer",
    "whatsapp_inbox.conversation.move_customer",
    "whatsapp_inbox.conversation.erase_for_customer",
    "whatsapp_inbox.conversation.release_customer",
    "whatsapp_inbox.message.claim_delivery",
    "whatsapp_inbox.message.record_delivery",
    "whatsapp_inbox.conversation.claim_erasure",
    "whatsapp_inbox.conversation.record_erasure",
    "whatsapp_inbox.delivery.resume",
    "whatsapp_inbox.template.claim_submit",
    "whatsapp_inbox.template.record_submit",
    "whatsapp_inbox.template.claim_delete",
    "whatsapp_inbox.template.record_delete",
}


def get(client, path, host="a.localhost", **params):
    return client.get(f"/api{path}", params, HTTP_HOST=host)


def post(client, path, data, host="a.localhost"):
    return client.post(
        f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=host
    )


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("boss", host="a", role="hub_admin"))
    return client


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(
        make_user("luis", host="a", role="hub_employee", first_name="Luis")
    )
    return client


def test_every_route_is_bound_to_its_operation():
    routes = {
        (method, path, route.operation_id)
        for path, view in router.path_operations.items()
        for route in view.operations
        for method in route.methods
    }
    assert routes == ROUTES


def test_the_system_s_operations_have_no_route():
    bound = {operation for _, _, operation in ROUTES}
    assert bound.isdisjoint(SYSTEM_ONLY)


def test_the_api_keeps_parity():
    assert ensure_api_parity(api) == []


def test_the_spa_s_route_map_names_every_route():
    # frontend/generated/operations.json: the op → route map the SDK's client uses (hand-written until V3).
    spa = json.loads(
        (settings.BASE_DIR / "frontend" / "generated" / "operations.json").read_text()
    )
    mine = {
        (route["method"].upper(), route["path"].removeprefix("/api"), op)
        for op, route in spa.items()
        if op.startswith("whatsapp_inbox.")
    }
    assert mine == ROUTES


@pytest.mark.django_db
def test_the_inbox_over_http(employee_client):
    receive("wamid.1", contact_name="Ana")
    page = get(employee_client, "/whatsapp_inbox/conversations", search="600 111 222")
    assert page.status_code == 200
    row = page.json()["rows"][0]
    assert (row["display_name"], row["unread_count"]) == ("Ana", 1)
    read = post(
        employee_client, "/whatsapp_inbox/conversations/mark_read", {"id": row["id"]}
    )
    assert (read.status_code, read.json()["unread_count"]) == (200, 0)
    thread = get(employee_client, "/whatsapp_inbox/messages", id=row["id"])
    assert thread.json()["rows"][0]["body"] == "Hola, ¿tenéis hora mañana?"
    note = post(
        employee_client, "/whatsapp_inbox/notes", {"id": row["id"], "text": "Llamar"}
    )
    assert (note.status_code, note.json()["author_name"]) == (201, "Luis")


@pytest.mark.django_db
def test_who_waits_for_an_answer_over_http(employee_client):
    # WHATSAPP_INBOX-F09: the bell's count and the device's notices, for an integration as for the Hub.
    receive("wamid.1", contact_name="Ana")
    count = get(employee_client, "/whatsapp_inbox/conversations/count_awaiting_reply")
    assert (count.status_code, count.json()) == (200, {"count": 1})
    told = get(employee_client, "/whatsapp_inbox/conversations/notices", limit=10)
    assert told.status_code == 200
    assert [(row["display_name"], row["last_message_preview"]) for row in told.json()["rows"]] == [("Ana", "Hola, ¿tenéis hora mañana?")]
    assert get(employee_client, "/whatsapp_inbox/conversations/notices", limit=101).status_code == 422


@pytest.mark.django_db
@respx.mock
def test_sending_over_http_is_201_queued_and_a_closed_window_is_a_409(employee_client, django_capture_on_commit_callbacks):
    connect()
    receive("wamid.1")
    conversation = get(employee_client, "/whatsapp_inbox/conversations").json()["rows"][0]["id"]
    respx.post("http://saas.test/internal/whatsapp/send").mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
    key = "0199e000-0000-7000-8000-0000000000bb"
    with django_capture_on_commit_callbacks(execute=True):
        sent = post(employee_client, "/whatsapp_inbox/messages/send", {"id": conversation, "text": "¡Hola!", "client_message_id": key})
    assert (sent.status_code, sent.json()["status"]) == (201, "queued")
    assert Message.objects.get(pk=sent.json()["id"]).status == "sent"
    from apps.whatsapp_inbox.models import Conversation

    Conversation.objects.update(last_inbound_at="2026-10-01T10:00:00Z")
    refused = post(
        employee_client,
        "/whatsapp_inbox/messages/send",
        {"id": conversation, "text": "¿Sigues ahí?", "client_message_id": "0199e000-0000-7000-8000-0000000000bc"},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "whatsapp_inbox.window_closed"


@pytest.mark.django_db
def test_a_422_names_its_field(admin_client):
    response = post(admin_client, "/whatsapp_inbox/messages/send", {"text": "Hola", "client_message_id": "0199e000-0000-7000-8000-0000000000bd"})
    assert response.status_code == 422
    assert set(response.json()["error"]["fields"]) == {"conversation"}


@pytest.mark.django_db
def test_an_employee_neither_erases_nor_opens_the_settings_reads_of_others(
    employee_client,
):
    receive("wamid.1")
    conversation = get(employee_client, "/whatsapp_inbox/conversations").json()["rows"][
        0
    ]["id"]
    assert (
        post(
            employee_client, "/whatsapp_inbox/conversations/erase", {"id": conversation}
        ).status_code
        == 403
    )
    assert get(employee_client, "/whatsapp_inbox/channel").status_code == 200


@pytest.mark.django_db
def test_without_a_session_nothing_is_read(client):
    assert get(client, "/whatsapp_inbox/conversations").status_code in (401, 403)


# Templates (WHATSAPP_INBOX-F29…F31)


@pytest.mark.django_db
@respx.mock
def test_templates_over_http_are_201_registered_after_the_commit_and_422_under_their_field(
    admin_client, django_capture_on_commit_callbacks
):
    connect()
    respx.post("http://saas.test/internal/whatsapp/templates").mock(
        return_value=httpx.Response(200, json={"meta_id": "m-1", "status": "PENDING"})
    )
    body = {
        "name": "recordatorio_cita",
        "language": "es",
        "category": "UTILITY",
        "body": "Hola {{1}}, te esperamos.",
        "body_examples": ["Ana"],
        "submit_key": "0199e000-0000-7000-8000-0000000000c1",
    }
    with django_capture_on_commit_callbacks(execute=True):
        made = post(admin_client, "/whatsapp_inbox/templates", body)
    assert (made.status_code, made.json()["status"], made.json()["submit_state"]) == (201, "DRAFT", "queued")
    listed = get(admin_client, "/whatsapp_inbox/templates").json()["rows"]
    assert [(row["name"], row["status"], row["meta_id"]) for row in listed] == [("recordatorio_cita", "PENDING", "m-1")]
    refused = post(admin_client, "/whatsapp_inbox/templates", {**body, "name": "Con Espacios", "submit_key": "0199e000-0000-7000-8000-0000000000c2"})
    assert refused.status_code == 422
    assert set(refused.json()["error"]["fields"]) == {"name"}
    taken = post(admin_client, "/whatsapp_inbox/templates", {**body, "submit_key": "0199e000-0000-7000-8000-0000000000c3"})
    assert (taken.status_code, taken.json()["error"]["code"]) == (409, "whatsapp_inbox.template_exists")


@pytest.fixture
def hub_files(settings):
    """``storages["hub_files"]`` in memory, empty for each test."""
    from django.core.files.storage import storages

    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": "django.core.files.storage.InMemoryStorage"}}
    storages._storages.pop("hub_files", None)
    yield storages["hub_files"]
    storages._storages.pop("hub_files", None)


@pytest.mark.django_db
def test_a_header_video_bigger_than_djangos_ceiling_still_uploads(admin_client, hub_files):
    """F29: a 16 MB MP4 is far above the 2.5 MB every other route takes; its file comes back as the template's."""
    import base64

    video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * (3 * 1024 * 1024)
    assert len(video) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE
    body = {"header_format": "VIDEO", "name": "visita.mp4", "content_base64": base64.b64encode(video).decode()}

    response = post(admin_client, "/whatsapp_inbox/templates/samples", body)

    assert response.status_code == 201
    assert {key: response.json()[key] for key in ("header_format", "content_type", "size", "name")} == {
        "header_format": "VIDEO",
        "content_type": "video/mp4",
        "size": len(video),
        "name": "visita.mp4",
    }


@pytest.mark.django_db
def test_a_header_file_past_the_largest_is_refused_before_it_is_read(admin_client):
    response = post(admin_client, "/whatsapp_inbox/templates/samples", {"content_base64": "A" * 36_100_000})

    assert (response.status_code, response.json()["error"]["code"]) == (413, "payload_too_large")


@pytest.mark.django_db
def test_an_employee_picks_templates_but_neither_makes_nor_deletes_them(employee_client):
    connect(templates=[{"name": "recordatorio", "language": "es", "body": "Hola", "meta_id": "m"}])
    [row] = get(employee_client, "/whatsapp_inbox/templates", sendable="true").json()["rows"]
    body = {"name": "otra", "language": "es", "body": "Hola", "submit_key": "0199e000-0000-7000-8000-0000000000c4"}
    assert post(employee_client, "/whatsapp_inbox/templates", body).status_code == 403
    assert post(employee_client, "/whatsapp_inbox/templates/delete", {"id": row["id"]}).status_code == 403
    sample = {"header_format": "IMAGE", "name": "carta.jpg", "content_base64": "/9j/4AAQ"}
    assert post(employee_client, "/whatsapp_inbox/templates/samples", sample).status_code == 403

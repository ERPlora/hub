"""``POST /api/whatsapp_inbox/messages/notify`` (FLOW-F31): the narrow send over HTTP, as the inbox's other routes."""

import json

import httpx
import pytest
import respx

from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import connect, receive

pytestmark = pytest.mark.django_db

PATH = "/api/whatsapp_inbox/messages/notify"


def post(client, data):
    return client.post(PATH, json.dumps(data), content_type="application/json", HTTP_HOST="a.localhost")


@pytest.fixture
def employee_client(client, make_user):
    client.force_login(make_user("luis", host="a", role="hub_employee"))
    return client


@respx.mock
def test_it_is_201_queued_to_the_exact_number_and_a_number_without_conversation_is_a_409(
    employee_client, django_capture_on_commit_callbacks
):
    connect()
    receive("wamid.1")
    respx.post("http://saas.test/internal/whatsapp/send").mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))
    with django_capture_on_commit_callbacks(execute=True):
        sent = post(employee_client, {"phone": "+34600111222", "text": "¡Confirmada!"})
    assert (sent.status_code, sent.json()["status"]) == (201, "queued")
    assert Message.objects.get(pk=sent.json()["id"]).status == "sent"

    nobody = post(employee_client, {"phone": "+34600999888", "text": "¡Confirmada!"})
    assert (nobody.status_code, nobody.json()["error"]["code"]) == (409, "whatsapp_inbox.no_conversation")


def test_a_number_not_international_is_a_422_on_its_field(employee_client):
    connect()
    receive("wamid.1")
    refused = post(employee_client, {"phone": "600111222", "text": "¡Confirmada!"})
    assert refused.status_code == 422
    assert set(refused.json()["error"]["fields"]) == {"phone"}

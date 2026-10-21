"""«Send a message to a customer» (FLOW-F31): the WhatsApp inbox's narrow send (``whatsapp_inbox.message.notify``) is an
action an automation may be granted and run, while the inbox's own send (a person's, to any number) still needs a
person in front. A run that cannot send leaves the reason in its history.
"""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import InvalidPayload

from apps.flow import queries
from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import connect, receive

from .conftest import run

pytestmark = pytest.mark.django_db

NOTIFY = "whatsapp_inbox.message.notify"
STEP = {
    "id": "s1",
    "kind": "command",
    "operation": NOTIFY,
    "params": {"phone": "input.phone", "text": "Hi {{input.name}}, it is confirmed."},
}


@pytest.fixture(autouse=True)
def saas(settings):
    settings.SAAS_INTERNAL_URL = "http://saas.test"
    settings.INTERNAL_SHARED_SECRET = "s3cret"


def automation() -> str:
    created = run("flow.flow.create", {"name": "Tell Ana", "trigger": {"kind": "manual"}, "steps": [STEP]})
    run("flow.flow.grant", {"id": str(created.id), "operations": [NOTIFY]})
    run("flow.flow.set_enabled", {"id": str(created.id), "enabled": True})
    return str(created.id)


def test_the_narrow_send_is_an_action_an_automation_may_take_and_the_inbox_s_own_send_is_not():
    catalog = queries.catalog_operations()
    assert NOTIFY in catalog
    assert "whatsapp_inbox.message.send" not in catalog
    fields = {field["name"] for field in queries.action_fields(catalog[NOTIFY])}
    assert {"phone", "text", "template"} <= fields


def test_granting_it_is_allowed_and_granting_the_inbox_s_send_still_needs_a_person():
    flow_id = automation()
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.grant", {"id": flow_id, "operations": [NOTIFY, "whatsapp_inbox.message.send"]})
    assert refused.value.code == "flow.high_risk"


def test_a_run_sends_to_the_customer_s_conversation_and_a_refusal_is_its_reason_in_the_history():
    connect()
    receive("wamid.IN", sent_at=(timezone.now() - dt.timedelta(minutes=10)).isoformat())
    flow_id = automation()

    done = run("flow.flow.run", {"id": flow_id, "input": {"phone": "+34600111222", "name": "Ana"}})
    assert done.status == "succeeded"
    message = Message.objects.get(direction="outbound")
    assert (message.conversation.phone, message.body, message.status) == ("+34600111222", "Hi Ana, it is confirmed.", "queued")

    typed = run("flow.flow.run", {"id": flow_id, "input": {"phone": "600111222", "name": "Ana"}})
    assert typed.status == "failed"
    assert "is not a number in international format" in typed.error_message

    nobody = run("flow.flow.run", {"id": flow_id, "input": {"phone": "+34600999888", "name": "Bea"}})
    assert (nobody.status, nobody.error_code) == ("failed", "whatsapp_inbox.no_conversation")
    assert Message.objects.filter(direction="outbound").count() == 1

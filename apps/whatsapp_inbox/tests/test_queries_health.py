"""``whatsapp_inbox.channel.health``: whether the business's number is connected, said in the Home's health row words.

It reads what erplora.com last reported of the number, for whoever reads the inbox; it is not a tool of the assistant,
which asks ``whatsapp_inbox.channel.get``, and it reads each business's own number.
"""

import pytest
from live.errors import PermissionDenied
from live.operations import get

from apps.whatsapp_inbox.tests.conftest import HUB_DB, B, connect, ctx_for, run
from base.tenancy.context import use_hub

pytestmark = HUB_DB

HEALTH = "whatsapp_inbox.channel.health"


@pytest.mark.parametrize(
    ("reported", "state"),
    [
        (None, "not_configured"),
        ({"status": "not_connected", "phone_number": ""}, "not_configured"),
        ({"status": "reconnect_needed"}, "no_signal"),
        ({}, "ok"),
    ],
)
def test_it_says_the_state_of_the_number_erplora_com_reported(reported, state):
    if reported is not None:
        connect(**reported)

    assert run(HEALTH, {}, ctx_for("hub_employee")).model_dump() == {"state": state}


def test_whoever_cannot_read_the_inbox_is_refused():
    with pytest.raises(PermissionDenied):
        run(HEALTH, {}, ctx_for("hub_accountant"))


def test_it_is_no_tool_of_the_assistant():
    assert not get(HEALTH).ai


def test_each_business_reads_its_own_number(hub_b):
    with use_hub(hub_b):
        connect(scope=B)
        assert run(HEALTH, {}, ctx_for(scope=B)).model_dump() == {"state": "ok"}

    assert run(HEALTH, {}, ctx_for()).model_dump() == {"state": "not_configured"}

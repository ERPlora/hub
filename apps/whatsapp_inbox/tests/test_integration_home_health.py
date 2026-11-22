"""The WhatsApp inbox in the Home's health row (BASE-F02): who runs the business is told whether the business's number
is connected, as erplora.com last reported it, with where to connect it. Nothing while the inbox is off, and nothing for
whoever does not run the business.

base and the inbox run for real: the row comes from WhatsappInboxConfig through ``base.health.list``, as the person, and
by HTTP as the SPA asks it.
"""

import dataclasses

import pytest
from live.operations import get

from apps.whatsapp_inbox.tests.conftest import HOST, HUB_DB, B, connect, ctx_for, run
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas.health import HealthListIn
from base.tenancy.context import use_hub

pytestmark = HUB_DB

SETTINGS = "/whatsapp_inbox/settings"


def row(ctx) -> dict | None:
    """The inbox's item of the health row for the person of ``ctx`` (``None``: not told)."""
    items = get("base.health.list")(ctx, HealthListIn()).model_dump(mode="json")["items"]
    found = [item for item in items if item["app"] == "whatsapp_inbox"]
    assert len(found) <= 1, found
    return found[0] if found else None


@pytest.mark.parametrize(
    ("reported", "state", "title", "action"),
    [
        (None, "not_configured", "WhatsApp not connected", "Connect WhatsApp"),
        ({"status": "not_connected", "phone_number": ""}, "not_configured", "WhatsApp not connected", "Connect WhatsApp"),
        ({"status": "reconnect_needed"}, "no_signal", "WhatsApp needs reconnecting", "Connect WhatsApp"),
        ({}, "ok", "WhatsApp connected", None),
    ],
)
def test_who_runs_the_business_is_told_whether_its_number_is_connected(reported, state, title, action):
    if reported is not None:
        connect(**reported)

    assert row(ctx_for("hub_owner")) == {
        "key": "whatsapp_inbox",
        "app": "whatsapp_inbox",
        "state": state,
        "title": title,
        "action": action,
        "route": SETTINGS if action else None,
    }


def test_it_says_it_in_the_persons_language():
    connect(status="reconnect_needed")

    item = row(ctx_for("hub_admin", language="es"))

    assert (item["title"], item["action"]) == ("Hay que volver a conectar WhatsApp", "Conectar WhatsApp")


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_whoever_does_not_run_the_business_is_not_told(role):
    assert row(ctx_for(role)) is None


def test_who_runs_the_business_without_connecting_the_number_is_not_told():
    reads_only = dataclasses.replace(
        ctx_for("hub_employee"), permissions=frozenset({VIEW_HOME, ADMINISTER_HUB, "whatsapp_inbox.view"})
    )

    assert row(reads_only) is None


def test_with_the_inbox_off_the_row_says_nothing_of_it_and_the_other_business_keeps_its_own(hub_b):
    with use_hub(hub_b):
        connect(scope=B)
    run("base.app.disable", {"app": "whatsapp_inbox"}, dataclasses.replace(ctx_for(), permissions=frozenset({"*"})))

    assert row(ctx_for("hub_owner")) is None
    with use_hub(hub_b):
        assert row(ctx_for("hub_owner", scope=B))["state"] == "ok"


def test_by_http_the_owner_is_told_in_their_language_and_an_employee_nothing(client, make_user):
    connect(status="reconnect_needed")
    client.force_login(make_user("boss", role="hub_owner"))

    response = client.get("/api/home/health", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es")

    assert response.status_code == 200, response.content
    told = {item["app"]: item for item in response.json()["items"]}
    assert told["whatsapp_inbox"] == {
        "key": "whatsapp_inbox",
        "app": "whatsapp_inbox",
        "state": "no_signal",
        "title": "Hay que volver a conectar WhatsApp",
        "action": "Conectar WhatsApp",
        "route": SETTINGS,
    }
    assert told["printing"]["state"] == "not_configured"

    client.force_login(make_user("leo", role="hub_employee"))
    response = client.get("/api/home/health", HTTP_HOST=HOST)

    assert (response.status_code, response.json()) == (200, {"items": []})

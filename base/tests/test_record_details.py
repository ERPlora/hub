"""FIX-HUB-BASE-ASSISTANT-CARD-SHOWS-RAW-VALUES: one record of the platform by its id — an API key, a device, a failed
event, a load —, read by who runs the business, as the screen that lists it names it. The assistant's card names by
them what a write of base names by its id («Revoke in API keys» says which key), never by the id; the API reads them
too. Each one is of the business that asks: another business's is not there.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from live.models import OutboxEvent

from base import access
from base.models import EventDelivery, ImportBatch, Membership, TrustedDevice
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

pytestmark = pytest.mark.django_db(databases=hubs.HUB_DATABASES)


@pytest.fixture(autouse=True)
def as_in_production(monkeypatch):
    """Every request opens its own database context, as in production (``base/tenancy/tests/conftest.py``)."""
    monkeypatch.setattr(context, "_test_fallback", None)
    cache.clear()
    yield
    cache.clear()


def signed_in(client, hub, role: str = "hub_admin", username: str = "saas:1"):
    user, _ = get_user_model().objects.get_or_create(username=username, defaults={"first_name": "Olga"})
    Membership.objects.get_or_create(user=user, host=hub.slug, defaults={"role": role})
    client.force_login(user)
    return client


def host(hub) -> str:
    return f"{hub.slug}.localhost:8000"


def api_key(client, hub) -> str:
    """A key made as its screen makes it (Employees › API keys)."""
    body = {"name": "Tienda online", "rate_per_minute": 60, "mode": "full", "scopes": {}}
    made = client.post("/api/keys", json.dumps(body), content_type="application/json", HTTP_HOST=host(hub))
    assert made.status_code == 200, made.content
    return made.json()["key"]["id"]


def device(client, hub) -> str:
    with use_hub(hub):
        return str(
            TrustedDevice.objects.create(
                token_digest=access.token_digest(f"token-{hub.slug}"), name="Barra", last_entry_at=timezone.now()
            ).pk
        )


def failed_event(client, hub) -> str:
    with use_hub(hub):
        now = timezone.now()
        event = OutboxEvent.objects.create(
            scope_kind="host", scope_key=hub.slug, name="sale.sale.completed", payload={}, created_at=now, delivered_at=now
        )
        delivery = EventDelivery.objects.create(
            event=event, app_label="invoice", status=EventDelivery.Status.DEAD, attempts=8, next_attempt_at=now
        )
        return str(delivery.pk)


def load(client, hub) -> str:
    with use_hub(hub):
        return str(
            ImportBatch.objects.create(
                name="Peluquería",
                source=ImportBatch.Source.CATALOG,
                purpose="template",
                status=ImportBatch.Status.PARTIAL,
                # As a load leaves it (base.services ``blueprint_import``): what each app loaded.
                report={"status": "partial", "apps": [], "dropped": []},
            ).pk
        )


#: Each read: its route, how a record of it is made, and the name its screen gives it.
RECORDS = [
    pytest.param("/keys/detail", api_key, "Tienda online", id="api_key"),
    pytest.param("/devices/detail", device, "Barra", id="device"),
    pytest.param("/system/failed-events/detail", failed_event, "sale.sale.completed", id="failed_event"),
    pytest.param("/settings/data/imports/detail", load, "Peluquería", id="import"),
]


@pytest.mark.parametrize(("path", "made", "name"), RECORDS)
def test_who_runs_the_business_reads_one_by_its_id_with_the_name_its_screen_gives_it(client, hub_a, path, made, name):
    signed_in(client, hub_a)
    record = made(client, hub_a)
    answer = client.get(f"/api{path}", {"id": record}, HTTP_HOST=host(hub_a))
    assert answer.status_code == 200, answer.content
    assert (answer.json()["id"], answer.json()["name"]) == (record, name)


@pytest.mark.parametrize(("path", "made", "name"), RECORDS)
def test_another_businesss_record_is_not_there(client, hub_a, hub_b, path, made, name):
    signed_in(client, hub_b)
    theirs = made(client, hub_b)
    signed_in(client, hub_a)
    answer = client.get(f"/api{path}", {"id": theirs}, HTTP_HOST=host(hub_a))
    assert (answer.status_code, answer.json()["error"]["code"]) == (404, "not_found")


@pytest.mark.parametrize(("path", "made", "name"), RECORDS)
def test_one_that_does_not_exist_is_not_there(client, hub_a, path, made, name):
    signed_in(client, hub_a)
    answer = client.get(f"/api{path}", {"id": "0192f0b2-9999-7000-8000-000000000009"}, HTTP_HOST=host(hub_a))
    assert (answer.status_code, answer.json()["error"]["code"]) == (404, "not_found")


@pytest.mark.parametrize(("path", "made", "name"), RECORDS)
def test_only_who_runs_the_business_reads_them_as_its_screen(client, hub_a, path, made, name):
    signed_in(client, hub_a)
    record = made(client, hub_a)
    signed_in(client, hub_a, role="hub_manager", username="saas:4")
    answer = client.get(f"/api{path}", {"id": record}, HTTP_HOST=host(hub_a))
    assert (answer.status_code, answer.json()["error"]["code"]) == (403, "permission_denied")

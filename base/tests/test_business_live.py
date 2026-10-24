"""A change of the business made on erplora.com reaches Settings › Business without reloading (APP-BASE-6, BASE-G99).

The SaaS registers the business again (``PUT /internal/hubs/{id}``, HUBS-F15) as the platform: its own event goes to the
platform's channel. ``base.business.get`` listens on the business's, so the registry notifies that one too, after the
COMMIT (a rollback says nothing), as the photo does (``test_hub_state_wake.py``); another business hears nothing.
"""

import json

import psycopg
import pytest
from django.db import connections
from live.context import Scope
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from base.events import HUB_REGISTERED
from base.models import Hub
from base.tests.test_internal import HUB_ID, signed

pytestmark = pytest.mark.django_db(transaction=True)

REGISTRY_PATH = f"/internal/hubs/{HUB_ID}"
REGISTRY = {
    "id": HUB_ID,
    "slug": "acme",
    "name": "Acme Bar",
    "country": "ES",
    "timezone": "Europe/Madrid",
    "language": "es",
}


@pytest.fixture
def listening():
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )
    sessions = []

    def open_session(scope: Scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 1.0) -> set[str]:
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


@pytest.fixture
def acme():
    # Already ready: registering it again reports nothing to the SaaS.
    Hub.objects.create(id=HUB_ID, slug="acme", status="ready", name="Acme Bar", country="ES", language="es")


def test_the_business_hears_its_language_changed_on_erplora_com(client, acme, listening):
    on_acme, on_other = listening(Scope("host", "acme")), listening(Scope("host", "other"))

    answer = signed(client, "put", REGISTRY_PATH, {**REGISTRY, "language": "en"})

    assert answer.status_code == 200, answer.content
    assert HUB_REGISTERED in heard(on_acme)
    assert heard(on_other, timeout=0.3) == set()
    assert Hub.objects.get(pk=HUB_ID).language == "en"


def test_a_refused_registration_notifies_nobody(client, acme, listening):
    Hub.objects.create(slug="taken", status="ready")
    on_acme = listening(Scope("host", "acme"))

    answer = signed(client, "put", REGISTRY_PATH, {**REGISTRY, "slug": "taken"})

    assert answer.status_code == 409
    assert heard(on_acme, timeout=0.3) == set()

"""A change of the business made on erplora.com reaches Settings › Business without reloading.

The SaaS registers the business again (``PUT /internal/hubs/{id}``, HUBS-F15) as the platform: its own event goes to the
platform's channel. ``base.business.get`` listens on the business's, so the registry notifies that one too, after the
COMMIT (a rollback says nothing), as the photo does (``test_hub_state_wake.py``); another business hears nothing.
"""

import pytest

from base.events import HUB_REGISTERED
from base.models import Hub
from base.tenancy.tests.business import A, B, HUB_DB_COMMITTED
from base.tests.test_hub_state_wake import heard, listening
from base.tests.test_internal import HUB_ID, signed

__all__ = ["listening"]

pytestmark = [HUB_DB_COMMITTED]

REGISTRY_PATH = f"/internal/hubs/{HUB_ID}"
REGISTRY = {
    "id": HUB_ID,
    "slug": A.key,
    "name": "Acme Bar",
    "country": "ES",
    "timezone": "Europe/Madrid",
    "language": "es",
}


@pytest.fixture
def acme(hub_a):
    # Already ready: registering it again reports nothing to the SaaS.
    Hub.objects.filter(pk=hub_a.pk).update(name="Acme Bar", country="ES", language="es")


def test_the_business_hears_its_language_changed_on_erplora_com(client, acme, listening):
    on_acme, on_other = listening(A), listening(B)

    answer = signed(client, "put", REGISTRY_PATH, {**REGISTRY, "language": "en"})

    assert answer.status_code == 200, answer.content
    assert HUB_REGISTERED in heard(on_acme)
    assert heard(on_other, timeout=0.3) == set()
    assert Hub.objects.get(pk=HUB_ID).language == "en"


def test_a_refused_registration_notifies_nobody(client, acme, listening):
    Hub.objects.create(slug="taken", status="ready")
    on_acme = listening(A)

    answer = signed(client, "put", REGISTRY_PATH, {**REGISTRY, "slug": "taken"})

    assert answer.status_code == 409
    assert heard(on_acme, timeout=0.3) == set()

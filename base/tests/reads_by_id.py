"""The API's read of one record by its id, as a screen asks it at a business's host: shared by the apps' tests of their
reads by id (``apps/<app>/tests/test_reads_by_id.py``)."""

from django.contrib.auth import get_user_model

from base.models import Membership
from base.tenancy.context import use_hub


def signed_in(client, hub):
    """``client`` signed in as an administrator of ``hub``."""
    user, _ = get_user_model().objects.get_or_create(username="saas:1", defaults={"first_name": "Olga"})
    Membership.objects.get_or_create(user=user, host=hub.slug, defaults={"role": "hub_admin"})
    client.force_login(user)
    return client


def read(client, hub, path: str, record_id) -> tuple[int, dict]:
    answer = client.get(f"/api{path}", {"id": str(record_id)}, HTTP_HOST=f"{hub.slug}.localhost:8000")
    return answer.status_code, answer.json()


def read_own(client, hub, path: str, made) -> dict:
    """A record ``made()`` in ``hub``, read by its id at its host by its administrator: the answer, a 200 with its id."""
    signed_in(client, hub)
    with use_hub(hub):
        record = made()
    status, body = read(client, hub, path, record.id)
    assert status == 200, body
    assert body["id"] == str(record.id)
    return body


def read_theirs(client, hub, other, path: str, made) -> tuple[int, dict]:
    """A record ``made()`` in ``other``, asked for by its id at ``hub``'s host by ``hub``'s administrator."""
    with use_hub(other):
        theirs = made()
    signed_in(client, hub)
    return read(client, hub, path, theirs.id)

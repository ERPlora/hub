"""Migration 0003 of the cash register: the shifts kept before it say whose they are.

Before it, a shift kept who opened and closed it only as the screen shows it (a name, else an e-mail, else a username),
which no longer names a person once they rename. The migration gives each kept shift the person whose name, e-mail or
username that label is, when exactly one person of the business answers to it; a label nobody or several people answer
to stays without a person, so only whoever sees every shift sees it. Backwards it changes nothing: the columns go.

The function of the ``RunPython`` is called the way the migration runs it, with the app registry and a schema editor
whose connection is business A's own database, inside the test's transaction.
"""

from importlib import import_module

from django.apps import apps as global_apps
from django.db import connections
from django.utils import timezone

from apps.cash_register.models import Session
from base.models import HubUser
from base.tenancy.context import current_alias

from .conftest import HUB_DB

pytestmark = HUB_DB

MIGRATION = import_module("apps.cash_register.migrations.0003_session_people")


class _SchemaEditor:
    @property
    def connection(self):
        return connections[current_alias()]


def kept(sequence: int, opened_by: str, closed_by: str = "") -> Session:
    """A closed shift as it was kept before the migration: who did it only by its label."""
    now = timezone.now()
    return Session.objects.create(
        number=f"S-261101-{sequence:04d}",
        business_day=now.date(),
        sequence=sequence,
        status=Session.Status.CLOSED,
        opened_by=opened_by,
        closed_at=now,
        closed_by=closed_by,
        expected_balance=0,
    )


def whose(session: Session) -> tuple[str, str]:
    session.refresh_from_db()
    return session.opened_by_username, session.closed_by_username


def test_each_label_that_names_one_person_becomes_that_person():
    HubUser.objects.create(username="saas:ana", name="Ana Ruiz", email="ana@example.com")
    HubUser.objects.create(username="saas:bea", name="", email="bea@example.com")
    HubUser.objects.create(username="demo:carla", name="", email="")
    by_name = kept(1, "Ana Ruiz", "bea@example.com")
    by_username = kept(2, "demo:carla", "Ana Ruiz")
    MIGRATION.who_opened_and_closed(global_apps, _SchemaEditor())
    assert whose(by_name) == ("saas:ana", "saas:bea")
    assert whose(by_username) == ("demo:carla", "saas:ana")


def test_a_label_of_nobody_or_of_several_people_stays_without_a_person():
    HubUser.objects.create(username="saas:ana", name="Ana Ruiz")
    HubUser.objects.create(username="saas:ana2", name="Ana Ruiz")
    twice = kept(1, "Ana Ruiz", "Closed by a key")
    by_itself = kept(2, "Somebody who left")
    MIGRATION.who_opened_and_closed(global_apps, _SchemaEditor())
    assert whose(twice) == ("", "")
    assert whose(by_itself) == ("", "")

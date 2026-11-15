"""What VeriFactu answers the platform before a business's database is put back as it was at a moment (hub#1205,
hub#1198; ``base.tenancy.restore``).

The platform asks through a direct connection to a database closed to the app (the business's own, or its copy on a
temporary cluster, which has no alias), never through the ORM: each production record by id, with what it says of
its life at the AEAT (its status, when it was sent, when it last changed). A record the copy lacks or has otherwise
stops the restore, since putting the copy back would repeat numbers the AEAT already has. The AEAT's test environment
files nothing, so its records never count; a database the app was never set up in has nothing to say. The read is the
app's own (``queries.record_states``); its config's ``fiscal_record_states`` answers the platform with it.
"""

import datetime as dt

import pytest
from django.apps import apps
from django.db import connection
from django.utils import timezone

from apps.verifactu import queries
from apps.verifactu.models import Environment, Record
from apps.verifactu.tests.test_fiscal_backlog import record

pytestmark = pytest.mark.django_db


def direct():
    """The raw connection of the tests' database, as the restore's direct one reads it."""
    connection.ensure_connection()
    return connection.connection


def test_each_production_record_says_its_status_when_it_was_sent_and_when_it_last_changed():
    now = timezone.now()
    sent = record(Record.Status.ACCEPTED, now - dt.timedelta(days=1))
    Record.objects.filter(pk=sent.pk).update(transmitted_at=now - dt.timedelta(hours=3))
    waiting = record(Record.Status.PENDING, now - dt.timedelta(minutes=5))
    sent.refresh_from_db()
    waiting.refresh_from_db()

    assert queries.record_states(direct()) == {
        sent.pk: (Record.Status.ACCEPTED, sent.transmitted_at, sent.updated_at),
        waiting.pk: (Record.Status.PENDING, None, waiting.updated_at),
    }


def test_a_record_of_the_aeats_test_environment_never_counts():
    record(Record.Status.ACCEPTED, timezone.now(), environment=Environment.TESTING)

    assert queries.record_states(direct()) == {}


def test_a_database_without_its_table_has_nothing_to_say():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE verifactu_record CASCADE")

    assert queries.record_states(direct()) == {}


def test_the_app_answers_the_platforms_question_with_its_records():
    sent = record(Record.Status.ACCEPTED, timezone.now() - dt.timedelta(hours=2))
    sent.refresh_from_db()

    assert apps.get_app_config("verifactu").fiscal_record_states(direct()) == {
        sent.pk: (Record.Status.ACCEPTED, None, sent.updated_at)
    }

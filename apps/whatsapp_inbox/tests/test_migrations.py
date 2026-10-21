"""The inbox's migrations: in step with the models, and the channel's move to one row per business (0005) both ways.

The one shared row cannot be told apart by business: going forward it is not kept (each business's row is born from
its next photo); going back leaves the newest-synced row as the one row again.
"""

import io

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

APP = "whatsapp_inbox"
BEFORE = [(APP, "0004_message_reply_id")]
AFTER = [(APP, "0005_channel_per_business")]


def test_the_migrations_are_in_step_with_the_models(db):
    output = io.StringIO()
    call_command("makemigrations", APP, "--check", "--dry-run", stdout=output)
    assert "No changes detected" in output.getvalue()


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


@pytest.mark.django_db(transaction=True)
def test_the_shared_row_goes_forward_to_none_and_back_to_one():
    try:
        old = migrate(BEFORE)
        old.get_model(APP, "Channel").objects.create(status="connected", version=7)

        new = migrate(AFTER)
        Channel = new.get_model(APP, "Channel")
        assert not Channel.objects.exists()
        Channel.objects.create(host="a", status="connected", version=50)
        Channel.objects.create(host="b", status="reconnect_needed", version=120)

        old = migrate(BEFORE)
        rows = list(old.get_model(APP, "Channel").objects.values_list("slot", "status", "version"))
        assert rows == [(1, "reconnect_needed", 120)]
    finally:
        migrate(AFTER)

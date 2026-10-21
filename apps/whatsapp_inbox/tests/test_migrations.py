"""The inbox's migrations: in step with the models, and the moves to one business each, both ways: the channel's
(0005) and the templates' (0006).

The one shared channel row cannot be told apart by business: going forward it is not kept (each business's row is
born from its next photo); going back leaves the newest-synced row as the one row again. The shared templates go
forward unowned (no business lists them; the staff sees them in the admin) and, going back, keep one live copy per
name and language: the newest-synced.
"""

import io

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

APP = "whatsapp_inbox"
BEFORE = [(APP, "0004_message_reply_id")]
AFTER = [(APP, "0005_channel_per_business")]
LATEST = [(APP, "0006_templates_per_business")]


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
        migrate(LATEST)


@pytest.mark.django_db(transaction=True)
def test_the_shared_templates_go_forward_unowned_and_back_to_one_per_name():
    try:
        old = migrate(AFTER)
        old.get_model(APP, "Template").objects.create(name="recordatorio", language="es", body="Hola")

        new = migrate(LATEST)
        Template = new.get_model(APP, "Template")
        assert list(Template.objects.values_list("host", "name", "body")) == [("", "recordatorio", "Hola")]
        Template.objects.all().delete()
        Template.objects.create(host="a", name="recordatorio", language="es", body="De a", synced_at="2026-10-15T10:00Z")
        Template.objects.create(host="b", name="recordatorio", language="es", body="De b", synced_at="2026-10-16T10:00Z")
        Template.objects.create(host="b", name="aviso", language="es", body="Aviso de b")

        old = migrate(AFTER)
        rows = sorted(old.get_model(APP, "Template").objects.values_list("name", "body"))
        assert rows == [("aviso", "Aviso de b"), ("recordatorio", "De b")]
    finally:
        migrate(LATEST)

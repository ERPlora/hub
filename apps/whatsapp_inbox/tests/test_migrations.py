"""The inbox's migrations: in step with the models, and the moves to one business each, both ways: the channel's
(0005), the templates' (0006) and the business of what the Hub hands erplora.com (0007).

The one shared channel row cannot be told apart by business: going forward it is not kept (each business's row is
born from its next photo); going back leaves the newest-synced row as the one row again. The shared templates go
forward unowned (no business lists them; the staff sees them in the admin) and, going back, keep one live copy per
name and language: the newest-synced. A message or an erasure made before 0007 comes forward with no business (the
worker resumes it as its own scope, as before); going back keeps the rows and drops the two columns. Every test leaves
the database at the app's latest migration, whatever that is when it runs.
"""

import datetime as dt
import uuid

import io

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

APP = "whatsapp_inbox"
BEFORE = [(APP, "0004_message_reply_id")]
AFTER = [(APP, "0005_channel_per_business")]
TEMPLATES = [(APP, "0006_templates_per_business")]
DELIVERIES = [(APP, "0007_deliveries_per_business")]


def test_the_migrations_are_in_step_with_the_models(db):
    output = io.StringIO()
    call_command("makemigrations", APP, "--check", "--dry-run", stdout=output)
    assert "No changes detected" in output.getvalue()


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


def latest():
    """The app's last migration, so that what comes after these tests finds every column."""
    return MigrationExecutor(connection).loader.graph.leaf_nodes(APP)


def columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        return {column.name for column in connection.introspection.get_table_description(cursor, table)}


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
        migrate(latest())


@pytest.mark.django_db(transaction=True)
def test_the_shared_templates_go_forward_unowned_and_back_to_one_per_name():
    try:
        old = migrate(AFTER)
        old.get_model(APP, "Template").objects.create(name="recordatorio", language="es", body="Hola")

        new = migrate(TEMPLATES)
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
        migrate(latest())


@pytest.mark.django_db(transaction=True)
def test_messages_and_erasures_go_forward_with_no_business_and_back_without_the_columns():
    try:
        old = migrate(TEMPLATES)
        Conversation, Message = old.get_model(APP, "Conversation"), old.get_model(APP, "Message")
        when = dt.datetime(2026, 10, 15, tzinfo=dt.UTC)
        talk = Conversation.objects.create(phone="+34600111222")
        Message.objects.create(
            conversation=talk, direction="outbound", origin="hub", status="queued", client_message_id=uuid.uuid7(), sent_at=when
        )
        Conversation.objects.create(phone="", erase_status="pending", erase_phone="+34600111333", erased_at=when)

        new = migrate(DELIVERIES)
        assert list(new.get_model(APP, "Message").objects.values_list("host", flat=True)) == [""]
        assert sorted(new.get_model(APP, "Conversation").objects.values_list("erase_status", "erase_host")) == [
            ("", ""),
            ("pending", ""),
        ]
        new.get_model(APP, "Message").objects.update(host="a")

        old = migrate(TEMPLATES)
        assert "host" not in columns("whatsapp_inbox_message")
        assert "erase_host" not in columns("whatsapp_inbox_conversation")
        assert old.get_model(APP, "Message").objects.count() == 1
        assert old.get_model(APP, "Conversation").objects.count() == 2
    finally:
        migrate(latest())

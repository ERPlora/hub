"""The inbox's migrations: in step with the models, and the moves to one business each, both ways: the channel's
(0005), the templates' (0006) and the business of what the Hub hands erplora.com (0007).

The one shared channel row cannot be told apart by business: going forward it is not kept (each business's row is
born from its next photo); going back leaves the newest-synced row as the one row again. The shared templates go
forward unowned (no business lists them; the staff sees them in the admin) and, going back, keep one live copy per
name and language: the newest-synced. A message or an erasure made before 0007 comes forward with no business (the
worker resumes it as its own scope, as before); going back keeps the rows and drops the two columns. They run on a
business's own database, cloned from the template for each test, through the migrator's alias as ``migrate_hubs`` runs
them.
"""

import datetime as dt
import uuid

import io

import pytest
from django.core.management import call_command
from django.db import connections
from django.db.migrations.executor import MigrationExecutor

from apps.whatsapp_inbox.tests.conftest import HUB_DB
from base.tenancy import connections as tenancy_connections
from base.tenancy import names
from base.tenancy.tests import hubs

APP = "whatsapp_inbox"
BEFORE = [(APP, "0004_message_reply_id")]
AFTER = [(APP, "0005_channel_per_business")]
TEMPLATES = [(APP, "0006_templates_per_business")]
DELIVERIES = [(APP, "0007_deliveries_per_business")]


@HUB_DB
def test_the_migrations_are_in_step_with_the_models():
    output = io.StringIO()
    call_command("makemigrations", APP, "--check", "--dry-run", stdout=output)
    assert "No changes detected" in output.getvalue()


@pytest.fixture
def database(hub_databases, django_db_blocker):
    """The migrator's connection to a business's database cloned from the template for the test, dropped after it. No
    test case around it: one refuses the migrator's alias (``…__ddl``), which is not among its databases."""
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with django_db_blocker.unblock(), hubs.clone_of_the_template(hub_databases, name):
        database = connections[tenancy_connections.register_ddl_alias(name)]
        try:
            yield database
        finally:
            database.close()


def migrate(database, targets):
    """Migrates ``database`` to ``targets`` and gives its models as its tables are now: every app at the migrations the
    database has applied, so a row a test writes in another app's table (the customer a booking needs) fits it."""
    executor = MigrationExecutor(database)
    executor.loader.build_graph()
    executor.migrate(targets)
    loader = MigrationExecutor(database).loader
    return loader.project_state([key for key in loader.applied_migrations if key in loader.graph.nodes]).apps


def columns(database, table: str) -> set[str]:
    with database.cursor() as cursor:
        return {column.name for column in database.introspection.get_table_description(cursor, table)}


def test_the_shared_row_goes_forward_to_none_and_back_to_one(database):
    old = migrate(database, BEFORE)
    old.get_model(APP, "Channel").objects.using(database.alias).create(status="connected", version=7)

    new = migrate(database, AFTER)
    Channel = new.get_model(APP, "Channel")
    assert not Channel.objects.using(database.alias).exists()
    Channel.objects.using(database.alias).create(host="a", status="connected", version=50)
    Channel.objects.using(database.alias).create(host="b", status="reconnect_needed", version=120)

    old = migrate(database, BEFORE)
    rows = list(old.get_model(APP, "Channel").objects.using(database.alias).values_list("slot", "status", "version"))
    assert rows == [(1, "reconnect_needed", 120)]


def test_the_shared_templates_go_forward_unowned_and_back_to_one_per_name(database):
    old = migrate(database, AFTER)
    old.get_model(APP, "Template").objects.using(database.alias).create(name="recordatorio", language="es", body="Hola")

    new = migrate(database, TEMPLATES)
    Template = new.get_model(APP, "Template")
    assert list(Template.objects.using(database.alias).values_list("host", "name", "body")) == [("", "recordatorio", "Hola")]
    Template.objects.using(database.alias).all().delete()
    Template.objects.using(database.alias).create(host="a", name="recordatorio", language="es", body="De a", synced_at="2026-10-15T10:00Z")
    Template.objects.using(database.alias).create(host="b", name="recordatorio", language="es", body="De b", synced_at="2026-10-16T10:00Z")
    Template.objects.using(database.alias).create(host="b", name="aviso", language="es", body="Aviso de b")

    old = migrate(database, AFTER)
    rows = sorted(old.get_model(APP, "Template").objects.using(database.alias).values_list("name", "body"))
    assert rows == [("aviso", "Aviso de b"), ("recordatorio", "De b")]


def test_messages_and_erasures_go_forward_with_no_business_and_back_without_the_columns(database):
    old = migrate(database, TEMPLATES)
    Conversation, Message = old.get_model(APP, "Conversation"), old.get_model(APP, "Message")
    when = dt.datetime(2026, 10, 15, tzinfo=dt.UTC)
    talk = Conversation.objects.using(database.alias).create(phone="+34600111222")
    Message.objects.using(database.alias).create(
        conversation=talk, direction="outbound", origin="hub", status="queued", client_message_id=uuid.uuid7(), sent_at=when
    )
    Conversation.objects.using(database.alias).create(phone="", erase_status="pending", erase_phone="+34600111333", erased_at=when)

    new = migrate(database, DELIVERIES)
    assert list(new.get_model(APP, "Message").objects.using(database.alias).values_list("host", flat=True)) == [""]
    assert sorted(new.get_model(APP, "Conversation").objects.using(database.alias).values_list("erase_status", "erase_host")) == [
        ("", ""),
        ("pending", ""),
    ]
    new.get_model(APP, "Message").objects.using(database.alias).update(host="a")

    old = migrate(database, TEMPLATES)
    assert "host" not in columns(database, "whatsapp_inbox_message")
    assert "erase_host" not in columns(database, "whatsapp_inbox_conversation")
    assert old.get_model(APP, "Message").objects.using(database.alias).count() == 1
    assert old.get_model(APP, "Conversation").objects.using(database.alias).count() == 2


HEADER_FILES = [(APP, "0008_template_header_files")]
BEFORE_HEADER_FILES = [(APP, "0007_deliveries_per_business")]
HOST_DEFAULTS = [(APP, "0011_host_defaults")]
NO_HOSTS = [(APP, "0012_no_business_hosts")]
#: The business each row carried before hub#1053, as (model, its table, its column).
HOST_COLUMNS = (
    ("Channel", "whatsapp_inbox_channel", "host"),
    ("Conversation", "whatsapp_inbox_conversation", "erase_host"),
    ("Message", "whatsapp_inbox_message", "host"),
    ("Template", "whatsapp_inbox_template", "host"),
    ("TemplateSample", "whatsapp_inbox_templatesample", "host"),
)


def column_default(database, table: str, column: str) -> str | None:
    """The database default of ``table.column`` (its SQL text), ``None`` when it has none."""
    with database.cursor() as cursor:
        cursor.execute(
            "SELECT column_default FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            [table, column],
        )
        [default] = cursor.fetchone()
        return default


def test_business_hosts_get_a_default_and_leave_only_the_state(database):
    migrate(database, HOST_DEFAULTS)
    for _model, table, column in HOST_COLUMNS:
        assert column_default(database, table, column) is not None

    new = migrate(database, NO_HOSTS)
    for model, table, column in HOST_COLUMNS:
        assert column not in {item.name for item in new.get_model(APP, model)._meta.get_fields()}
        assert column in columns(database, table)

    Channel = new.get_model(APP, "Channel")
    TemplateSample = new.get_model(APP, "TemplateSample")
    Channel.objects.using(database.alias).create()
    TemplateSample.objects.using(database.alias).create(
        header_format="IMAGE", key="sample.jpg", sha256="a" * 64,
        content_type="image/jpeg", size=10, name="sample.jpg",
    )
    old = migrate(database, HOST_DEFAULTS)
    assert "host" in {item.name for item in old.get_model(APP, "Channel")._meta.get_fields()}


def test_the_templates_with_a_file_header_the_hub_now_sends_are_marked_and_back_unmarked(database):
    """F33: a photo header the Hub fills with the file chosen; one with named variables or a code still not."""
    old = migrate(database, BEFORE_HEADER_FILES)
    Template = old.get_model(APP, "Template")
    for name, fields in {
        "foto": {"header_format": "IMAGE", "body": "Hola {{1}}"},
        "foto_con_nombre": {"header_format": "IMAGE", "body": "Hola {{nombre}}"},
        "codigo": {"header_format": "DOCUMENT", "category": "AUTHENTICATION", "body": "{{1}}"},
        "texto": {"header_format": "TEXT", "header": "Tu cita", "body": "Hola {{1}}"},
    }.items():
        Template.objects.using(database.alias).create(host="a", name=name, language="es", supported=name == "texto", **fields)

    new = migrate(database, HEADER_FILES)
    marked = dict(new.get_model(APP, "Template").objects.using(database.alias).values_list("name", "supported"))
    assert marked == {"foto": True, "foto_con_nombre": False, "codigo": False, "texto": True}

    old = migrate(database, BEFORE_HEADER_FILES)
    back = dict(old.get_model(APP, "Template").objects.using(database.alias).values_list("name", "supported"))
    assert back == {"foto": False, "foto_con_nombre": False, "codigo": False, "texto": True}

